# Prompt: Dubletten-Inventur & Bereinigung (Todos, Blocker, Offene Punkte)

## Kontext

Du arbeitest am Supabase-Projekt **„Dashboard Job“** (Projekt-Ref `lghwikeotbkmojyyjglz`, nutze die Supabase-MCP-Tools, v. a. `execute_sql`). Das Projekt ist ein Meeting-Dashboard: Aus Meeting-Transkripten werden automatisch Todos, Blocker und offene Punkte extrahiert (Tabellen `todos`, `blockers`, `open_items`). Weil dieselben Themen in Folgemeetings erneut besprochen werden, sind mit hoher Wahrscheinlichkeit **Dubletten** entstanden, und viele Einträge sind **inzwischen erledigt, stehen aber noch auf „offen“** — die Statuspflege erfolgt nicht konsequent.

Relevante Strukturen:
- `todos`: status `open | in_progress | done | cancelled`, Felder u. a. `assignee`, `title`, `description`, `meeting_id`, `meeting_source`, `project_id`, `due_date`, `completed_at`, `created_at`
- `blockers`: status `active | resolved | escalated`, Felder u. a. `reported_by`, `title`, `description`, `meeting_id`, `resolved_at`, `resolution_note`, `created_at`
- `open_items`: status `open | watching | closed`, Felder u. a. `owner`, `title`, `description`, `category`, `meeting_id`, `closed_at`, `created_at`
- Beleg-Material für Erledigungs-Nachweise: `meetings` (`meeting_date`, `executive_summary`, `ai_summary`) und `meeting_topics` (`name`, `summary`, je Meeting)
- `activity_log`: App-seitiges Änderungsprotokoll (Einträge entstehen normalerweise über das Frontend)
- Nightly-Job: pg_cron `nightly-archive` ruft täglich 22:00 `nightly_archive_completed()` auf und räumt abgeschlossene Einträge weg

## Auftrag

Zwei Phasen. Phase 1 erzeugt eine Inventur, Phase 2 führt die Bereinigung aus. Zwischen den Phasen legst du die Inventur vollständig vor.

### Phase 0 — Vorbereitung (Pflicht, vor jeder Mutation)

1. Lies die Definition von `nightly_archive_completed()` (`pg_get_functiondef`) und stelle fest, welche Status/Zeitstempel der Job als „abgeschlossen“ behandelt. Deine Status-Setzungen in Phase 2 müssen exakt dazu passen.
2. Prüfe mit `pg_trigger`/Migrationen, ob auf `todos`/`blockers`/`open_items` Trigger liegen, die bei UPDATE/DELETE Einträge in `activity_log` oder Embedding-Pipelines erzeugen. Anforderung des Nutzers: **Löschungen und Bereinigungs-Updates sollen das Protokoll nicht fluten.** Schreibe selbst keine `activity_log`-Einträge; falls Trigger welche erzeugen würden, benenne das und schlage das Vorgehen vor, bevor du mutierst.
3. Lege eine Backup-Tabelle an (z. B. `cleanup_backup_20260708` mit Spalten `entity_type text, row jsonb, reason text, deleted_at timestamptz default now()`). Jede Zeile, die du löschst oder deren Status du änderst, wird VOR der Mutation dort als JSON gesichert. Ohne Backup keine Mutation.

### Phase 1 — Inventur (nur lesen)

Erstelle über alle drei Tabellen (nur nicht-finale Status: `open`, `in_progress`, `active`, `watching`) zwei Listen:

**A) Dubletten-Gruppen.** Kandidaten-Findung mehrstufig — **primär auf Embedding-Ebene**, denn wortgleiche Dubletten sind unwahrscheinlich; dieselbe Sache wird in Folgemeetings umformuliert erfasst:
- Es existiert eine `embeddings`-Tabelle (pgvector) mit Entity-Embeddings. Prüfe zuerst die Coverage für `todos`/`blockers`/`open_items` und ziehe Fehlendes über die Edge Function `backfill-embeddings` nach.
- Kandidaten: paarweise Cosine-Ähnlichkeit innerhalb derselben Tabelle über der Schwelle (~0.75, an Stichproben kalibrieren und die gewählte Schwelle im Report nennen).
- Ergänzend, als Netz für Embedding-Lücken: exakt gleiche normalisierte Titel und `pg_trgm`-Ähnlichkeit (`similarity > 0.6`; Extension ggf. prüfen/aktivieren).
- Jede Kandidaten-Gruppe bewertest du inhaltlich anhand Titel + Beschreibung + Zuständigem: gleiches reales Anliegen = Dublette, nur ähnliches Thema = keine. Embedding-Nähe allein ist nie das Urteil.
- gleiche Sache über Tabellen hinweg (z. B. identischer Punkt als Todo UND offener Punkt) nur ausweisen, nicht automatisch löschen

Je Gruppe bestimmst du den **Überlebenden**: der vollständigste Eintrag (hat `meeting_id`/`meeting_source`, `project_id`, `due_date`, längste Beschreibung; bei Gleichstand der älteste). Felder, die nur eine Dublette hat (z. B. `project_id`, `due_date`), werden vor dem Löschen auf den Überlebenden übertragen.

