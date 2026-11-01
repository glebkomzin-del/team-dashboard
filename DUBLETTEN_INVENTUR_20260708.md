# Dubletten-Inventur & Bereinigungsvorschlag

> Status: ÜBERHOLT / NICHT ALS PHASE-2-GRUNDLAGE VERWENDEN.
> Diese erste Inventur nutzte für Erledigungsnachweise primär `meetings` und `meeting_topics`.
> Nach Review ist klar: Die zuverlässige Belegsuche muss über echte `transcript_chunks`
> laufen und `chunk_index = -1` Kontext-/Summary-Chunks ausschließen.

Stand: 2026-07-08

## Phase 0 - Vorbereitung

- Projekt: `lghwikeotbkmojyyjglz`
- Backup-Tabelle angelegt: `public.cleanup_backup_20260708`
- Backup-Tabelle aktuell leer: `0` Zeilen
- `pg_trgm` ist aktiv.

### Nightly-Job

`public.nightly_archive_completed()` behandelt folgende Status als abgeschlossen und löscht diese nachts:

| Tabelle | Abschluss-Status |
|---|---|
| `todos` | `done`, `cancelled` |
| `blockers` | `resolved` |
| `open_items` | `closed` |

Die Funktion schreibt vor dem Löschen selbst `activity_log`-Einträge und löscht danach die finalen Einträge aus den drei Tabellen.

### Trigger-Risiko vor Phase 2

Auf `todos`, `blockers`, `open_items` liegen aktive Trigger für:

| Art | Wirkung |
|---|---|
| `trg_*_status` | schreibt bei `UPDATE` in `activity_log` |
| `trg_*_updated` | setzt `updated_at` bei `UPDATE` |
| `embed_*` und `trg_*_embedding` | rufen bei `INSERT/UPDATE/DELETE` die Embedding-Pipeline auf |
| `trg_*_prefix`, `trg_*_role_enum` | greifen bei `INSERT/UPDATE` |

Zusätzlich hat `activity_log` einen `AFTER INSERT`-Trigger für Activity-Embeddings.

Konsequenz: Phase 2 sollte nicht mit normalen `UPDATE`/`DELETE`-Statements laufen, sonst entstehen neue `activity_log`-Einträge und Embedding-Jobs. Vorgeschlagenes Vorgehen für Phase 2: innerhalb einer Transaktion gezielt `DISABLE TRIGGER USER` auf den drei betroffenen Tabellen, Backup schreiben, Mutationen per expliziten IDs ausführen, verwaiste `activity_log`-Zeilen für gelöschte Dubletten entfernen, Trigger wieder aktivieren, Verifikation durchführen. Keine manuellen neuen `activity_log`-Einträge.

## Ausgangszahlen

| Tabelle | Gesamt | Nicht final |
|---|---:|---:|
| `todos` | 68 | 68 |
| `blockers` | 21 | 21 |
| `open_items` | 192 | 192 |

## A) Dubletten-Gruppen

Exakt gleiche normalisierte Titel: keine.

| Gruppe | Tabelle | Überlebender | Zu löschende IDs | Zu übernehmende Felder |
|---|---|---|---|---|
| D1 | `todos` | `580085d7-f15f-412f-9f0f-a5c8a22e66eb` - Thomas: Kostenstellen-Gruppen in SAP anlegen | `50e0111a-7b66-41ad-8707-27a9db30123b` | Keine; beide haben `meeting_id`, keine `project_id`/`due_date`, Überlebender hat spezifischere SAP-Beschreibung. |
| D2 | `open_items` | `9d7147a3-6ffc-47ea-b66b-851b429e6223` - Konsolidierungsbuchungen mit Daniel klären | `0f9ad6fd-ef15-4fdf-b02c-f2ebd904cbd2`, `7f307f6e-6442-4f46-a371-e8841ce7794f` | Keine; keine `project_id`/`due_date`, Überlebender hat konkreteste Prozessbeschreibung. |
| D3 | `open_items` | `3c0e5849-4ebe-497d-b22a-3f68f9724df5` - Strategische vs. politische Filiale | `c1ffa3d7-a413-4864-b646-d826a15fe092`, `4a2cea3c-e66b-4d0a-aa9d-43f963d513d2` | Keine; keine `project_id`/`due_date`, Überlebender hat allgemeinste und vollständigste Definition. |

### Tabellenübergreifende Dubletten / Überschneidungen

Nur ausweisen, nicht automatisch löschen:

| Gruppe | Tabellen | IDs | Bewertung |
|---|---|---|---|
| X1 | `blockers` + `todos` | `4a99973c-6bca-4f2c-a3cd-bd8e61f64f40` / `8394134d-e4c8-455f-880b-417ffcb0a06e` | Gleiche Sache: Link für Rechtskosten-Datei von Diana Hampe fehlt/einholen. |
| X2 | `open_items` + `todos` | `918c1c98-3876-4e22-897b-d7ab94e92e02` / `8440b377-7a56-47d1-875b-7882eaaa070a` | Gleiche Sache: Roadmap für Berichte/Berichtsentwicklung finalisieren. |
| X3 | `blockers` + `open_items` | `26e902ee-93f4-4e92-a197-09f7e4b15428` / `64be7502-77e1-494f-b9f5-df12c8b606f0` | Gleiches Oberthema Berechtigungskonzept, aber späterer Kontext widersprüchlich; nicht automatisch löschen. |

