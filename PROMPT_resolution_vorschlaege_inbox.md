# Prompt: Auto-Erkennung gelöster Punkte bei Meeting-Eingang → Vorschläge in der Inbox

## Kontext

Du arbeitest am Projekt **„Dashboard Job“**: Supabase-Backend (Projekt-Ref `lghwikeotbkmojyyjglz`, Supabase-MCP-Tools verfügbar, Edge-Function-Code lokal unter `supabase/functions/`, Deploy per `supabase functions deploy <name> --project-ref lghwikeotbkmojyyjglz`) und React-Frontend unter `meeting-os/` (Git-Repo, Push auf `main` deployt automatisch über Vercel).

Bestehender Ablauf beim Meeting-Eingang:
1. Make.com legt Meetings als `inbox_items` (entity_type `meeting`) an bzw. `ingest-transcript` schreibt in `meetings`.
2. Ein DB-Trigger (`on_meeting_insert_extract`, AFTER INSERT auf `meetings`, via `pg_net`) ruft die Edge Function `extract-structured-data` auf, die Todos/Blocker/offene Punkte extrahiert und als `inbox_items` (status `pending`) zur Freigabe ablegt.
3. Der Nutzer bestätigt Einträge in der Inbox-Seite des Frontends (`meeting-os/src/pages/InboxPage.tsx`, Handler `handleInboxApprove` in `meeting-os/src/App.tsx`, Typen in `meeting-os/src/supabase.ts`).

Was fehlt — und was du bauen sollst: Wenn ein neues Meeting eingeht, laufen zwei Prüfungen:

**A) Abschluss-Erkennung:** Behandelt das Meeting bereits erfasste offene Punkte (Todos, Blocker, offene Punkte) und belegt deren Abschluss? Für jeden belegten Abschluss entsteht ein VORSCHLAG in der Inbox. Erst wenn der Nutzer bestätigt, wird der Ziel-Eintrag als gelöst markiert (der Nightly-Job `nightly_archive_completed()` räumt Abgeschlossenes dann weg). Nichts wird automatisch geschlossen.

**B) Dubletten-Erkennung bei neuen Punkten:** Die frisch extrahierten `pending`-Inbox-Items dieses Meetings (Todos/Blocker/offene Punkte aus `extract-structured-data`) werden gegen den Bestand geprüft — existiert bereits ein offener Eintrag oder ein älteres pending-Item zur selben Sache? Treffer werden NICHT gelöscht, sondern im Inbox-Item als mögliche Dublette markiert, damit der Nutzer beim Freigeben informiert entscheidet.

Relevante Strukturen:
- `todos` (`status open|in_progress|done|cancelled`, `completed_at`), `blockers` (`status active|resolved|escalated`, `resolved_at`, `resolution_note`), `open_items` (`status open|watching|closed`, `closed_at`)
- `meetings` (`meeting_date`, `executive_summary`, `ai_summary`), `meeting_topics` (`summary` je Thema)
- `inbox_items` (`entity_type`, `payload jsonb`, `source`, `status pending|approved|rejected`) — der erlaubte `entity_type`-Wertebereich (Check-Constraint prüfen!) muss um einen neuen Typ erweitert werden
- `ANTHROPIC_API_KEY` **und `OPENAI_API_KEY`** stehen in den Edge Functions als Env-Var zur Verfügung (Embeddings laufen über OpenAI, siehe unten)
- `transcript_chunks` (`meeting_id`, `content`) — Chunks tragen einen kontextualisierten Kopf („Titel: … Datum: … Teilnehmer: … Zusammenfassung: …“) vor dem Rohtext; der Substring-Check für Zitate muss das tolerieren
- Vorbild für die Absicherung interner Edge-Aufrufe: Migration `20260706184310_secure_internal_edge_calls.sql`; Vorbild für den pg_net-Trigger: `20260528061738_create_meeting_extract_trigger.sql`

### Empirische Randbedingungen (aus der Datenbereinigung 2026-07-08 gemessen — beim Bau beachten)

