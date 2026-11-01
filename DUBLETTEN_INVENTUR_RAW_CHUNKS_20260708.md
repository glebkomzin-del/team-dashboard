# Dubletten-Inventur auf Raw-Transcript-Chunks

Stand: 2026-07-08

Diese Inventur ersetzt `DUBLETTEN_INVENTUR_20260708.md`.

## Methodik

- Dubletten:
  - exakt normalisierte Titel: keine Treffer
  - `pg_trgm` auf normalisierten Titeln, Schwelle ca. `> 0.55`
  - zusätzlich `pg_trgm` auf Titel + Beschreibung, Schwelle ca. `> 0.42`
  - inhaltliche Bewertung anhand Titel, Beschreibung, Person und Datum
- Erledigungsnachweise:
  - ausschließlich echte Raw-Transcript-Chunks aus `transcript_chunks.content`
  - `chunk_index >= 0`
  - `chunk_index = -1` wurde ausgeschlossen, weil es Kontext-/Summary-Chunks sind
  - Meeting-Datum muss nach dem Belegdatum des Eintrags liegen
  - generische Tokens wurden herausgefiltert
  - klare Abschlussmarker: erledigt, abgeschlossen, fertiggestellt, fertig, gelöst, geklärt, umgesetzt, validiert, freigegeben, entfallen, obsolet, nicht mehr relevant

## Phase 0 - Vorbereitung

Backup-Tabelle existiert: `public.cleanup_backup_20260708`.

`public.nightly_archive_completed()` behandelt als abgeschlossen:

| Tabelle | Abschluss-Status |
|---|---|
| `todos` | `done`, `cancelled` |
| `blockers` | `resolved` |
| `open_items` | `closed` |

Trigger-Risiko: Normale `UPDATE`/`DELETE` auf `todos`, `blockers`, `open_items` würden `activity_log`- und Embedding-Trigger auslösen. Phase 2 darf deshalb nur mit expliziten ID-Listen, vorherigem Backup und trigger-schonendem Vorgehen laufen.

## Ausgangszahlen

| Tabelle | Gesamt | Nicht final |
|---|---:|---:|
| `todos` | 68 | 68 |
| `blockers` | 21 | 21 |
| `open_items` | 192 | 192 |

## A) Dubletten-Gruppen - innerhalb derselben Tabelle

| Gruppe | Tabelle | Überlebender | Zu löschende IDs | Zu übernehmende Felder |
|---|---|---|---|---|
| D1 | `todos` | `574b9474-236e-436a-a7d5-31cf1f1800f2` - Thomas: Kostenstellengruppen für deutschen Zentralbereich anlegen | `50e0111a-7b66-41ad-8707-27a9db30123b`, `580085d7-f15f-412f-9f0f-a5c8a22e66eb` | Keine strukturierten Felder; alle haben `meeting_id`, keine `project_id`/`due_date`. Überlebender ist spezifischster Eintrag. |
| D2 | `open_items` | `9d7147a3-6ffc-47ea-b66b-851b429e6223` - Konsolidierungsbuchungen mit Daniel klären | `0f9ad6fd-ef15-4fdf-b02c-f2ebd904cbd2`, `7f307f6e-6442-4f46-a371-e8841ce7794f` | Keine strukturierten Felder; Überlebender hat konkreteste Prozessbeschreibung. |
| D3 | `open_items` | `3c0e5849-4ebe-497d-b22a-3f68f9724df5` - Strategische vs. politische Filiale | `c1ffa3d7-a413-4864-b646-d826a15fe092`, `4a2cea3c-e66b-4d0a-aa9d-43f963d513d2` | Keine strukturierten Felder; Überlebender beschreibt das allgemeinere reale Anliegen. |

## Tabellenübergreifende Dubletten / Überschneidungen

Nur ausweisen, nicht automatisch löschen:

| Gruppe | Tabellen | IDs | Bewertung |
|---|---|---|---|
| X1 | `blockers` + `todos` | `4a99973c-6bca-4f2c-a3cd-bd8e61f64f40` / `8394134d-e4c8-455f-880b-417ffcb0a06e` | Gleiche Sache: Link für Rechtskosten-Datei von Diana Hampe fehlt/einholen. |
| X2 | `open_items` + `todos` | `918c1c98-3876-4e22-897b-d7ab94e92e02` / `8440b377-7a56-47d1-875b-7882eaaa070a` | Gleiche Sache: Roadmap Berichte/Berichtsentwicklung finalisieren. |
| X3 | `blockers` + `open_items` | `26e902ee-93f4-4e92-a197-09f7e4b15428` / `64be7502-77e1-494f-b9f5-df12c8b606f0` | Gleiches Oberthema Berechtigungskonzept, aber späterer Kontext widerspricht automatischer Bereinigung. |
| X4 | `blockers` + `todos` | `6f4bd5fe-6c4e-4566-ba17-94193b56fb8e` / `39412715-c9fb-49db-a614-73457977c5df` | Gleiche Sache: WBN-Kostenstellen-Verteilung klären. |
| X5 | `open_items` + `todos` | `d19e56c3-f45a-400e-b087-f3457ee02a23` / `f65a4406-4a1a-4cde-9d4f-2ca289f50514` | Gleiche Sache: Grauert / neue Quadratmeter-Planwerte klären. |
| X6 | `open_items` + `todos` | `56c4c45a-6428-4bf4-8ba1-ec524c64ccb0` / `c54f09dd-a6c1-4ff2-ad4c-064a90f30d1a` | Gleiche Sache: JobRouter-Kostenstellenberechtigungen / Genehmigungsworkflow. |
| X7 | `blockers` + `todos` | `35b99d01-d7c5-4f7a-ba2c-6993958b8ebc` / `6d17d232-b541-4d6d-8386-f22f24f30f09` | Gleiche Sache: Stammdaten für Innenauftragsnummern organisieren. |

## B) Ableitbar erledigte Einträge

| Tabelle | ID | Titel | Raw-Chunk-Beleg | Ziel-Status |
|---|---|---|---|---|
| `open_items` | `1f683b65-5cc3-4fcd-ac48-347bd7866c72` | Berechtigungskonzept Termin nächste Woche | 2026-05-06, Raw-Chunk 34/35: "das was heute besprochen und abgeschlossen wurde..." und anschließend "Hätten wir das? OK." Der Eintrag beschreibt den Termin zur Klärung, nicht das gesamte Berechtigungskonzept. | `closed`, `closed_at='2026-05-06'` |

## Unsicher - nicht anfassen