## B) Ableitbar erledigte Einträge

Konservativ eindeutige Treffer:

| Tabelle | ID | Titel | Beleg | Ziel-Status |
|---|---|---|---|---|
| `open_items` | `1f683b65-5cc3-4fcd-ac48-347bd7866c72` | Berechtigungskonzept Termin nächste Woche | 2026-05-18: "Das Berechtigungskonzept hat sich dahingehend erledigt, dass Berechtigungen ausschließlich auf Profitcenter-Ebene vergeben werden." | `closed`, `closed_at='2026-05-18'` |

## Unsicher - nicht anfassen

| Tabelle | ID | Titel | Beleg / Signal | Warum unsicher |
|---|---|---|---|---|
| `blockers` | `26e902ee-93f4-4e92-a197-09f7e4b15428` | Berechtigungskonzept unklar | 2026-05-18: "Das Berechtigungskonzept wurde als im Wesentlichen gelöst betrachtet..." | Späterer Treffer 2026-06-29 sagt: "Das Berechtigungskonzept für den Datenzugriff ist noch nicht abgeschlossen..." Daher nicht eindeutig final. |
| `open_items` | `64be7502-77e1-494f-b9f5-df12c8b606f0` | Berechtigungskonzept klären | 2026-05-18 gelöst/erledigt, aber 2026-06-29 nicht abgeschlossen | Kann altes Profitcenter-Thema oder neues Datenzugriffs-/RLS-Thema sein. |
| `open_items` | `2c93621f-19f0-43f4-b714-269af410f97b` | Berechtigungskonzept für Datenfeld-Pflege | 2026-05-18 gelöst/erledigt | Inhalt bezieht sich auf Trade-Net-Datenpflege, nicht sicher auf Profitcenter-Berechtigung. |
| `open_items` | `3766e787-5d1e-4af2-bc37-6cde467feca6` | Berechtigungskonzept für Ergebnisrechnung entwickeln | Mehrere spätere Sätze zu Ergebnisrechnung validiert/fertiggestellt | Ergebnisrechnung teilweise fertig, Berechtigungskonzept/RLS später weiter offen. |
| `blockers` | `166a4f0e-79b5-48d1-ae2c-de687a822f49` | Faruk: Verzögerung bei Plankosten-Freigabe | 2026-06-01: "die Lösung für Juni umgesetzt wurde, der Mai jedoch nie explizit zur Neuverteilung freigegeben wurde..." | Satz enthält Umsetzung/Freigabe, beschreibt aber weiterhin fehlende Mai-Freigabe. |
| `todos` | `8440b377-7a56-47d1-875b-7882eaaa070a` | Roadmap für Berichte finalisieren | 2026-06-12: "Roadmap ... noch nicht abgeschlossen"; 2026-06-29: "fertiger Roadmap..." | Spätere Roadmap kann anderer Workshop-Kontext sein; nicht eindeutig. |
| `open_items` | `918c1c98-3876-4e22-897b-d7ab94e92e02` | Roadmap für Berichtsentwicklung finalisieren | gleiche Roadmap-Treffer wie oben | Nicht eindeutig genug. |
| `todos` | `50e0111a-7b66-41ad-8707-27a9db30123b` / `580085d7-f15f-412f-9f0f-a5c8a22e66eb` | Thomas: Kostenstellengruppen anlegen | 2026-05-08: "Grundarchitektur ist weitestgehend fertig, aber die Kostenstellengruppen sind noch nicht verlinkt."; 2026-06-02: "Ungeklärte Situation..." | Keine Abschlussbestätigung für das konkrete Anlegen. |
| `blockers` | `4a99973c-6bca-4f2c-a3cd-bd8e61f64f40` / `todos` `8394134d-e4c8-455f-880b-417ffcb0a06e` | Diana-Hampe-Rechtskosten-Link | keine eindeutige spätere Abschlussformulierung gefunden | Nur Dubletten-/Überschneidungskandidat, keine Erledigung. |

## Summen

| Kategorie | Anzahl |
|---|---:|
| Dubletten löschen | 5 |
| Als erledigt markieren | 1 |
| Unsicher, nicht anfassen | 9 Einträge / Themen |

## Phase-2-Plan nach Freigabe

1. Vorher-Zählung je Tabelle und `activity_log`-Baseline erfassen.
2. Transaktion starten.
3. `alter table public.todos disable trigger user;` analog für `blockers`, `open_items`.
4. Alle zu ändernden/zu löschenden Zeilen in `cleanup_backup_20260708` sichern.
5. Dubletten per expliziten IDs löschen; `activity_log`-Zeilen zu gelöschten IDs entfernen.
6. `open_items.1f683b65-5cc3-4fcd-ac48-347bd7866c72` auf `status='closed'`, `closed_at='2026-05-18'` setzen.
7. Trigger wieder aktivieren.
8. Commit.
9. Nachher-Zählung, Backup-Stichprobe und Prüfung, dass keine neuen `activity_log`-Einträge durch Phase 2 entstanden sind.

Hinweis: Der Nightly-Job läuft laut Migration täglich um 22:00 und räumt final markierte Einträge weg.
