# Inventur-Ledger — Dashboard Job

- Projekt-ref: `lghwikeotbkmojyyjglz`
- Lauf gestartet: `2026-06-27T17:27:35+02:00`
- Modus: strikt read-only gegen Live-DB/Cloud; lokale Schreibzugriffe ausschließlich für dieses Ledger und den Abschlussbericht

## Schritt 0 — Zugang

### 0A Live-DB — PASS

Befehl/Quelle: Supabase MCP `execute_sql`, Projekt `lghwikeotbkmojyyjglz`, `SELECT 1 AS access_ok;`

Rohe Evidenz:

```json
[{"access_ok":1}]
```

### 0B Deployter Edge-Function-Quellcode — PASS

Befehl/Quelle: Supabase MCP `list_edge_functions`, Projekt `lghwikeotbkmojyyjglz`.

Rohe Evidenz (beweisender Auszug):

```json
{"functions":[{"slug":"generate-embedding","version":7},{"slug":"semantic-search","version":51},{"slug":"backfill-embeddings","version":6},{"slug":"ingest-transcript","version":5},{"slug":"extract-structured-data","version":2},{"slug":"enrich-chunks","version":1},{"slug":"run-eval","version":16},{"slug":"semantic-search-v2","version":2}]}
```

### 0C Lokales Git-Repo — BLOCKED

Befehl/Quelle: lokales Dateisystem, `git rev-parse --show-toplevel` im Workspace; anschließend begrenzte Suche nach `.git` bis vier Ebenen oberhalb.

Rohe Evidenz:

```text
fatal: not a git repository (or any of the parent directories): .git
```

Die Suche fand kein `.git`. `supabase/functions` ist lokal vorhanden, aber ohne Git-Herkunft. Gemäß Stop-Gate wird G2 als BLOCKED geführt; Abwesenheit eines Repos ist kein Beleg für Driftfreiheit.

## Check-Status

| Check | Status |
|---|---|
| A1 Tabellen-Counts + Datenrückstand | PASS |
| A2 Belegkette leer? | FINDING |
| A3 Waisen (FK-Integrität) | PASS |
| B1 Embedding-Abdeckung | PASS |
| B2 Embedding-Dimension | PASS |
| B3 Granularität | FINDING |
| C1 HNSW | PASS |
| C2 Extensions | PASS |
| D1 Warm-Ping-Cron | PASS |
| D2 Extraktions-Trigger | PASS |
| D3 Letzte Ingest-Aktivität | BLOCKED |
| E1 Kern-RPCs | DRIFT |
| E2 FTS-Smoke | FINDING |
| F1 RLS-Status | FINDING |
| G1 Live-Versionen | PASS |
| G2 Cloud-vs-Lokal | BLOCKED |
| G3a run-eval Ziel-URL | FINDING |
| G3b judgeAnswer | PASS |
| G3c Intent-Aliase | PASS |
| G3d mini_eval-Batchgröße | FINDING |
| G4 v1-v2-Quelldiff | DRIFT |
| H1 Goldfelder-Abdeckung | PASS |
| H2a Q20 Rollout-Goldlabel | FINDING |
| H2b Expected-Source-IDs | FINDING |
| H3 Letzte Eval-Läufe | FINDING |
| I1 Deno-Check | FINDING |

## Evidenz je Check

### A1 — PASS

Query/Quelle: Live-DB, die in `INVENTUR_AGENT.md` angegebene Single-Pass-Count-/Lag-Query.

```json
[{"meetings":83,"latest_meeting":"2026-05-22 00:00:00+00","chunks":1447,"embeddings":405,"open_items":209,"todos":86,"blockers":27,"decisions":245,"commitments":182,"today":"2026-06-27","lag_days":36}]
```

Alle Referenzmengen und der Referenzrückstand von 36 Tagen stimmen überein.

### A2 — FINDING

Query/Quelle: Live-DB, NULL-Zählung für `evidence_chunk_id`.

```json
[{"dec_null":245,"com_null":182}]
```

Damit fehlt bei allen 245 Decisions und allen 182 Commitments die Chunk-Belegkette. EMPFEHLUNG: Evidenzzuordnung separat konzipieren und backfillen; in diesem Lauf keine Änderung.

