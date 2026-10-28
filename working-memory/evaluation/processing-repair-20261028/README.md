# Verarbeitung: Reparaturprüfung 28.10.2026

## Produktives Ergebnis nach Glebs Freigabe „Ja“

Die geprüfte Korrektur und Zusatzdiagnose sind auf dem Server eingespielt (`dashboard-memory:processing-repair-20261028`). Beide betroffenen Quellen und ihre Zusammenfassungen wurden getrennt über die vorhandenen geprüften Funktionen übernommen und zurückgelesen: GCO auf Stand 339, Reporting auf Stand 340. Zwei Archivnotizhashes stimmen mit den geprüften gespeicherten Antworten überein. Die elf persönlichen Entscheidungen bleiben erhalten.

Aktuell: **0 `validation_failed`, 22 verbleibende `provider_outcome_unknown`**. Die automatische Verarbeitung und sämtliche ursprünglichen Betriebsflags sind wiederhergestellt. Während der Reparatur keine neuen Modell- oder Frageaufrufe: Zähler unverändert bei 5.782 beziehungsweise 65. Laufende Codehashes entsprechen den geprüften Kandidaten; öffentliche Serverprüfung `/dashboard-memory/health`: HTTP 200, `status=ok`, `mode=production`.

Die öffentliche Dashboardseite lädt im Browser. Eine angemeldete Browserabnahme ist hier nicht belegt: Der Prüf-Browser verlangt eine Anmeldung; Zugangsdaten wurden nicht verwendet. Die erfolgreiche Übernahme ist serverseitig und anhand der gespeicherten Zustände belegt.

Sicherung: 706.679.003 Bytes auf dem bestehenden Server, SHA-256 `19662added3659ea456c68084ef76f2813998f98075d87ec849740244acd2178`, vollständiges Archiv-Rücklesen erfolgreich. Keine Wiederherstellung in eine neue Datenbank behauptet. Beim ersten Wartungsstart verhinderte die Kombination aus Lesemodus und aktiviertem Originallöschen den Start; die fehlende temporäre Einstellung wurde korrigiert, mit echter Startregression geprüft und der Dienst erfolgreich erneut gestartet. Danach 7 Deploymenttests grün; kein Datenverlust oder zusätzlich ausgelöster KI-Aufruf.

Belege: `audit/production-result.json`, `audit/backup-result.json`, `audit/adoption-readback.json`, `audit/generation-readback.json`; private Phasenausgaben unter `deploy/private/`. Die folgenden Abschnitte dokumentieren Vorbereitung und Prüfung vor der Übernahme.

Auftrag: Die im Dashboard gemeldeten 24 unvollständigen Quellen untersuchen und die konkrete Fehlerursache reparieren. Bestehende Quellen, Schutzprüfungen und fremde Arbeitsstände erhalten. Gleb hat neue KI-Aufrufe ausdrücklich abgelehnt.

## Aktuell bestätigter Befund

Rein lesende Produktionsabfragen am 28.10.2026:

- 24 Aufträge im Zustand `review`: 22 `provider_outcome_unknown`, 2 `validation_failed`.
- 22 Empfangsfehler enthalten eine gespeicherte Fehlerantwort mit `error=ValueError`, `terminal_status=null`, leerem Inhalt und einem Flex-Versuch. Die genaue ursprüngliche Stream-Fehlermeldung ist nicht gespeichert.
- 16 dieser 22 Quellen scheiterten beim ersten Aufruf; 6 haben frühere Teilergebnisse. Keiner der 22 Aufträge hat `prepared_payload`.
- Die zwei Inhaltsprüfungen betreffen GCO JF (`7b4057c2`) und Regelmäßiger Austausch Reportingthemen (`a77d73b4`), beide vom 13.10.2026.
- Andere Quellen wurden bis 28.10.2026 erfolgreich übernommen. Die isolierten Quellen belegen keinen Stillstand der gesamten Verarbeitung.

## Begrenzte lokale Arbeit

