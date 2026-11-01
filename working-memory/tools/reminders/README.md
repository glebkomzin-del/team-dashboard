# Lokaler Arbeits-Memory-Digest

Stdlib-Werkzeug für Python 3.10 oder neuer. Es liest ein Backup, rekonstruiert Aufgaben und schreibt einen deutschen Markdown-Digest. Es stellt nichts zu und benötigt weder Pakete noch Netzwerkzugriff. Alle Ausgaben liegen unter diesem Verzeichnis.

## Aufruf und Prüfung

```sh
cd '/Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard Job/meeting-os/working-memory/tools/reminders'
python3 -I reminders.py --archive auto --today 2026-10-13 --owner Gleb --out out/digest-2026-10-13.md
python3 -I reminders.py --archive '/absoluter/pfad/dashboard-20261012T155114Z.tar.gz' --today 2026-10-13 --owner Gleb --out out/digest.md --cooldown-days 3
python3 -I -m unittest -v
```

`auto` wählt den lexikografisch neuesten `dashboard-*.tar.gz` unter `~/Library/Application Support/Dashboard Job Backup/archives/`. Annahme: Die Dateinamen enthalten den Sicherungszeitpunkt im vorhandenen sortierbaren UTC-Format; Änderungszeitpunkte können durch Kopieren abweichen. `--today` ist verbindlich und steuert die gesamte Auswertung. Relative Ausgabepfade beziehen sich auf das Aufrufverzeichnis. Der CLI-Ausgabepfad muss innerhalb von `tools/reminders/` liegen. Parameterstandards stehen zusammen in `DEFAULT_CONFIG` am Anfang von `reminders.py`; die Sperrfrist lässt sich zusätzlich per CLI einstellen.

Die CLI gibt ausschließlich JSON-Kennzahlen aus: rohe Treffer pro Regel vor Sperrfrist und Mengenlimit, dargestellte Einträge, übrige meldbare Aufgaben, Aufgabenbestand, Digest-Länge in Unicode-Zeichen und UTF-8-Bytes sowie Sekunden einschließlich Archivlesen und Dateischreiben. Fehlerausgaben enthalten keine Datensatzinhalte. Der Digest selbst enthält die erlaubten Aufgabentitel und Quellen; Dateien werden mit privaten Rechten atomisch ersetzt.

## Rekonstruktion und Annahmen

Ein einziger `tar -xzOf`-Prozess streamt `canonical/journal.jsonl` und `canonical/notes.jsonl`. Es werden keine Archivdateien entpackt oder als Zwischenkopie gespeichert. Journal und erforderliche Daten bleiben im RAM; das komprimierte Archiv benötigt keinen zusätzlichen Platz seiner Größe.

Der tatsächliche Archivstand vom 12.10.2026 enthält direkte Journalobjekte mit `revision` sowie Notizobjekte mit teilweise JSON-kodiertem `note_json`. Die im Auftrag beschriebene Hülle mit `kind`, `sequence` und `record_json` wird ebenfalls akzeptiert. Unbekannte Journalarten, beschädigte Daten, unbekannte Änderungsziele und Generationsreferenzen führen zum Abbruch statt zu einem teilweise vollständigen Digest.

Akzeptierte Ersetzungsgenerationen ersetzen die logische Quellen-/Entscheidungsfolge über ihre gespeicherten Referenzen und Feldänderungen. Erst danach werden Aufgaben projiziert. Aufgabenidentitäten folgen den SHA-256-Identitäten von Quelle, Pipeline und Beobachtungsindex. Die Projektion erhält Titel, Claim, Besitzer, Status, Fristtext und Referenzdatum, Bedingung, Thema, letzte Meetingquelle mit Datum sowie erste und letzte fachliche Änderung. Normale Fortschrittsmeldungen löschen keine fehlenden Besitzer-/Frist-/Bedingungswerte. Persönliche Planungen, Bestätigungen und Änderungen werden berücksichtigt. Wissenskorrekturen erzeugen keine Aufgaben; menschlich korrigierte Claims bleiben bei späteren Statusmeldungen erhalten. Bestätigte Aufgabenänderungen tragen die Quelle des bestätigten Meetingvorschlags. `cancelled` und `dismissed` werden als `aborted` geführt; Fakten, Fragen und ungeprüfte Vorschläge erzeugen keine Aufgaben.