### A3 — PASS

Query/Quelle: Live-DB, LEFT-JOIN-Waisenzählung aus der Checkliste.

```json
[{"t":"open_items","count":0},{"t":"todos","count":0},{"t":"blockers","count":0},{"t":"decisions","count":0},{"t":"commitments","count":0}]
```

### B1 — PASS

Query/Quelle: Live-DB, Embedding-Abdeckung nach `entity_type`.

```json
[{"entity_type":"blocker","rows":27,"with_vec":27,"missing_vec":0},{"entity_type":"meeting","rows":83,"with_vec":83,"missing_vec":0},{"entity_type":"open_item","rows":209,"with_vec":209,"missing_vec":0},{"entity_type":"todo","rows":86,"with_vec":86,"missing_vec":0}]
```

### B2 — PASS

Query/Quelle: Live-DB, `vector_dims` nach Entity-Typ.

```json
[{"entity_type":"blocker","mn":1536,"mx":1536},{"entity_type":"meeting","mn":1536,"mx":1536},{"entity_type":"open_item","mn":1536,"mx":1536},{"entity_type":"todo","mn":1536,"mx":1536}]
```

### B3 — FINDING

Query/Quelle: Live-DB, Chunk-Abdeckung/-Länge; ergänzend Aggregat zu Chunks pro Meeting und Inhalt der Meeting-Vektoren.

```json
[{"chunks":1447,"chunks_with_vec":1447,"avg_len":"2853"}]
[{"avg_chunks_per_meeting":"17.43","meeting_vectors":83,"distinct_meetings_vectorized":83,"avg_meeting_embedding_chars":"5202"}]
```

Die bekannte Grobkörnigkeit ist bestätigt: zusätzlich zu granularen, vollständig vektorisierten Chunks existiert genau ein Meeting-Vektor pro Meeting über durchschnittlich 5.202 Zeichen. EMPFEHLUNG: Retrieval-Auswirkungen der Meeting-Grobkörnigkeit separat mit einem echten Query-Embedding evaluieren; keine Änderung in diesem Lauf.

### C1 — PASS

Query/Quelle: Live-DB, `pg_indexes` für HNSW auf `embeddings` und `transcript_chunks`.

```json
[{"tablename":"embeddings","indexname":"embeddings_embedding_hnsw","indexdef":"CREATE INDEX embeddings_embedding_hnsw ON public.embeddings USING hnsw (embedding vector_cosine_ops)"},{"tablename":"transcript_chunks","indexname":"idx_transcript_chunks_vector","indexdef":"CREATE INDEX idx_transcript_chunks_vector ON public.transcript_chunks USING hnsw (embedding vector_cosine_ops) WITH (m='16', ef_construction='64')"}]
```

### C2 — PASS

Query/Quelle: Live-DB, `pg_extension`.

```json
[{"extname":"pg_cron","extversion":"1.6.4"},{"extname":"pg_net","extversion":"0.20.0"},{"extname":"pg_trgm","extversion":"1.6"},{"extname":"vector","extversion":"0.8.0"}]
```

### D1 — PASS

Query/Quelle: Live-DB, `cron.job`.

```json
[{"jobid":5,"jobname":"nightly-archive","schedule":"0 22 * * *","active":true},{"jobid":6,"jobname":"keep-semantic-search-warm","schedule":"*/4 * * * *","active":true}]
```

Der 4-Minuten-Warm-Ping ist aktiv.

### D2 — PASS

Query/Quelle: Live-DB, nicht-interne Trigger auf `meetings`.

```json
[{"tgname":"trg_meetings_created","table":"meetings","tgenabled":"O"},{"tgname":"trg_meetings_created_at","table":"meetings","tgenabled":"O"},{"tgname":"trg_meetings_embedding","table":"meetings","tgenabled":"O"},{"tgname":"embed_meeting","table":"meetings","tgenabled":"O"},{"tgname":"on_meeting_created_ingest_transcript","table":"meetings","tgenabled":"O"},{"tgname":"trg_meetings_tsv","table":"meetings","tgenabled":"O"},{"tgname":"on_meeting_insert_extract","table":"meetings","tgenabled":"O"}]
```