1. Den tatsächlich laufenden Provideradapter unverändert nach `baseline/` exportieren; SHA-256 in `baseline-manifest.json`.
2. Verlust technischer Fehlercodes im Streamparser mit künstlichen Antworten reproduzieren und minimal korrigieren. Keine Erweiterung automatischer Wiederholungen.
3. Die zwei vorhandenen Prüfablehnungen ohne neue KI-Aufrufe gegen gespeicherte Antworten untersuchen.
4. Lokale Prüfungen ausführen. Kein Erfolg der 24 Quellen aus einem Parser-Test ableiten.

Abnahme: Der lokale Adapter erhält sichere technische Fehlercodes, unterscheidet unvollständigen Stream und Statuswiderspruch und akzeptiert weiterhin nur vollständige gültige Antworten. Keine Ausgabe von Schlüsseln, Prompts oder freien Providerfehlermeldungen. Prüfungen: `python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/provider -p 'test_*.py'` vom übergeordneten Projektordner.

## Ausgeführte lokale Prüfung

Lead-Prüfung: `python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/provider -p 'test_*.py'`: 6 Tests bestanden, Exit 0. Der isolierte Kandidat steht unter `provider/`; der laufende Dienst wurde nicht verändert. Diese Abnahme betrifft nur die technische Fehlerdiagnose, nicht die Wiederherstellung der 24 Quellen.

Der zweite Kandidat `replay/overlay/memory.py` korrigiert einen konkret reproduzierten Fehler: Eine vom Gate bereits abgelehnte, prüfpflichtige Aufgabenänderung mit widersprüchlicher Themenzuordnung wurde trotz bereits gesperrter Wirkung nochmals wie eine wirksame Aufgabenänderung behandelt. Die Korrektur erhält diese Beobachtung im ursprünglichen bekannten Wissensbereich; wirksame Änderungen in einem fremden Bereich werden weiterhin abgelehnt. Unbekannte Aufgaben und erfundene Belege bleiben ebenfalls gesperrt.

Lead-Prüfungen des zweiten Kandidaten:

- `python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/replay -p 'test_scope.py'`: zuletzt 6 Tests bestanden, Exit 0.
- `python3 meeting-os/working-memory/evaluation/processing-repair-20261028/replay/check_memory.py`: 17 bestehende Tests bestanden, nachweislich mit dem Kandidaten geladen, Exit 0.
- `python3 meeting-os/working-memory/evaluation/processing-repair-20261028/replay/validate_saved.py`: beide vollständigen historischen Vorschläge scheitern im unveränderten Original an `Work update belongs to a different matter`, Exit 0 für die erwartete Reproduktion.
- Derselbe Befehl mit `--candidate`: beide Vorschläge bestehen mit 31 beziehungsweise 36 Beobachtungen, jeweils ohne Arbeitsereignis für die abgelehnte Aufgabenänderung, Exit 0.

Diese Wiederholungen sind vom Netzwerk und von Unterprozessen abgeschottet. Sie verwenden bestehende Antworten; kein neuer KI-Aufruf.

Lead-Prüfung `replay/current_preview.py`: aktueller Journalstand 337 mit allen historischen Ergebnisprüfsummen unverändert rekonstruiert. Kombinierte lokale Wiederherstellungsvorschau kompiliert und verifiziert: 324 bestehende Quellen und 11 menschliche Entscheidungen bleiben erhalten, zwei Quellen kommen hinzu. Kandidatenhash `e822eb293d6d87cc74f0df5671e4d656c060c81ccce6502860b7c142803c2316`; Vorschauhash `b5e633b79f268174018089997b6b356e9fd1a61618087c9e5fcca50f2c20f076`.

Die kombinierte Vorschau ersetzt keinen produktiven Übernahmeablauf: Das bestehende Entscheidungssystem bindet jeweils genau einen betroffenen Auftrag. Deshalb wurden zusätzlich zwei aufeinanderfolgende Vorschauen samt Zusammenfassungen vorbereitet und geprüft. Nach einer Datenübernahme wäre allein das alte Programm kein sicherer Rückweg, weil dessen alte Prüfung die neu aufgenommenen Wissensbeobachtungen wieder ablehnen würde.