Referenzen: `../../evaluation/poc-tiered-reconcile-20261012/m1-bewertung/aufgaben-bewertung.md`, `../../evaluation/sol-operational-release-20261006/backend/memory.py` (`overview`), `planner.py`, `human_decisions.py` sowie die kompakte Generationslogik in `../../evaluation/poc-tiered-reconcile-20261012/pipeline-v12/backend/generation_review.py`. Diese Dateien werden vom ausgelieferten Skript nicht importiert und bleiben unverändert.

## Regeln und Priorität

Es wird der gesamte Aufgabenbestand überwacht. `--owner` beschränkt nur die Stillstandsregel bei Aufgaben ohne Frist; es ist kein Filter auf ausschließlich eigene Aufgaben. Für Gleb werden `Gleb`, `Gleb Komzin`, `Komzin Gleb` und die Variante mit Komma gleichgesetzt. Andere Namen werden nach Groß-/Kleinschreibung und Interpunktion verglichen, ohne Personen zu erraten.

| Priorität | Regel | Standard |
| --- | --- | --- |
| 1 | Überfällig | `open`/`waiting`, geparste Frist vor heute |
| 2 | Bald fällig | `open`/`waiting`, heute bis einschließlich heute + 3 Tage |
| 3 | Nachfassen | `waiting`, letzte Änderung älter als 7 Tage; Bedingung wird genannt, fehlende Bedingung explizit gekennzeichnet |
| 4 | Stillstand | `open`/`waiting`, letzte Änderung älter als 21 Tage, mit Fristtext oder passendem Besitzer |
| 5 | Frist klären oder schließen | `open`/`waiting`, kein Fristtext, erste Änderung älter als 45 Tage |
| 6 | Frist unklar | `open`/`waiting`, vorhandener, nicht eindeutig geparster Fristtext |
| 7 | Aktuell erledigt | `done`, letzte Änderung 0 bis einschließlich 3 Tage zurück |

Annahme: „letzte 3 Tage“ meint maximal drei verstrichene Kalendertage einschließlich heute. Altersgrenzen mit „älter als“ sind strikt. Fehlende/ungültige Änderungsdaten ergeben keinen Alters-/Stillstandstreffer. Abgebrochene Aufgaben bleiben ohne Meldung. Unklare Fristen werden zusätzlich als eigene Klärungsmeldung angeboten; sie gelten nicht als fehlende Frist und können niemals einen geratenen Fälligkeitstreffer erzeugen.

Fristen werden ausschließlich als vollständige Ausdrücke erkannt: ISO-Datum `YYYY-MM-DD`, deutsches `DD.MM.YYYY`, Wochentag, `Ende <Monat> [YYYY]`, `heute`, `morgen`, `übermorgen`, `in N Tagen`; außerdem Präfixe `bis`, `bis zum`, `am`, `zum`, `spätestens bis`. Relative Texte verwenden das Datum ihrer ursprünglichen Fristsetzung, niemals das Auswertungsdatum. `bis Freitag` meint den Freitag am oder nach diesem Referenzdatum, einschließlich desselben Tages. `Ende Oktober` meint das Monatsende im Referenzjahr; es gibt keinen stillen Jahreswechsel. Ohne erforderliches Referenzdatum, bei ungültigen Daten, mehreren Alternativen oder freier Prosa bleibt die Frist unklar. Wörter wie „demnächst“ werden nicht interpretiert.

## Sperrfrist und Digest

`reminders-state.json` liegt neben der gewählten Markdown-Ausgabe und speichert nur Version, Aufgabenidentitäten, Regel und letztes Meldedatum. Standard: erneute Meldung frühestens nach drei verstrichenen Tagen. Nur die fünf Aufgaben mit der ältesten geparsten überfälligen Frist dürfen täglich erneut erscheinen; Gleichstände werden nach stabiler Aufgabenidentität geordnet. Auch für diese fünf gibt es am selben Tag keine Wiederholung. Künftige gespeicherte Meldedaten werden bei einer rückdatierten Auswertung nicht überschrieben.