Alle gelisteten Trigger sind aktiv (`O`). Das belegt nicht, dass neue Meetings eingehen oder die Pipeline erfolgreich endet.

### D3 — BLOCKED

Befehl/Quelle: Supabase MCP `get_logs`, Service `edge-function` (Werkzeugfenster: letzte 24 Stunden); Rückgabe programmatisch auf `ingest-transcript` gefiltert.

```json
{"returned_rows":100,"ingest_rows":0,"first_returned":{"event_message":"POST | 200 | https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/semantic-search","timestamp":1782574080302000},"last_returned":{"event_message":"POST | 200 | https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/semantic-search","timestamp":1782548880866000}}
```

Die 100 verfügbaren, durch Warm-Pings dominierten Logzeilen enthalten keinen Ingest. Das Werkzeug liefert nur das letzte 24-Stunden-Fenster und keine historische letzte erfolgreiche Invocation; daher keine Aussage über den letzten Ingest-Zeitpunkt.

### E1 — DRIFT

Query/Quelle: Live-DB, `pg_proc` + `pg_get_function_arguments`.

```json
[{"proname":"hybrid_search_chunks","args":"query_text text, query_embedding vector DEFAULT NULL::vector, match_count integer DEFAULT 20, rrf_k integer DEFAULT 50, candidate_n integer DEFAULT 80"},{"proname":"keyword_search","args":"search_query text, result_limit integer DEFAULT 20"},{"proname":"match_embeddings","args":"query_embedding vector, match_threshold double precision, match_count integer, filter_entity_type text DEFAULT NULL::text"},{"proname":"match_transcript_chunks","args":"query_embedding vector, match_threshold double precision DEFAULT 0.6, match_count integer DEFAULT 5, filter_meeting_id uuid DEFAULT NULL::uuid"}]
```

Alle vier Kern-RPCs existieren. Der live von PostgreSQL ausgegebene Typ für `hybrid_search_chunks.query_embedding` ist `vector`, während die Referenz `vector(1536)` nennt; deshalb formaler Signatur-DRIFT. Keine Behauptung, dass dies einen Laufzeitfehler verursacht.

### E2 — FINDING

Query/Quelle: Live-DB, FTS-only-Aufruf `hybrid_search_chunks('Plankosten Buchungskreis 8003')`, anschließend read-only Titelauflösung.

```json
[{"meeting_id":"60abf158-96ad-4bc2-9c70-1165505bc702","hits":4},{"meeting_id":"c36fbed9-c752-451a-9d0f-3f053fe885d8","hits":2},{"meeting_id":"4b9e0b0f-6b08-4ddc-99df-2e209a586dd2","hits":2},{"meeting_id":"8b103e0b-1caf-405e-bead-543eb0e0c5e5","hits":2},{"meeting_id":"3a54a166-5857-47f7-a07c-56e9725e1801","hits":1}]
[{"id":"60abf158-96ad-4bc2-9c70-1165505bc702","title":"Abstimmung zu Buchungskreis-Mapping und Kostenstellen-Anlegung"},{"id":"3a54a166-5857-47f7-a07c-56e9725e1801","title":"Plankosten und Anpassungskosten im Buchungskreis 8003"}]
```

Der FTS-Pfad liefert Ergebnisse, aber das Meeting mit dem direkt passenden Titel steht anhand der vorgegebenen `hits`-Sortierung auf Rang 5 statt oben. EMPFEHLUNG: FTS-Ranking für exakte Titel-/Termtreffer untersuchen. Der Vektor-Zweig wurde mangels echten Query-Embeddings nicht getestet.

### F1 — FINDING (Sicherheit)

Query/Quelle: Live-DB, `pg_class.relrowsecurity` für alle öffentlichen Tabellen.

```json
[{"relname":"commitments","rls_enabled":false},{"relname":"decisions","rls_enabled":false},{"relname":"embeddings","rls_enabled":false},{"relname":"eval_questions","rls_enabled":false},{"relname":"eval_results","rls_enabled":false},{"relname":"eval_runs","rls_enabled":false},{"relname":"open_loops","rls_enabled":false},{"relname":"project_meetings","rls_enabled":false},{"relname":"activity_log","rls_enabled":true},{"relname":"blockers","rls_enabled":true},{"relname":"inbox_items","rls_enabled":true},{"relname":"meeting_topics","rls_enabled":true},{"relname":"meetings","rls_enabled":true},{"relname":"open_items","rls_enabled":true},{"relname":"projects","rls_enabled":true},{"relname":"team_members","rls_enabled":true},{"relname":"todos","rls_enabled":true},{"relname":"transcript_chunks","rls_enabled":true}]
```

