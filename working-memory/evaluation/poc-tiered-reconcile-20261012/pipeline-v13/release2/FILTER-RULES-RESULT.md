# FILTER-RULES-RESULT · 2026-10-13 · lokal/offline

**Status: Teilnachweis; Originalrang-Rekonstruktion blockiert.** H = historischer Rangbericht; A = aktuelle Replay-Nachrechnung; F = Mengenfolgerung; n/b = nicht bestimmbar. Intervalle bei Kandidaten sind Grenzen, keine Messwerte.
Der angegebene Archivpfad ist nicht vorhanden (FileNotFoundError; tar -xzOf: Exit 1); scratchpad/codex-rank ist ebenfalls nicht vorhanden. Keine Ersatzränge aus Cosine/Lexikal-Scores.
36 Aufrufe / 32 Jobs; 12.223 Kandidatenvorkommen; 64 genutzt = 30 reine Lebenszyklusfälle + 34 Beobachtungsziele; Überschneidung 0 (A). 41 Zeilen: 40 gültig, 1 Fehler; 4 ohne Beobachtung / 67 Kandidaten ausgeschlossen. 4 Zwischenrunden ohne Ergebnisslots bleiben im Kandidatennenner.
Genutzt = vorhandener work_results[work_index] ≠ unchanged ODER update_target; fehlende Slots sind kein unchanged. Einheit: (Aufruf, Alias), keine global eindeutigen Aufgaben.
Alter = meeting_date − last_changed, jüngstes gespeichertes Aufgabenereignis; keine Erstellungsdaten. Kandidatenalter 0–133 Tage (A). Historisch 0 explizite echte Aufgaben-IDs; erneut nicht prüfbar (H).
Annahmen: Rang nullbasiert, unveränderte separate Work-Liste, Minimum über Beobachtungen; matter exakter nichtleerer Name, keine Kaskade; waiting in V3 unabhängig vom Alter; Frist = due_text ODER due_reference_date gesetzt, nur Fristzweig age ≤ 120.

| Regel | Recall gesamt | Lebenszyklus | Ziel | Behalten / Anteil | CP95 gesamt | Beleg |
|---|---:|---:|---:|---|---|---|
| V0 | 64/64 (100.00 %) | 30/30 (100.00 %) | 34/34 (100.00 %) | 6,002 (49.10 %) | 94.40–100.00 % | H |
| V1 | 64/64 (100.00 %) | 30/30 (100.00 %) | 34/34 (100.00 %) | 7,860–8,968 (64.30–73.37 %) | 94.40–100.00 % | H+A+F |
| V2 | 64/64 (100.00 %) | 30/30 (100.00 %) | 34/34 (100.00 %) | 6,002–12,223 (49.10–100.00 %) | 94.40–100.00 % | H+A+F |
| V3 | 64/64 (100.00 %) | 30/30 (100.00 %) | 34/34 (100.00 %) | 7,495–8,603 (61.32–70.38 %) | 94.40–100.00 % | H+A+F |
| V4 | 64/64 (100.00 %) | 30/30 (100.00 %) | 34/34 (100.00 %) | 7,495–12,223 (61.32–100.00 %) | 94.40–100.00 % | H+A+F |
| V5 | 63/64 (98.44 %) | 29/30 (96.67 %) | 34/34 (100.00 %) | 5,699–6,568 (46.63–53.73 %) | 91.60–99.96 % | H+F |
| V6 | 64/64 (100.00 %) | 30/30 (100.00 %) | 34/34 (100.00 %) | 6,547 (53.56 %) | 94.40–100.00 % | H |
| V7 | 53–56/64 (82.81–87.50 %) | 24–26/30 (80.00–86.67 %) | 29–30/34 (85.29–88.24 %) | 3,321–4,591 (27.17–37.56 %) | n/b; siehe unten | H+F |
V0 age30/rank5; V1 open/waiting age90, done age30; V2 V0 + nicht-done mit matter aus Beobachtung oder rank<5-Aufgabe; V3 V0 + waiting + Frist/age120; V4 V2+V3; V5 age14/rank10; V6 age30/rank8; V7 rank10 ohne Alter; jeweils explizite IDs.
V1–V4 sind Obermengen von V0. V5: age14/rank5 behält schon 63; der einzige weitere Fall hat Rang12/Alter25 und bleibt bei rank10 ausgeschlossen. V7: getrennte Grenzen aus rank8/rank12, nicht frei kombinierbare Split-Zähler.
CP95 V7 exakt n/b; für 53/64: 71.32–91.10 %; für 56/64: 76.85–94.45 %; mögliche Intervallhülle 71.32–94.45 %. Clopper–Pearson, zweiseitig α=0.05, Binomialinversion (Stdlib).
CP95 ist formal: wiederholte Aufgaben/Jobs und 36 Aufrufcluster; Unabhängigkeit nicht nachgewiesen. Kein kalibriertes Zukunftsintervall, keine Modellqualitätsabnahme.
Grenzen: |R5\A30| = 6002−4891 = 1111 (H). V1 Nicht-Rang-Basis 7858/62 genutzt, 2 genutzt außerhalb, 1 alter Rangfall innerhalb; V3 Basis 7494/63 genutzt, 1 außerhalb, 2 alte Rangfälle innerhalb (A+H).