Pro Aufgabe steht höchstens eine Zeile im Digest, mit gebündelten aktuell meldbaren Gründen. Gesperrte Regeln werden dabei nicht erneut als Grund gemeldet. Meldungen sind priorisiert und auf 15 Aufgaben begrenzt; weitere meldbare Aufgaben und durch die Sperrfrist zurückgestellte Aufgaben erscheinen als Zähler. Nur tatsächlich dargestellte Gründe aktualisieren den Zustand für ihre Aufgabe und Regel. Bereits gesperrte Gründe behalten ihr Meldedatum, auch wenn ein anderer Grund derselben Aufgabe neu angezeigt wird. Das Datum allein setzt nach einer Aufgabenänderung die Sperrfrist nicht zurück. Ein anderer Ausgabedateiname im selben Verzeichnis nutzt denselben Zustand.

Ein beschädigter Zustand wird nicht still gelöscht. Ein absichtlich frischer Lauf benötigt ein neues Ausgabeverzeichnis innerhalb dieses Werkzeugs oder eine bewusst zurückgesetzte Zustandsdatei. Das kann Wiederholungen erzeugen. Produktionseinsatz sollte einen einzelnen täglichen Prozess verwenden; parallele Aufrufe sind nicht synchronisiert. Digest und Zustand werden einzeln atomisch ersetzt, aber nicht als gemeinsame Transaktion; ein Prozessabbruch zwischen beiden Ersetzungen kann eine spätere Wiederholung erlauben.

## Grenzen, Zustellungsvorschlag und Rückweg

Das Werkzeug ist eine Offline-Erinnerung auf dem gesicherten Datenstand. Es bewertet keine Zusagen neu, erkennt keine Personen aus Meetingtexten und stellt keine Verbindung zum Dashboard her. Der Referenzbericht und der Sicherungszeitpunkt können unterschiedliche Stände repräsentieren. Akzeptierte Generationsreferenzen werden geprüft; eine vollständige Backend-Checksum-/Backup-/Produktionsabnahme wird nicht behauptet. Der Rückblick verwendet die letzte Aufgabenänderung, kein zusätzlich abgeleitetes Erledigungsdatum.

Als spätere, separat zu autorisierende Zustellung: Ein Scheduled Task erzeugt täglich um **07:30 Europe/Berlin** einen Digest mit dem aktuellen lokalen Kalenderdatum. Danach kann Gmail-MCP `create_draft` einen E-Mail-Entwurf aus der Markdown-Datei erstellen; Empfänger und Betreff wären separat festzulegen. Der Auftrag hier richtet weder Task noch Entwurf ein und versendet nichts. Die hier gespeicherte Sperrfrist bezieht sich auf die Digest-Erstellung, nicht auf eine tatsächliche Zustellung; ein späterer Zustelldienst müsste seinen eigenen Erfolg bestätigen.

Rückweg: Aufrufe einstellen und ausschließlich dieses Werkzeugverzeichnis entfernen; an Archiv, Referenzen, Dashboard und Produktion wurde nichts geändert. Ein Git-Commit wurde wegen der strikten Schreibgrenze auf dieses Verzeichnis nicht erstellt (`.git` liegt außerhalb). Der lokal geprüfte Dateistand und Zahlenbeleg werden in `out/verification.json` mit SHA-256 festgehalten. Tests verwenden synthetische Daten und temporäre Dateien ausschließlich hier.

## Verifizierter Paketstand

Prüfstand 13.10.2026: synthetische Unittest-Prüfung und echter Archivlauf mit `--today 2026-10-13`. Der Zahlenbeleg, Dateihashes und das unabhängige Review werden in `out/verification.json` festgehalten. Das Werkzeugverzeichnis samt Digest und Zustand war beim Auftragsbeginn bereits vorhanden. Der vorhandene Zustand wird beim Nachweislauf respektiert; Trefferzahlen sind unabhängig von dessen Sperrfristen. Es wurde kein Zustand zurückgesetzt. Nur die ausdrücklich erlaubten Dateien dieses Verzeichnisses werden verändert; kein Commit, Push, Deployment, Versand oder Produktionsschreibzugriff. Es wird keine Laufzeitdurchsetzung der Governance behauptet. Ein lokaler Graphify-Graph fehlt; die begrenzte Quellprüfung verwendet direkte Reads ohne Installation oder neue Graphartefakte.