Acht öffentliche Tabellen haben RLS deaktiviert. EMPFEHLUNG: Zugriffsmodell, Data-API-Exposition und Policies tabellenweise prüfen, bevor RLS in einem separaten Change aktiviert wird; keine Aktivierung in diesem Lauf.

### G1 — PASS

Befehl/Quelle: Supabase MCP `list_edge_functions`, Projekt `lghwikeotbkmojyyjglz`.

```json
[{"slug":"generate-embedding","version":7,"status":"ACTIVE"},{"slug":"semantic-search","version":51,"status":"ACTIVE"},{"slug":"backfill-embeddings","version":6,"status":"ACTIVE"},{"slug":"ingest-transcript","version":5,"status":"ACTIVE"},{"slug":"extract-structured-data","version":2,"status":"ACTIVE"},{"slug":"enrich-chunks","version":1,"status":"ACTIVE"},{"slug":"run-eval","version":16,"status":"ACTIVE"},{"slug":"semantic-search-v2","version":2,"status":"ACTIVE"}]
```

Alle Referenzversionen stimmen überein.

### G2 — BLOCKED

Befehl/Quelle: lokaler Zugangstest aus Schritt 0C.

```text
fatal: not a git repository (or any of the parent directories): .git
```

Ohne Git-Repo ist der geforderte Cloud-vs-Lokal-Drift-Check gemäß Stop-Gate nicht belastbar. Die vorhandene unversionierte `supabase/functions`-Momentaufnahme wird nicht als Drift-Wahrheit ausgegeben.

### G3a — FINDING

Befehl/Quelle: Supabase MCP `get_edge_function(run-eval)`, deployte Version 16, `run-eval/index.ts`.

```text
86:   const SEARCH_URL = `${SUPABASE_URL}/functions/v1/semantic-search`;
```

`run-eval` adressiert fest v1. Damit können als v2 bezeichnete Evals weiterhin v1 messen. EMPFEHLUNG: Zielversion in einem separaten Change explizit parametrieren und im Lauf persistieren; nicht in dieser Inventur ändern.

### G3b — PASS

Befehl/Quelle: deployter `run-eval`-v16-Quellcode.

```text
40: async function judgeAnswer(
165:       const judged = await judgeAnswer(
```

Der Judge-Helper ist vorhanden und wird im Fragenloop aufgerufen.

### G3c — PASS

Befehl/Quelle: deployter `run-eval`-v16-Quellcode.

```text
16: const EXPECTED_INTENT_ALIASES: Record<string, string> = {
17:   meeting_list: "latest_entities",
18:   meeting_summary: "summarize_notes",
19:   person_profile: "person_status_query",
```

Die drei veralteten Aliase `decision_history`, `open_items` und `status_check` sind nicht enthalten.

### G3d — FINDING

Befehl/Quelle: deployter `run-eval`-v16-Quellcode; statische Prüfung, Eval nicht gestartet.

```text
14: const MINI_EVAL_QUESTION_IDS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 18, 19, 20];
```

Die statische Batchgröße beträgt 14. Zusammen mit der Handover-Referenz von ca. 14–16 Sekunden pro Frage besteht ein rechnerisches Wall-Clock-Risiko von ca. 196–224 Sekunden (>150 Sekunden). Dies ist eine Risikoableitung, keine gemessene Laufzeit. EMPFEHLUNG: Batch verkleinern oder Eval-Ausführung asynchronisieren; hier nicht ausführen.

### G4 — DRIFT

Befehl/Quelle: deployte Quellen von `semantic-search` v51 und `semantic-search-v2` v2, byteweiser Inhaltsvergleich nach relativem Dateinamen plus statische Zeilensuche.

