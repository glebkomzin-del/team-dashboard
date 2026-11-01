# Inventurbericht — Dashboard Job

## 1. Kopf

- Projekt-ref: `lghwikeotbkmojyyjglz` („Dashboard Job“)
- Inventurzeitraum: `2026-06-27T17:27:35+02:00` bis `2026-06-27T17:39:01+02:00`
- Live-DB lesen: **verfügbar** (`SELECT 1` → `[{"access_ok":1}]`)
- Deployte Edge-Function-Quellen lesen: **verfügbar**
- Lokales Git-Repo: **nicht verfügbar** (`fatal: not a git repository`)
- Modus: read-only gegen DB und Cloud. Kein Deploy, keine Migration, kein DML, keine Trigger-/Cron-/RLS-Änderung und kein `run-eval`-Aufruf. Im Workspace wurden nur dieses Report-Artefakt und das Evidenz-Ledger geschrieben.

Vollständige Rohbelege und exakte Quellen stehen in `INVENTUR_LEDGER.md`.

## 2. Zählung

| Status | Anzahl |
|---|---:|
| PASS | 12 |
| DRIFT | 2 |
| FINDING | 10 |
| BLOCKED | 2 |
| **Gesamt** | **26** |

## 3. Drift-Tabelle

| Check | Referenz 27.06.2026 | Live / gemessen |
|---|---|---|
| E1 RPC-Signatur | `query_embedding vector(1536)` | PostgreSQL gibt `query_embedding vector DEFAULT NULL::vector` aus. Alle vier RPCs existieren. |
| G4 v1-v2-Dateidiff | Nur `index.ts` und `ranking.ts` verschieden | Drei Dateien verschieden: `index.ts`, `ranking.ts`, **`context_builder.ts`**. Rollup, Gewicht 1,3 und FTS-only-`null` sind bestätigt. |
| H2b Goldquellen-Menge | etwa 5 tote IDs von 28 | 5 tote IDs von **39**, alle bei Q1. Primär als FINDING klassifiziert. |
| H3 Eval-Schema | `created_at`, `target_version` | Live heißen die Spalten `run_at`, `semantic_search_version`; die letzten sechs Versionswerte sind `null`. Primär als FINDING klassifiziert. |
| I1 Deno-Fehler | genau 5 TS2367-Fehler | 12 Fehler: 8× TS2367, 2× TS2322, 2× TS18046. Primär als FINDING klassifiziert. |

## 4. Findings, priorisiert

### Hoch — Sicherheit: RLS auf acht öffentlichen Tabellen aus

Beleg: `commitments`, `decisions`, `embeddings`, `eval_questions`, `eval_results`, `eval_runs`, `open_loops`, `project_meetings` liefern `rls_enabled=false`.

EMPFEHLUNG: Data-API-Exposition und Rollenrechte prüfen und anschließend ein tabellenspezifisches Policy-Konzept erstellen. RLS nicht blind aktivieren, da dies die App brechen kann.

### Hoch — Eval-Runner misst fest v1

Beleg aus deploytem `run-eval` v16:

```text
86: const SEARCH_URL = `${SUPABASE_URL}/functions/v1/semantic-search`;
```

Damit können nominelle v2-Evals weiterhin v1 messen. EMPFEHLUNG: Zielendpoint explizit parametrieren/validieren und die tatsächlich verwendete Version persistieren.

### Hoch — Strukturierte Aussagen ohne Chunk-Belegkette

Beleg: `{"dec_null":245,"com_null":182}` — sämtliche Decisions und Commitments haben `evidence_chunk_id IS NULL`.

EMPFEHLUNG: Evidenzmodell und kontrollierten Backfill als separaten Change planen.

### Mittel — Eval-Instrument hat falsche und tote Goldlabels

- Q20 erwartet „Rollout“, aber `open_items` enthält in Titel/Beschreibung 0 Treffer.
- 5 von 39 `expected_source_ids` existieren nicht in `meetings`; alle gehören zu Q1.
- Die letzten sechs `eval_runs` haben `semantic_search_version=null`.

EMPFEHLUNG: Q1/Q20 gegen Live-Daten neu kuratieren und Zielversion obligatorisch mitschreiben. Judge-Werte erst nach Eichung vergleichend interpretieren.

