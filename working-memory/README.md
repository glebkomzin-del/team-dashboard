# Dashboard Job – produktives Arbeitsgedächtnis

## Aktueller Betriebsstand

Die App ist produktiv unter https://team-dashboard-rho.vercel.app. Der aktuelle Betriebsstand und die Automatikfreigabe stehen in [NEXT-OPERATIONS.md](docs/NEXT-OPERATIONS.md), die Release- und Verarbeitungsnachweise in [RELEASE-2026-09-19.md](docs/RELEASE-2026-09-19.md).

## Historischer Prototypstand

Die folgenden Angaben beschreiben die ursprüngliche isolierte Erprobung. Aussagen zu fehlender Produktionsfreigabe, pausierter Verarbeitung und damaligen Rückständen sind keine aktuellen Betriebssperren.

Die Bestandsaufnahme und ein durchgängiger Prototyp sind umgesetzt. Die produktive Migration ist noch nicht freigegeben. Der bisherige Import stockt zusätzlich wegen des ausgeschöpften Make-Kontingents; der vorhandene Google-Drive-Zugang funktioniert.

- [Belegte Ursachen und tatsächliche Verarbeitung](docs/AUDIT.md)
- [Fachliches Zielmodell und Freigaberegeln](docs/TARGET.md)
- [Modellvergleich, echte Fälle, Kosten und Nachweisgrenzen](docs/EVALUATION.md)
- [n8n, Drive-Zugang, Sicherung und Umschaltung](docs/MIGRATION.md)
- [19 reale Vorher-/Nachher-Zuordnungen für den Altbestand](docs/BACKLOG.md)
- [React-Testansicht, Start und Prüfprotokoll](docs/UI-PREVIEW.md)
- [Finance-Testansicht](.local/preview/index.html) · [langes Jan/Gleb-Meeting](.local/preview/long-meeting.html)

## Nachvollziehbare Änderungen

Originalquelle/Version → belegte Beobachtungen → bestehende Vorgänge → echte Verpflichtungen und Änderungen. Voraussetzungen, Optionen und Risiken bleiben Wissen. Nutzerbestätigte Quellenkorrekturen überstimmen Modellurteile. In der Finance-Folge bleiben Caroline/Marc und Olivers schriftliche Ergänzung offen; der spätere Terminabschluss schließt nicht die Migrationsentscheidung.

Python-Standardbibliothek, SQLite mit Ereignishistorie, private HTTP-Schnittstelle, eigenständiger n8n-Workflow und Docker-Dienst. Wiederholte Imports, konkurrierende Worker, begrenzte Fehlerbehandlung und unveränderte Quellen sind abgesichert. Keine produktive Supabase-Tabelle wurde durch diesen Prototyp geändert.

## Lokal nachprüfen

Aus diesem Verzeichnis:

```sh
python3 -m unittest discover -v
python3 evaluation/measure_saved.py
python3 render_review.py --db .local/finance-corrected-v4.sqlite --output .local/preview/index.html
python3 -m http.server 8793 --bind 127.0.0.1 --directory .local/preview
```

Die Regressionen benötigen die hier lokal vorhandenen privaten Ergebnisdateien. Sie werden absichtlich nicht versioniert. Nur das Preview-Unterverzeichnis per HTTP freigeben; `.local` enthält auch vertrauliche Originale und lokale Zugangsdaten.

`processor.py` verarbeitet explizit angegebene Meeting-JSON-Dateien und kann kostenpflichtige API-Aufrufe auslösen. `reproject.py` baut gespeicherte Vorschläge in einer **neuen** SQLite-Datei ohne API-Aufruf neu auf. Bestehende Zieldateien werden abgelehnt. `backup.py` erzeugt konsistente Online-Backups mit Integritätsnachweis.

## Verifizierter Stand

42 Python-Tests, zehn Node-Tests des Drive-Leseflusses, fünf Deno-Tests des API-Testzugangs und sieben eng begrenzte Regressionen aus echten Ergebnissen bestehen. Ein echtes Meeting wurde über n8n auf Hetzner importiert; Wiederholung, Dienstneustart und Upgrade erzeugten keine zusätzliche Aufgabe oder KI-Kosten. PostgreSQL-Restore im getrennten Testcontainer und SQLite-Backup wurden geprüft. Auch der Drive-Lesefluss bestand einen synthetischen Test direkt in n8n, einschließlich leerer Zwischenseite und abgewiesener Versionsänderung. Das passende bestehende Google-Projekt wurde gefunden; der zusätzliche n8n-Client ist mit ausdrücklicher Freigabe erstellt und sein Credential mit den drei HTTP-Leseschritten verbunden. Der HTTPS-Zugang zu n8n samt OAuth-Rückruf ist eingerichtet und verlangt weiterhin eine Anmeldung. Die Browser-Anmeldung und Google-Freigabe sind abgeschlossen. Der echte Drive-Lesetest fand 194 Dateien und las das Finance-Original vom 15.07.; dessen Transkript ist nach dem zusätzlichen Tactiq-Kopf vollständig identisch mit der bisherigen Quelle. Google bestätigt `drive.readonly`; das Refresh-Token läuft im bestehenden Teststatus nach sieben Tagen ab.

Bekannte KI-Testkosten: 7,125607 USD einschließlich der bekannten Wiederholungen, dazu zwei Fehlversuche ohne Usage-Rückmeldung. Die Zahlen sind aus API-Usage und Listenpreisen berechnet, keine Rechnungsbeträge. Eine allgemeine fachliche Präzision/Recall-Quote ist noch nicht nachgewiesen.

## Noch erforderlich vor Produktion

Ein unabhängig geprüfter fachlicher Testsatz; ausreichender Archivkontext mit gemessenem Retrieval-Recall; eindeutige Projekt-/Personenidentitäten und historische Kenntnisnahme; dauerhaft geeigneter Google-Autorisierungsstatus für unbeaufsichtigten Betrieb; vollständige Dateiübernahme mit Pagination und Versionsabgleich; authentifizierte Dashboard-Anbindung an den neuen Zustand; vollständige Bestandsvorschau; externe regelmäßige Backups und geprobte Gesamtwiederherstellung.

Die React-Oberfläche besitzt jetzt eine Entwicklungsansicht unter `/memory-preview` und einen nur im Entwicklungsmodus sichtbaren Eintrag „Arbeitsgedächtnis“. Datum, Vorgang, Suche, Belegverlauf und Originaldialog lesen den isolierten Bestand über einen privaten lokalen Proxy. Der Produktionsbuild enthält den Preview-Zugang nicht; Anmeldung und Veröffentlichung bleiben unverändert. Die HTML-Ansichten bleiben zusätzlich verfügbar. Der Graphify-Graph im Projektwurzelverzeichnis dokumentiert den Ausgangsbestand; die neu hinzugefügten Prototypdateien sind darin noch nicht nachgezogen.

Die anschließende getrennte Originalsicherung ist ebenfalls abgeschlossen: 194/194 Google-Docs-Exporte, rund 7,6 Millionen Zeichen, lokal und auf dem Server mit geprüften Prüfsummen. Alle acht bisherigen Referenztranskripte haben eine eindeutige exakte Drive-Zuordnung. `archive_drive.py` bewahrt vollständigen Export und abgeleiteten Transkriptkörper getrennt; zwei große Quellen liegen oberhalb des bisherigen Verarbeitungslimits. Diese Sicherung erzeugt noch keinen fachlichen Arbeitszustand. Nachweis: [Archivprüfung](evaluation/n8n-drive-archive-result.json).
