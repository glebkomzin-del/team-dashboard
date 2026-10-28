# Read-only-Abnahme der 22 Quellen

Ergebnis: Werkzeug implementiert, Teilstand gelesen: **8/22 übernommen**, Revision 348,
335 Quellversionen, 11 persönliche Entscheidungen; alle ausgeführten Metadatenprüfungen
grün, Dienstgesundheit 200. Das ist ausdrücklich **keine** vollständige 22er-Abnahme.

## Ausführen

Vom Projektstamm aus:

```text
python3 -B meeting-os/working-memory/evaluation/processing-repair-20261028/audit/reprocess22-final.py --require-complete --require-restored
```

Ohne die beiden Pflichtoptionen ist ein sauberer Zwischenstand mit `IN_PROGRESS`
und Exit 0 möglich. `--require-complete` verlangt tatsächlich alle 22;
`--require-restored` verlangt die fünf ursprünglichen Betriebsflags, CPU/RAM/Swap-
Grenzen und aktivierte Verarbeitung. Bei verletzter Pflicht Exit 1, technischen
Abfragefehlern Exit 2. Endgültige Ausgabe als `reprocess22-final.json` speichern.

## Geprüft

- Alle 22 Ziele aus unverändertem Snapshot; Quellenkennung, Dokument, Datum,
  gespeicherter Originalhash und direkt berechneter Original-Inhaltshash.
- Übernommene Quellversion mit Originalhash; Zusammenfassungs-ID und Hash sowohl
  aus produktiver Archivnotiz als auch eigenem `prepared.json` samt Inhaltsprüfung.
- Angenommene Prüfgeneration mit exaktem Prüfsummenabgleich und zugehöriger
  Journalrevision; exakt die neue Zielquelle enthalten.
- Alle 11 ursprünglichen persönlichen Entscheidungen als eindeutige unveränderte
  Referenzen in jeder angenommenen Generation; keine neue persönliche Entscheidung.
- Normale einzelne Aufrufbelege ab dem unveränderlichen Startindex der ausdrücklich
  auditierten Neuläufe: Hashes, Modell und Kosten gegen dauerhaft gespeicherte
  Einzelbelege. Für die erste Quelle separat genau 7 bounded-Belege; importierte oder
  wiederverwendete Antworten werden nicht erneut als zusätzliche Aufrufe gezählt.
- Unveränderte Verarbeitungskonfiguration und Runtimecode; ursprüngliche/aktuelle
  Limits und fünf Betriebsflags; normaler Gesundheitsabruf. Erwarteter Schluss:
  Revision 362, 349 Quellversionen. Abweichung lässt die vollständige Abnahme scheitern.

## Belege / Grenzen

`python3 -B .../audit/reprocess22-final.py --self-check`: Exit 0; unveränderte
persönliche Referenzen akzeptiert, veränderte Referenz verworfen, kein Netzwerk.
AST-Syntaxprüfung: bestanden. Echte lesende Zwischenabnahme: Exit 0, Ausgabe in
`reprocess22-final.json`, keine festgestellten Abweichungen.

Nur vorhandenes Python/SSH/Docker/Postgres, keine Abhängigkeit, keine produktive
Schreiboperation, kein Modellaufruf und keine Zugangsdaten gelesen. SQL läuft in
einer wiederholbar lesenden Read-only-Transaktion; Rohinhalte bleiben auf dem Server.
Die Ausgabe enthält nur Metadaten/Hashes/Zahlen. Private Fehlerdetails werden nicht
ausgegeben. Laufende Annahme kann genau zwischen SQL-Snapshot und Runnerdatei liegen;
ein solcher Zählunterschied erfordert erneutes Lesen nach Abschluss.

Die frühere vollständige Generationsverifikation wird nicht wiederholt; deren exaktes
angenommenes Ergebnis wird zurückgelesen. Kein angemeldeter Browsernachweis.
Zum Abgleich mit `prepared.json` muss der reguläre Recovery-Cache noch vorhanden sein;
daher erste vollständige Abnahme vor Freigeben der Original-Löschwartung ausführen.
Danach Betriebsflags/Restaurierung erneut prüfen. Kein Commit durch den Umsetzer.

Aufwand: gezielt etwa 12 bestehende Quellen/Belege gelesen; ein Skript, ein JSON-
Zwischenbeleg und dieser Bericht geschrieben. Keine Nacharbeit am Pipelinecode.