```text
DIFF_FILES ["context_builder.ts","index.ts","ranking.ts"]
index.ts:77: async function rollupChunksToMeetings(
index.ts:586:       chunkMeetingResults = await rollupChunksToMeetings(sb, intent.semantic_query || query, null);
ranking.ts:211:   if (sourceName === "chunk_meeting") return 1.3;

V1 context_builder.ts:
11:   open_items:          { fullDetail: 35, compact: 15 },
12:   default:             { fullDetail: 10, compact: 20 },

V2 context_builder.ts:
11:   open_items:          { fullDetail: 35, compact: 15 },
12:   // v2: topic/semantic brauchen breite Themenabdeckung über mehrere Meetings.
13:   // Sonst landen gerollte Meeting-Kandidaten im Kompakt-Block (120 Zeichen)
14:   // und verlieren Inhalt (z.B. "S/4HANA").
15:   topic_query:         { fullDetail: 25, compact: 20 },
16:   semantic_search:     { fullDetail: 25, compact: 20 },
17:   default:             { fullDetail: 10, compact: 20 },
```

Rollup, Gewicht 1,3 und FTS-only-Aufruf (`null`) sind bestätigt. Die Referenzaussage „nur `index.ts` + `ranking.ts` verschieden“ ist jedoch falsch: auch `context_builder.ts` unterscheidet sich; daher DRIFT.

### H1 — PASS

Query/Quelle: Live-DB, Goldfelder-Abdeckung in `eval_questions`.

```json
[{"total":20,"has_answer":20,"has_source_ids":10}]
```

### H2a — FINDING

Query/Quelle: Live-DB, `open_items`-Suche nach „Rollout“ und Q20-Goldfeld.

```json
[{"count":0}]
[{"id":20,"question":"Was sind die wichtigsten offenen Punkte?","expected_answer":"Nennt die wichtigsten offenen Punkte (Plankosten, Rollout, Kennzahlen).","expected_source_ids":[]}]
```

Q20 fordert „Rollout“, obwohl der Begriff in Titel/Beschreibung der echten `open_items` nicht vorkommt. EMPFEHLUNG: Goldantwort gegen Live-Daten neu kuratieren.

### H2b — FINDING

Query/Quelle: Live-DB, `expected_source_ids` gegen `meetings`. Die Checklisten-Query schlug wegen `uuid = text` fehl; die read-only Wiederholung verglich deshalb `m.id::text = ex.sid`.

```text
ERROR: operator does not exist: uuid = text
LINE 7: FROM ex LEFT JOIN meetings m ON m.id = ex.sid
```

```json
[{"expected_ids":39,"dead_ids":5}]
[{"qid":1,"sid":"1b36c99a-4b59-4aed-b7a4-ab3e0ad12657","exists_in_meetings":false},{"qid":1,"sid":"6babee79-1ba2-43c3-8298-fe19e9b348da","exists_in_meetings":false},{"qid":1,"sid":"da914e73-06f9-41fb-a44e-fd805d3e358c","exists_in_meetings":false},{"qid":1,"sid":"f115836d-118f-4810-873c-10f8596aac51","exists_in_meetings":false},{"qid":1,"sid":"f2e6ddc1-53a4-4f32-b8da-80669d69e2e4","exists_in_meetings":false}]
```

Fünf von 39 erwarteten IDs sind tot, sämtlich bei Q1. EMPFEHLUNG: Q1-Quellen gegen reale Meeting-IDs neu labeln. Die Referenzangabe „28 IDs“ ist ebenfalls nicht mehr aktuell (live: 39).

### H3 — FINDING

Query/Quelle: Live-DB, letzte sechs `eval_runs`. Die Referenzquery schlug fehl; live heißen die Spalten `run_at` und `semantic_search_version`, die zweite Query aliasierte sie read-only.

```text
ERROR: column "created_at" does not exist
```