**B) Ableitbar erledigte Einträge.** Für jeden offenen Eintrag: Suche in Meetings mit `meeting_date` NACH dem Beleg-Datum des Eintrags (dessen Meeting-Datum, sonst `created_at`) nach Abschluss-Belegen — **in zwei Tiefen**:
1. **Summaries:** Sätze in `executive_summary`, `ai_summary` oder `meeting_topics.summary`, in denen ein **markanter Titelbegriff des Eintrags im selben Satz** wie ein Abschluss-Marker steht (erledigt, abgeschlossen, fertiggestellt, gelöst, geklärt, umgesetzt, validiert, freigegeben, entfallen, obsolet, nicht mehr relevant). → Konfidenz hoch.
2. **Transkript-Chunks:** Abschluss-Aussagen fallen oft der Summary-Kompression zum Opfer. Nutze die bestehende Hybrid-Suche über `transcript_chunks` (RPC `hybrid_search_chunks` bzw. `hybrid_search_chunks_smart` mit `min_meeting_date` = Beleg-Datum des Eintrags, Query = markante Titelbegriffe) und prüfe die Treffer-Chunks auf Abschluss-Aussagen zum Eintrag. Achtung gesprochene Sprache: Konjunktive („wäre erledigt, wenn …“), Bedingungen und Absichtserklärungen sind KEIN Abschluss. → Konfidenz mittel; solche Treffer kommen in der Inventur in eine eigene Spalte `beleg_quelle = chunk`.

Generische Wörter (Bericht, klären, offen …) zählen nicht als markant. Nur eindeutige Treffer übernehmen; Grenzfälle in die „unsicher“-Liste. Im Beleg-Feld der Inventur immer das wörtliche Zitat samt Quelle (Summary vs. Chunk + Meeting-Datum) angeben. Reine Chunk-Treffer mittlerer Konfidenz werden in Phase 2 NUR umgesetzt, wenn der Nutzer die Inventur freigegeben hat — im Zweifel „unsicher“.

**Präzisionsregeln für die Chunk-Suche** (Pflicht — das Projektvokabular wie „Berechtigungskonzept“, „Reporting“, „Datasphere“ kommt in fast jedem Meeting vor, Einzelbegriff-Matches sind Rauschen):
- **Seltenheit statt Vorkommen:** Bestimme die Dokumentfrequenz der Titelbegriffe über den Chunk-Bestand (einmalige SQL-Aggregation, keine hartkodierte Liste). Begriffe, die in einem großen Teil der Meetings vorkommen, gelten als nicht-markant. Ein Eintrag qualifiziert sich für die Chunk-Suche nur, wenn er **mindestens zwei markante (seltene) Tokens** hat; sonst bleibt es bei der Summary-Prüfung.
- **Ko-Okkurrenz gefordert:** Ein Chunk zählt nur als Kandidat, wenn mehrere markante Tokens des Eintrags darin gemeinsam auftreten — nicht bei einem Einzeltreffer.
- **Aggregiert bewerten, nicht per Einzel-Chunk:** Das Urteil „erledigt“ stützt sich auf das Gesamtbild der Treffer-Chunks eines Meetings (idealerweise mehrere übereinstimmende Stellen oder ein Treffer, der zusätzlich zur Summary passt). Ein einzelner langer Chunk mit zufälliger Begriffsdichte ist kein Beleg.
- **Effizienz:** Nutze die bestehenden RPCs (`hybrid_search_chunks*` mit `match_count`-Limit) statt eigener LIKE-Scans über die ganze Tabelle; pro Eintrag hart gedeckelte Kandidatenzahl (~10 Chunks).

**Ausgabeformat der Inventur** (als Markdown-Tabellen im Chat, zusätzlich als Datei speichern):
- Dubletten: Gruppe, Tabelle, Überlebender (id, Titel), zu löschende ids, zu übernehmende Felder
- Erledigt: Tabelle, id, Titel, Beleg (Meeting-Datum + wörtliches Zitat des Satzes), Ziel-Status
- Unsicher: dieselben Spalten + warum unsicher (NICHT anfassen)
- Summenzeile: X Dubletten löschen, Y als erledigt markieren, Z unsicher

### Phase 2 — Bereinigung (erst nach vollständig vorgelegter Inventur)

1. **Dubletten:** Felder auf den Überlebenden mergen, dann Dubletten per SQL `DELETE` entfernen — ohne `activity_log`-Einträge. Bestehende `activity_log`-Zeilen, deren `entity_id` zu einer gelöschten Dublette gehört, ebenfalls löschen (verwaiste Protokoll-Einträge vermeiden).
2. **Erledigte:** Status setzen, damit der Nightly-Job sie bereinigt:
   - `todos` → `status='done'`, `completed_at` = Datum des Beleg-Meetings
   - `blockers` → `status='resolved'`, `resolved_at` = Datum des Beleg-Meetings, `resolution_note` = kurzer Verweis „lt. Meeting vom <Datum>: <Zitat-Kurzform>“
   - `open_items` → `status='closed'`, `closed_at` = Datum des Beleg-Meetings
   (Falls Phase 0 ergab, dass `nightly_archive_completed()` andere Kriterien nutzt, passe dich denen an.)
3. **Verifikation:** Zähle vorher/nachher je Tabelle (gesamt + offen), prüfe stichprobenartig 5 Mutationen gegen das Backup, und bestätige, dass keine neuen `activity_log`-Einträge durch die Bereinigung entstanden sind.

## Leitplanken

- Nichts anfassen, was auf der „unsicher“-Liste steht — lieber zu konservativ als falsch.
- Keine Einträge löschen, die als erledigt ableitbar sind: Erledigt wird MARKIERT (Punkt 2), nur echte Dubletten werden GELÖSCHT.
- Einträge mit finalem Status (`done`, `resolved`, `closed`, `cancelled`) bleiben unangetastet.
- Alle SQL-Mutationen idempotent formulieren (per expliziten id-Listen aus der Inventur, keine breiten UPDATE/DELETE mit Textbedingungen).
- Abschlussreport: was gelöscht, was markiert, was übrig, wo die Backups liegen, und der Hinweis, dass der Nightly-Job um 22:00 die markierten Einträge wegräumt.