- **Embedding-Modell:** Der Bestand ist mit OpenAI `text-embedding-3-small` (1536 Dim.) in der `embeddings`-Tabelle abgelegt. Deren `content` wird von `generate-embedding` über eine feste Formatvorlage gebaut (z. B. Todo: `"Todo: <title>. <description>. Zuständig: <assignee>. Priorität: <priority>. Status: <status>."`). **Jeder eigene Embedding-Aufruf für Inbox-Items MUSS exakt dieselbe Formatvorlage nutzen**, sonst ist die Cosine-Ähnlichkeit gegen den Bestand verzerrt.
- **`generate-embedding` taugt NICHT zum Embedden von Inbox-Payloads:** Die Funktion liest die Entität per `entity_id` aus der echten Tabelle und ist per `x-internal-secret` gated — ein Inbox-`pending`-Item existiert dort nicht. Der Dubletten-Check muss die Inbox-Inhalte selbst formatieren und direkt gegen die OpenAI-Embeddings-API schicken (Batch-Input möglich, ~100 pro Request).
- **Coverage ist vollständig:** Alle offenen `todos`/`blockers`/`open_items` sind per Trigger (`trigger_generate_embedding` / `embed_*`) 1:1 embedded — ein `backfill-embeddings`-Lauf ist nur Sicherheitsnetz, kein Regelfall.
- **Realistische Cosine-Schwellen (empirisch, nicht raten):** Echte semantische Dubletten liegen bei **0,85–0,89**; oberhalb 0,90 gibt es praktisch nichts; das Band **0,80–0,85** ist „verwandt, aber oft verschieden“ → gehört ins LLM-Urteil, nicht in die Auto-Markierung.
- **Erwartungshaltung Dubletten-Check:** Der Inbox-Rückstau ist groß (~900 Items), aber **semantisch kaum doppelt** (über den gesamten Bestand nur ~10 Kandidatenpaare ≥ 0,82). Der Dubletten-Check wird also selten anschlagen — das ist korrekt, kein Grund, die Empfindlichkeit hochzudrehen. Der größere Nutzen liegt in der Abschluss-Erkennung (A).

## Auftrag

### 1. Datenmodell

- Migration: `inbox_items.entity_type` um den Wert **`resolution`** erweitern.
- Payload-Schema für Resolution-Vorschläge (dokumentiere es im Funktions-Code):
  ```json
  {
    "target_table": "todos | blockers | open_items",
    "target_id": "<uuid>",
    "target_title": "<Titel des offenen Eintrags>",
    "proposed_status": "done | resolved | closed",
    "evidence_meeting_id": "<uuid>",
    "evidence_meeting_date": "YYYY-MM-DD",
    "evidence_quote": "<wörtlicher Beleg-Satz aus Summary oder Transkript-Chunk>",
    "evidence_source": "summary | chunk",
    "confidence": "high | medium"
  }
  ```

### 2. Edge Function `detect-resolutions`

Neue Funktion `supabase/functions/detect-resolutions/index.ts`:

- **Input:** `{ meeting_id }` (plus optional `{ backfill_days: N }` für manuelle Nachläufe über die letzten N Tage).
- **Beleg-Korpus des Meetings:** executive_summary + ai_summary + alle `meeting_topics.summary` **+ die Transkript-Chunks dieses Meetings** (`transcript_chunks` per `meeting_id` — Abschluss-Aussagen fallen oft der Summary-Kompression zum Opfer und stehen nur im Transkript). Übersteigt die Chunk-Masse ein Budget von ~40k Tokens, filtere die Chunks pro Kandidat vor (Embedding-Ähnlichkeit Kandidatentitel↔Chunk oder FTS) statt alles zu senden.
- **Präzisionsregeln für Chunk-Bezüge** (das Projektvokabular — „Berechtigungskonzept“, „Reporting“, „Datasphere“ — kommt in fast jedem Meeting vor; Einzelbegriff-Matches sind Rauschen): Kandidaten-Zuordnung Item↔Chunk erfordert das gemeinsame Auftreten **mehrerer seltener Tokens** des Item-Titels (Seltenheit über Dokumentfrequenz im Chunk-Bestand bestimmen, nicht hartkodieren; Items mit weniger als zwei markanten Tokens laufen nur gegen Summaries). Chunk-Belege **aggregiert bewerten**: mehrere übereinstimmende Stellen oder Chunk + Summary gemeinsam wiegen mehr als ein einzelner langer Chunk mit zufälliger Begriffsdichte.
- **Kandidaten-Vorfilter (SQL, kein LLM):** alle Einträge mit nicht-finalem Status aus den drei Tabellen, AUSSER Einträgen, die aus genau diesem Meeting stammen (`meeting_id`/`meeting_source` gleich — das Meeting kann nicht seine eigenen frisch extrahierten Punkte lösen). Vorauswahl gegen den Beleg-Korpus zweigleisig: **Embedding-Ähnlichkeit** (bestehende `embeddings`-Tabelle, Entity-Filter auf offene Einträge; Coverage ist 1:1, kein Backfill nötig — Meeting-Korpus dafür über OpenAI im selben Format embedden) UND lexikalische Token-Überlappung als Fallback. Vereinigung beider Trefferlisten, Top ~30 Kandidaten. Niemals alle offenen Einträge (aktuell ~260) ins LLM geben.
- **LLM-Prüfung:** Ein Aufruf an `claude-haiku-4-5-20251001` (Kosten klein halten; wenn die Trefferqualität in der Verifikation nicht reicht, auf `claude-sonnet-4-6` gehen). System-Prompt-Kernregeln:
  - Für jeden Kandidaten entscheiden: behandelt dieses Meeting den Punkt UND belegt es den Abschluss (erledigt/abgeschlossen/gelöst/geklärt/umgesetzt/freigegeben/entfallen/obsolet)?
  - Nur werten, wenn ein **wörtlich zitierbarer Satz** aus dem Beleg-Korpus den Abschluss trägt; das Zitat muss zurückgegeben und serverseitig per Substring-Check gegen Summaries UND Chunk-Inhalte validiert werden (Halluzinations-Schutz — kein valides Zitat, kein Vorschlag).
  - **Konfidenz-Regel nach Beleg-Quelle:** Zitat aus einer Summary → `high`. Zitat nur aus einem Transkript-Chunk → maximal `medium` (gesprochene Sprache: Konjunktive wie „wäre dann erledigt, wenn …“, Bedingungen und Ironie ausdrücklich NICHT als Abschluss werten). Das Payload-Feld `evidence_source: "summary" | "chunk"` mitführen; die Inbox zeigt es an.
  - „Wird weiter besprochen“, „ist in Arbeit“, „Thema erwähnt“ ist KEIN Abschluss.
  - Ausgabe als striktes JSON-Array mit target_id, proposed_status, evidence_quote, evidence_source, confidence.