```json
[{"id":"6af06d3b-56eb-478f-a284-648c556858af","created_at":"2026-06-02 17:52:52.452098","target_version":null,"avg_judge_score":"1","source_hit_rate":null,"intent_accuracy":1,"must_include_hit_rate":0.222222222222222},{"id":"ccd925f2-895c-4207-b150-7806b72cf945","created_at":"2026-06-02 17:51:50.271432","target_version":null,"avg_judge_score":"2","source_hit_rate":0,"intent_accuracy":1,"must_include_hit_rate":0.444444444444444},{"id":"da807138-5d6c-43f7-984f-ae6c03ba2612","created_at":"2026-06-02 17:50:15.321008","target_version":null,"avg_judge_score":"2.25","source_hit_rate":0.5,"intent_accuracy":1,"must_include_hit_rate":0.833333333333333},{"id":"0848cdc6-febf-4ff4-9e14-29df0c4aa6d3","created_at":"2026-06-02 17:48:43.583178","target_version":null,"avg_judge_score":"2.25","source_hit_rate":0,"intent_accuracy":1,"must_include_hit_rate":0.4375},{"id":"7777cca4-7984-454b-94be-28cf8f2dfcea","created_at":"2026-06-02 17:46:28.776981","target_version":null,"avg_judge_score":"2.5","source_hit_rate":0.25,"intent_accuracy":1,"must_include_hit_rate":0.666666666666667},{"id":"cc935301-9eb9-4f5a-81fb-201e05549fee","created_at":"2026-06-02 17:44:42.434807","target_version":null,"avg_judge_score":"1.6666666666666667","source_hit_rate":null,"intent_accuracy":1,"must_include_hit_rate":0.333333333333333}]
```

Alle sechs letzten Läufe haben `target_version=null`; eine v1/v2-Zuordnung ist damit nicht belegt. EMPFEHLUNG: Zielversion bei künftigen, separat autorisierten Läufen verlässlich persistieren. Keine Aussage, dass v2 besser sei; der Judge ist ungeeicht.

### I1 — FINDING

Befehl/Quelle: lokale unversionierte Momentaufnahme, `rg --files supabase/functions -g '*.ts' -0 | sort -z | xargs -0 deno check`, Deno 2.8.1. Keine Datei geändert.

```text
TS18046 [ERROR]: 'err' is of type 'unknown'.
    at .../supabase/functions/backfill-embeddings/index.ts:92:49
TS18046 [ERROR]: 'err' is of type 'unknown'.
    at .../supabase/functions/generate-embedding/index.ts:167:49
TS2367 [ERROR]: ... and '"count_query"' have no overlap.
    at .../supabase/functions/semantic-search-v2/index.ts:421:7
TS2367 [ERROR]: ... and '"source_audit"' have no overlap.
    at .../supabase/functions/semantic-search-v2/index.ts:422:7
TS2367 [ERROR]: ... and '"count_query"' have no overlap.
    at .../supabase/functions/semantic-search-v2/index.ts:459:44
TS2367 [ERROR]: ... and '"source_audit"' have no overlap.
    at .../supabase/functions/semantic-search-v2/index.ts:459:79
TS2322 [ERROR]: Type ... is not assignable to type 'ScoredResult[]'.
    at .../supabase/functions/semantic-search-v2/index.ts:467:17
TS2367 [ERROR]: ... and '"count_query"' have no overlap.
    at .../supabase/functions/semantic-search/index.ts:358:7
TS2367 [ERROR]: ... and '"source_audit"' have no overlap.
    at .../supabase/functions/semantic-search/index.ts:359:7
TS2367 [ERROR]: ... and '"count_query"' have no overlap.
    at .../supabase/functions/semantic-search/index.ts:396:44
TS2367 [ERROR]: ... and '"source_audit"' have no overlap.
    at .../supabase/functions/semantic-search/index.ts:396:79
TS2322 [ERROR]: Type ... is not assignable to type 'ScoredResult[]'.
    at .../supabase/functions/semantic-search/index.ts:404:17
Found 12 errors.
```

Gegenprüfung der realen Dateien:

```text
semantic-search/retrieval_planner.ts
33 | "count_query"
34 | "source_audit"
semantic-search-v2/retrieval_planner.ts
33 | "count_query"
34 | "source_audit"
```

Live in dieser lokalen Momentaufnahme sind 12 statt der referenzierten 5 Fehler vorhanden: acht TS2367, zwei TS2322 und zwei TS18046. `IntentClass` enthält `count_query`/`source_audit` tatsächlich; eine darüber hinausgehende Ursache wird nicht behauptet. EMPFEHLUNG: zuerst das echte Git-Repo bereitstellen/identifizieren, dann die 12 Fehler gegen dessen HEAD triagieren.