### Mittel — Lokaler Deno-Check hat 12 Fehler

Beleg: `Found 12 errors.`; darunter 8× TS2367, 2× TS2322 und 2× TS18046. In beiden `retrieval_planner.ts` stehen `count_query` und `source_audit` real in Zeile 33–34.

EMPFEHLUNG: Zuerst das echte Git-Repo identifizieren, dann diese Fehler gegen dessen HEAD triagieren. Die unversionierte Momentaufnahme nicht ungeprüft ändern.

### Mittel — FTS-Smoke rankt den direkt passenden Titel nur auf Rang 5

Beleg: Für „Plankosten Buchungskreis 8003“ hat das Meeting `Plankosten und Anpassungskosten im Buchungskreis 8003` nur einen Hit und steht in der vorgegebenen Hit-Sortierung hinter vier Meetings.

EMPFEHLUNG: Gewichtung exakter Titel-/Termtreffer im FTS-Pfad untersuchen.

### Mittel — Meeting-Vektoren bleiben grobkörnig

Beleg: 83 Meeting-Vektoren für 83 Meetings, durchschnittlich 5.202 Zeichen je Vektor; parallel 1.447 vektorisierte Chunks und durchschnittlich 17,43 Chunks je Meeting.

EMPFEHLUNG: Retrieval-Auswirkungen mit echtem Query-Embedding separat evaluieren.

### Mittel — Mini-Eval kann das Wall-Clock-Budget reißen

Beleg: deployter v16-Code enthält 14 IDs im `MINI_EVAL_QUESTION_IDS`-Array. Mit der Handover-Annahme 14–16 Sekunden/Frage ergibt sich rechnerisch ca. 196–224 Sekunden.

EMPFEHLUNG: Batch verkleinern oder Eval-Ausführung asynchronisieren. Die Laufzeit wurde in dieser Inventur nicht gemessen.

## 5. „Eine Quelle der Wahrheit“-Urteil

**BLOCKED.** Der direkte Cloud-vs-Lokal-Vergleich ist nicht belastbar, weil im bereitgestellten Workspace und der begrenzten Umgebungssuche kein `.git` gefunden wurde. Eine unversionierte lokale `supabase/functions`-Momentaufnahme existiert, ersetzt aber kein Repo/HEAD.

Damit ist weder „kein Cloud-vs-Lokal-Drift“ noch eine konkrete betroffene lokale Funktion belegt. Innerhalb der Cloud ist dagegen belegt, dass v1 und v2 in drei Dateien differieren (`index.ts`, `ranking.ts`, `context_builder.ts`).

## 6. Blocked-Liste

| Check | Blocker |
|---|---|
| D3 Letzte erfolgreiche Ingest-Aktivität | Edge-Function-Logs liefern nur das letzte 24-Stunden-Fenster und 100 durch Warm-Pings dominierte Einträge; darin 0 `ingest-transcript`. Historischer letzter Erfolg nicht bestimmbar. |
| G2 Cloud-vs-Lokal-Diff | Kein lokales Git-Repo/HEAD verfügbar. |

## 7. Explizite Nicht-Aussagen

- Nicht belegt: dass der Vektor-Zweig oder v2-Rollup mit einem echten Query-Embedding funktioniert. Der verifizierte Rollup-Aufruf übergibt `null` und ist FTS-only.
- Nicht belegt: dass v2 qualitativ besser als v1 ist. `run-eval` hardcodiert v1, die letzten Zielversionen sind `null`, und der Judge ist ungeeicht.
- Nicht belegt: wann `ingest-transcript` zuletzt erfolgreich lief oder warum seit 22.05.2026 kein neueres Meeting vorhanden ist. Aktive Trigger beweisen keinen erfolgreichen End-to-End-Lauf.
- Nicht belegt: dass Cloud und lokaler Code synchron sind. Das Git-Repo fehlt.
- Nicht belegt: dass deaktiviertes RLS tatsächlich anonymen Datenzugriff erlaubt; Data-API-Exposition und Grants waren nicht Teil dieses Checks. Der RLS-Zustand selbst ist belegt.
- Nicht belegt: dass die 12 lokalen Typfehler im echten Repo-HEAD oder in den deployten Artefakten identisch vorliegen; die lokale Quelle ist unversioniert.