| Tabelle | ID | Titel | Raw-Chunk-Signal | Warum unsicher |
|---|---|---|---|---|
| `blockers` | `26e902ee-93f4-4e92-a197-09f7e4b15428` | Berechtigungskonzept unklar | 2026-05-13/15 teilweise fachlich geklärt; 2026-06-30 und 2026-07-02 weiterhin RLS/Berechtigungskonzept problematisch | Gleiches Wortfeld, aber Thema lebt später weiter. |
| `open_items` | `64be7502-77e1-494f-b9f5-df12c8b606f0` | Berechtigungskonzept klären | 2026-07-02: Konzept vom 15.05 steht als Arbeitsgrundlage, aber Schnittstelle/JobRouter/RLS weiterhin offen | Kein finaler Abschluss. |
| `open_items` | `3de75d09-dc85-400e-a5ad-96aa34a9bbf5` | Konsolidierungsbuchungen im Testsystem | 2026-06-30: "dann blieben nur noch ... Konsolidierungsbuchungen" | Weiter offen. |
| `open_items` | `9d7147a3-6ffc-47ea-b66b-851b429e6223` | Konsolidierungsbuchungen mit Daniel klären | 2026-06-30: Konsolidierungsbuchungen weiterhin Klärung | Nicht erledigt. |
| `todos` | `574b9474-236e-436a-a7d5-31cf1f1800f2` | Thomas: Kostenstellengruppen für deutschen Zentralbereich anlegen | 2026-05-26: Thomas nennt Kostenstellengruppen weiterhin als zu erstellendes Thema | Nicht erledigt. |
| `blockers` | `6f4bd5fe-6c4e-4566-ba17-94193b56fb8e` | Unklarheit über WBN-Kostenstellen Verteilung | Treffer vorhanden, aber keine klare Abschlussformulierung zum WBN-Verteilungsproblem | Nicht anfassen. |
| `todos` | `39412715-c9fb-49db-a614-73457977c5df` | Sebastian: WBN-Kostenstellen Verteilung klären | siehe WBN-Blocker | Nicht anfassen. |
| `open_items` | `918c1c98-3876-4e22-897b-d7ab94e92e02` | Roadmap für Berichtsentwicklung finalisieren | Spätere Roadmap-Treffer betreffen andere Kontexte/Workshops | Nicht eindeutig. |
| `todos` | `8440b377-7a56-47d1-875b-7882eaaa070a` | Roadmap für Berichte finalisieren | siehe Roadmap-Open-Item | Nicht eindeutig. |
| `open_items` | `d19e56c3-f45a-400e-b087-f3457ee02a23` | Herr Grauert: Spezifikation neuer Quadratmeter-Planwerte | Keine klare spätere Abschlussformulierung gefunden | Nicht anfassen. |
| `todos` | `f65a4406-4a1a-4cde-9d4f-2ca289f50514` | Gespräch mit Herrn Grauert zu neuen Quadratmeter-Planwerten | Keine klare spätere Abschlussformulierung gefunden | Nicht anfassen. |
| `open_items` | `56c4c45a-6428-4bf4-8ba1-ec524c64ccb0` | JobRouter Team: Genehmigungsworkflow für Kostenstellen-Berechtigungen | 2026-07-02: keine Schnittstelle S/4 -> JobRouter-Datenbank | Weiter offen. |
| `todos` | `c54f09dd-a6c1-4ff2-ad4c-064a90f30d1a` | Faruk: JobRouter-Implementierung für Kostenstellenberechtigungen | 2026-07-02: JobRouter-Teil weiterhin Problem | Nicht erledigt. |
| `blockers` | `35b99d01-d7c5-4f7a-ba2c-6993958b8ebc` | Fehlende Stammdaten für Innenauftragsnummern | Treffer zu Innenaufträgen, aber keine eindeutige Abschlussformulierung | Nicht anfassen. |
| `todos` | `6d17d232-b541-4d6d-8386-f22f24f30f09` | Innenauftragsnummern-Stammdaten organisieren | Treffer zu Innenaufträgen, aber keine eindeutige Abschlussformulierung | Nicht anfassen. |

## Summen

| Kategorie | Anzahl |
|---|---:|
| Dubletten löschen | 7 |
| Als erledigt markieren | 1 |
| Unsicher, nicht anfassen | 15 Einträge |

## Phase-2-Vorschlag

Phase 2 ist die eigentliche Mutation:

1. Vorher-Zählung je Tabelle und `activity_log`-Baseline.
2. Transaktion starten.
3. User-Trigger auf `todos`, `blockers`, `open_items` temporär deaktivieren.
4. Jede zu löschende oder zu ändernde Zeile vorher in `cleanup_backup_20260708` sichern.
5. Dubletten D1-D3 per expliziten IDs löschen.
6. `activity_log`-Zeilen für gelöschte Dubletten-IDs entfernen.
7. `open_items.1f683b65-5cc3-4fcd-ac48-347bd7866c72` auf `closed` mit `closed_at='2026-05-06'` setzen.
8. Trigger wieder aktivieren.
9. Commit, Nachher-Zählung, Backup-Stichprobe, Prüfung auf keine neuen `activity_log`-Einträge.

Der Nightly-Job räumt final markierte Einträge um 22:00 weg.