- **Vorschlag anlegen:** je bestätigtem Treffer ein `inbox_items`-Insert (`entity_type='resolution'`, `status='pending'`, `source` = Meeting-Quelle/-Titel, Payload wie oben).
- **Idempotenz & Anti-Nerv-Regeln:**
  - Kein neuer Vorschlag, wenn für dieselbe `target_id` bereits ein `pending`-Resolution-Vorschlag existiert.
  - Kein neuer Vorschlag aus demselben Meeting für dieselbe `target_id` (auch nicht nach `rejected` — der Nutzer hat für dieses Beleg-Meeting bereits Nein gesagt; ein SPÄTERES Meeting darf denselben Punkt erneut vorschlagen).
  - Mehrfachaufruf mit derselben `meeting_id` erzeugt keine Duplikate.
- **Absicherung:** interner Aufruf nach dem Muster von `secure_internal_edge_calls` (wie `extract-structured-data`); keine offenen Endpunkte.

### 2b. Dubletten-Check für neue Punkte (gleiche Funktion, zweiter Durchgang)

Nach der Abschluss-Prüfung nimmt `detect-resolutions` die frisch angelegten `pending`-Inbox-Items
dieses Meetings (entity_type `todo|blocker|open_item`, `source` = dieses Meeting) und prüft je Item:

- **Vorfilter primär auf Embedding-Ebene** — wortgleiche Dubletten sind unrealistisch, dieselbe
  Sache wird in Folgemeetings umformuliert: Embedde das neue Item **direkt über die OpenAI-API**
  (`text-embedding-3-small`) mit der **identischen Content-Formatvorlage wie `generate-embedding`**
  (siehe „Empirische Randbedingungen“ — sonst ist die Ähnlichkeit gegen den Bestand verzerrt), und
  suche per Cosine gegen (a) die Embeddings offener Einträge der drei Zieltabellen (Coverage ist 1:1,
  `backfill-embeddings` nur als Fallback) und (b) ältere `pending`-Inbox-Items (deren Embedding
  on-the-fly berechnen; wenige neue Items pro Meeting, also günstig). **Schwelle ~0,85** (Kandidaten
  ab ~0,82 ins LLM-Urteil geben); die exakte Konstante in der Verifikation feinjustieren, aber NICHT
  unter 0,80 gehen — darunter ist alles Rauschen aus dem wiederkehrenden Projektvokabular. Lexikalische
  Titel-Ähnlichkeit nur als Ergänzung für Embedding-Lücken. Top ~5 Kandidaten je neuem Item.
- **LLM-Urteil (derselbe Haiku-Aufruf oder ein zweiter, gebündelt für alle Items des Meetings):**
  „gleiches reales Anliegen“ vs. „nur ähnliches Thema“. Gleicher Zuständiger und gleiche Sache
  → Dublette; gleiches Thema, aber anderer konkreter Punkt → keine. Embedding-Nähe allein ist
  NIE ein Urteil — sie liefert nur die Kandidaten.
- **Ergebnis:** Treffer werden im Payload des NEUEN Inbox-Items vermerkt, nichts wird gelöscht:
  ```json
  "duplicate_of": {
    "kind": "bestand | inbox",
    "table": "todos | blockers | open_items | inbox_items",
    "id": "<uuid>",
    "title": "<Titel des existierenden Eintrags>",
    "reason": "<ein Satz, warum Dublette>"
  }
  ```