Lead-Prüfung `replay/sequential_preview.py`: Exit 0, vollständig PASS. GCO ist einzeln an Stand 337→338 gebunden, Reporting an 338→339. Die Zusammenfassungen mit sechs beziehungsweise vier belegten Absätzen sind aus vorhandenen Antworten rekonstruiert und geprüft. Alle elf persönlichen Entscheidungen bleiben erhalten. Eine ebenfalls geprüfte Gegengeneration stellt die ursprünglichen logischen Einträge wieder her; dies ist keine Behauptung einer vollständigen Rücksetzung aller Auftrags-/Auditmetadaten.

## Freigegebener Übernahmeumfang

- Im bestehenden Dienst ausschließlich `replay/overlay/memory.py` und die sichere Zusatzdiagnose `provider/openai_provider.py` übernehmen; vorhandene Modell-, Kosten- und Wiederholungsregeln erhalten. Neue Pipelinekennung regelkonform konfigurieren und zurücklesen.
- Die zwei gespeicherten Ergebnisse einzeln über die vorhandenen geprüften Entscheidungsfunktionen übernehmen, jeweils mit frischen Revisions-, Original-, Vorschauhash- und Auftragsstandprüfungen. Beide Zusammenfassungen über die vorhandene idempotente Archivnotizfunktion speichern.
- Nach jedem Schritt Arbeitsstand, Auftrag und Archiv zurücklesen; abschließend die reale Dashboardanzeige prüfen. Bei verändertem Ausgangsstand zunächst neue Offline-Vorschauen erstellen. Kein blindes Zurücksetzen der Warteschlange und keine direkten Tabellenupdates.
- Keine neuen KI-Aufrufe. Die 22 Empfangsfehler bleiben offen; fehlende Antworten werden nicht erfunden oder als wiederhergestellt gemeldet.

Der ausführliche Ablauf samt Rückweggrenzen steht in `replay/README.md`. Die oben dokumentierte produktive Übernahme ist inzwischen ausgeführt; eine angemeldete Browserabnahme bleibt nicht belegt.

## Unabhängige Ergebnisprüfung

Ergebnis: **PASS für lokale Korrekturen und vorbereitete Offline-Wiederherstellung**, keine blockierenden Codebefunde. Der frische schreibgeschützte Prüfer bestätigte selbst 29 Tests, 123 Request-/Response-Prüfsummen sowie beide echten vollständigen Vorschläge vor und nach Korrektur. Sequenz, Zusammenfassungen und Gegenentwurf wurden zusätzlich anhand von Code und Ergebnisartefakten geprüft. Das ursprüngliche Gesamtziel ist nur teilweise erreicht: zwei Quellen sind lokal wiederherstellbar; die produktive Übernahme und weitere 22 unvollständige Quellen bleiben offen.

Rückweghinweis aus dem Review: Die Gegengeneration stellt die ursprünglichen logischen Inhalte wieder her, setzt aber abgeschlossene Auftragszustände nicht zurück und entfernt separat gespeicherte Archivnotizen nicht. Sie ist kein vollständiges Datenbank-Undo. Auch die Ergebnisprüfung belegt keine produktive Browserabnahme.

## Noch offene Wiederherstellung

Zwei Quellen sind produktiv wiederhergestellt. Die verbleibenden 22 Quellen wurden nicht neu gestartet; ihre fehlenden Antworten wurden nicht erfunden. Zusätzliche KI-Aufrufe bleiben nicht freigegeben. Die Ablehnungsprüfungen bleiben wirksam. Die eigentliche Ursache der 22 verlorenen Streamantworten ist noch nicht belegt.

Die historische Journalbasis bis Revision 313 beziehungsweise 314 ist per SELECT vollständig belegt. Das ermöglicht die weitere Offline-Rekonstruktion der zwei Inhaltsprüfungen; fehlende temporäre SQLite-Dateien sind allein kein Abbruchgrund. Historische Suchergebnisse müssen dabei ebenfalls aus gespeicherten Daten kommen; produktive Such-RPCs mit möglichem Schreibeffekt sind ausgeschlossen.

Offizielle technische Referenzen: [Responses-Streamereignisse](https://developers.openai.com/api/reference/resources/responses/streaming-events), [Flex-Verarbeitung](https://developers.openai.com/api/docs/guides/flex-processing). Die Dokumentation belegt die Schnittstelle, nicht die tatsächliche Ursache der 22 Produktionsfehler.