**Statusanteile:** exakte Unionanteile n/b, außer waiting bei V3/V4 = 100 %. Folgende A-Werte sind garantierte Nicht-Rang-Mindestanteile, keine gemessenen gesamten Statusanteile.
| Regel | open (n=9346) | waiting (n=1301) | done (n=1576) |
|---|---:|---:|---:|
| V0 | ≥3748 (40.10 %) | ≥608 (46.73 %) | ≥535 (33.95 %) |
| V1 | ≥6352 (67.96 %) | ≥971 (74.63 %) | ≥535 (33.95 %) |
| V2 | ≥3748 (40.10 %) | ≥608 (46.73 %) | ≥535 (33.95 %) |
| V3 | ≥5250 (56.17 %) | =1301 (100.00 %) | ≥943 (59.84 %) |
| V4 | ≥5250 (56.17 %) | =1301 (100.00 %) | ≥943 (59.84 %) |
| V5 | ≥2692 (28.80 %) | ≥425 (32.67 %) | ≥454 (28.81 %) |
| V6 | ≥3748 (40.10 %) | ≥608 (46.73 %) | ≥535 (33.95 %) |
| V7 | n/b | n/b | n/b |
V2 direkte Beobachtungs-matter-Erweiterung: 0 zusätzliche Kandidaten; 716/716 Beobachtungen mit matter (A). Erweiterung über matter der Rangtreffer n/b. Fristfelder gesetzt: 3902 Kandidaten / 24 genutzt; davon 326 Kandidaten age>120 (A). Genutzt nach Status: open61 / waiting3 / done0.

| Altersperzentil der 64 genutzten (A; R7 linear interpoliert) | min | P25 | P50 | P75 | P90 | P95 | P99 | max |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tage | 0 | 1 | 3.5 | 8 | 15.4 | 24.55 | 99 | 99 |
| V0-Behalteweg (H+A+F) | gesamt / 64 | Lebenszyklus / 30 | Ziel / 34 |
|---|---:|---:|---:|
| nur Alter ≤30 | 14 (21.88 %) | 9 (30.00 %) | 5 (14.71 %) |
| nur Rang <5 | 3 (4.69 %) | 2 (6.67 %) | 1 (2.94 %) |
| Alter und Rang | 47 (73.44 %) | 19 (63.33 %) | 28 (82.35 %) |
| nur explizite ID / kein Weg | 0 / 0 | 0 / 0 | 0 / 0 |
Alter>30 und nur über Suche gefunden: 3/64 (4.69 %), davon Lebenszyklus2 / Ziel1; 3/3 alte genutzte (H+A+F):
| Job-Alias / Aufrufindex | Aufgabenalias | Alter | Status | Kategorie | Rang |
|---|---|---:|---|---|---|
| 6856cff5 / 51 | W174 | 99 | open | Lebenszyklus | <5 (H), exakt n/b |
| 6856cff5 / 51 | W341 | 99 | waiting | Lebenszyklus | 4 (H) |
| 85f9e46f / 76 | W263 | 73 | open | Ziel | <5 (H), exakt n/b |

| Verpasste Fälle | Job-Alias / Aufrufindex | Aufgabenalias | Alter | Status | Rang | Kategorie |
|---|---|---|---:|---|---|---|
| V5 und V7 | 4e7b6e03 / 54 | W349 | 25 | open | 12 (H) | Lebenszyklus |
| V0–V4, V6 | 0 Fälle (H/F) | — | — | — | — | — |
| V7 weitere | 7–10 Fälle; Identitäten n/b | n/b | n/b | n/b | n/b | Split n/b |

**Minimum bei 64/64:** V0, 6002/12223 = 49.10 % behalten / 50.90 % Ersparnis (H). V2 könnte gleichziehen; kein belegter kleinerer 64/64-Kandidat. V1 ≥64.30 %, V3/V4 ≥61.32 % behalten; deutlich geringere Ersparnis.
**Risiko/Ersparnis:** V6 als plausible Robustheitswahl, 53.56 % behalten / 46.44 % Ersparnis; +545 Kandidaten gegenüber V0. Rang allein deckt 53/64 statt 50/64 ab, Lebenszyklus24/30 statt21/30, Ziel29/34 unverändert (H). Empirisch geringeres Verlustrisiko gegenüber V0: n/b; beide beobachtet64/64. V5 verliert1, V7 verliert8–11.
**Nicht abgedeckte Verlustmöglichkeiten:** alte Aufgaben ohne passende Beobachtung; genutzte age>99; außerhalb des Replay fehlende Aufgaben; Referenz-LLM übersieht Änderungen; Suchausfälle/Nulltreffer; neue Themen-/Status-/Fristkonstellationen; explizite ID-Nennung (historisch0). Keine Token-/Kostenmessung; keine Zukunfts-/Produktionsgarantie.
**Offene Pflicht:** Originalranglisten samt Query-Hash-/Snapshot-/ID-Zuordnung fehlen; exakte V1–V4/V5/V7-Kandidatenanteile, Status-Unionanteile und vollständige V7-Verlustliste bleiben n/b. Lokaler Mengen-/Statistikreview bestätigt die bedingten Nachweise; keine vollständige Wiederholung behauptet.

Quellen: `selector/RANK-VALIDATION.md` (H); benannte `scratchpad/compact_calls.jsonl` (A); `sol-operational-release-20261006/backend/hybrid_index.py` und `hybrid_pipeline.py` (Methoden).
Archivquelle: `~/Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz`, Member `canonical/queue.jsonl` (nicht verfügbar). Replay-SHA256: `3de893f45ef4c55ff569a0df6385abd6781170460ed6ca0dd82a239b566f9211` = historischer Bericht.
Prüfung: Replay-Zähler/Splits/Status/Alter, mengenbasierte Grenzen, CP-Binomialinversion inkl. x=0/64 und 65 Werte; unabhängiger Read-only-Review. Nur Ergebnisdatei geschrieben; keine Zwischendateien/Installation/Netzwerk/API/Server/Secrets/Push; keine Außenverzeichnis-Unverändertheitsnachweise.