- **Frontend:** Items mit `duplicate_of` bekommen in der Inbox ein deutliches Badge
  („⚠ Mögliche Dublette von: <Titel>“, klickbar → öffnet den existierenden Eintrag).
  Ablehnen bleibt ein Klick; Freigeben bleibt möglich (der Nutzer entscheidet).
- Damit bleibt die bestehende `extract-structured-data`-Funktion unangetastet — der
  Dubletten-Check läuft als nachgelagerter Anreicherungsschritt auf den bereits
  erzeugten pending-Items.

### 3. Auslösung

**Empfohlene Variante: Aufruf am Ende von `extract-structured-data`** (nicht als paralleler zweiter Trigger). Grund: Der Dubletten-Check (2b) braucht die frisch geschriebenen `pending`-Items dieses Meetings — ein separater `pg_net`-Trigger, der gleichzeitig mit der Extraktion feuert, läuft in ein Race (die Items sind noch nicht da). Am Ende von `extract-structured-data`, nachdem die pending-Items committed sind, ist die Reihenfolge garantiert. Alternativ ein nachgelagerter Trigger auf `inbox_items`, der zündet, wenn die Extraktion des Meetings fertig ist — aber der Inline-Aufruf ist robuster. Begründe die gewählte Variante im Code kurz. Wichtig: Das Promoten eines Inbox-Meetings (`promote_inbox_meeting` → INSERT in `meetings`) darf `detect-resolutions` nicht doppelt oder für ein Meeting ohne frische Extraktion auslösen — prüfe das explizit.

### 4. Frontend (Inbox-Seite)

- `meeting-os/src/supabase.ts`: `DbInboxItem['entity_type']`-Union um `'resolution'` erweitern.
- `meeting-os/src/pages/InboxPage.tsx`: neue Sektion **„Gelöst? (Vorschläge)“** im Stil der bestehenden Sektionen. Je Zeile: Ziel-Typ (Todo/Blocker/Offener Punkt), Titel (klickbar → öffnet den Ziel-Eintrag), Beleg-Zitat mit Meeting-Datum (klickbar → öffnet das Beleg-Meeting), Confidence-Badge, ✓/✕.
- Approve-Logik (in `App.tsx` bei `handleInboxApprove` einhängen, Fall `entity_type === 'resolution'`):
  - `todos` → `status='done'`, `completed_at` = evidence_meeting_date
  - `blockers` → `status='resolved'`, `resolved_at` = evidence_meeting_date, `resolution_note` = „lt. Meeting vom <Datum>: <Zitat-Kurzform>“
  - `open_items` → `status='closed'`, `closed_at` = evidence_meeting_date
  - danach Inbox-Item auf `approved`; existiert der Ziel-Eintrag nicht mehr, Vorschlag mit verständlicher Meldung verwerfen.
  - Ablehnen (✕) nutzt den bestehenden Reject-Pfad.
- Inbox-Zähler (`fetchTableCounts` / Sidebar-Badge) muss die neuen Vorschläge mitzählen.

### 5. Verifikation (Pflicht, Ende-zu-Ende)

1. `deno check` auf die Funktion, Deploy, dann Testlauf gegen ein reales jüngeres Meeting (`{ meeting_id }` direkt aufrufen) — zeige die erzeugten Vorschläge inkl. Zitaten.
2. Zweiter Aufruf mit derselben meeting_id → beweise, dass keine Duplikate entstehen.
3. Frontend: `tsc` + Build grün; Inbox-Sektion rendert; ein Vorschlag testweise approven → Ziel-Eintrag hat korrekten Status + Zeitstempel, Inbox-Item ist `approved`. Dubletten-Badge: an einem Meeting mit absichtlich wiederholtem Punkt zeigen, dass das neue Item das `duplicate_of`-Badge trägt und der Verweis den richtigen Bestands-Eintrag öffnet.
4. Backfill-Empfehlung: einmalig `{ backfill_days: 30 }` laufen lassen und die Anzahl der erzeugten Vorschläge berichten — NICHT automatisch approven.
5. Abschlussreport: was gebaut, wie getriggert, Kosten pro Meeting (Token-Schätzung), bekannte Grenzen.

## Leitplanken

- Vorschlagen, nie automatisch schließen — die Entscheidung bleibt in der Inbox.
- Kein Vorschlag ohne serverseitig validiertes wörtliches Zitat.
- Vorfilter hart begrenzen (Top ~30 Kandidaten), damit die Funktion pro Meeting nur Cent-Beträge kostet.
- Bestehende Extract-Pipeline nicht verändern, nur ergänzen; alle Migrationen zusätzlich als Datei unter `supabase/migrations/` ablegen.
- Deutsch für alle nutzersichtbaren Texte.
