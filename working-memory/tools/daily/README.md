# Lokaler Tageslauf M5

Dieses Werkzeug bereitet täglich einen lokalen Digest, eine Relevanzliste und
höchstens fünf Übergabepakete vor. Es liest ein gesichertes Dashboard-Archiv,
sendet nichts und verändert weder Dashboard noch Archiv. Dieser Auftrag ist ein
lokaler M5-Meilenstein; er behauptet keine menschliche Abnahme von M1–M4 oder
der vollständigen M5-Phase. Python 3.10+ unter macOS, ausschließlich Stdlib.

## Betrieb

Aus dem Repository:

```sh
python3 -I -B working-memory/tools/daily/run_daily.py --date 2026-10-13 --out working-memory/tools/daily/out/2026-10-13
python3 -I -B working-memory/tools/daily/run_daily.py
python3 -I -B working-memory/tools/daily/test_daily.py
```

Ohne Datum gilt das aktuelle Kalenderdatum in **Europe/Berlin**. Ohne `--out`
gilt `daily/out/<Datum>`. `--step-timeout` setzt die echte Ausführungsgrenze pro
Schritt, standardmäßig **600 Sekunden**. `--archive /absoluter/Pfad` ist für
explizite lokale Eingaben und synthetische Prüfung verfügbar.

Vor einem geplanten Lauf um **07:30 Europe/Berlin** muss der bestehende
Mac-Archiv-Pull ein vollständiges neues Archiv unter
`~/Library/Application Support/Dashboard Job Backup/archives/` bereitgestellt
haben. Die lexikografisch größte reguläre Datei `dashboard-*.tar.gz` gewinnt;
das entspricht dem bestehenden UTC-Zeitformat der Backup-Namen. Kopier-Mtime
entscheidet nicht die Auswahl. Ohne Archiv: abstrakte Kennzahlen, Exitcode **2**.
Der Runner richtet weder Pull noch Zeitplan ein. Nur einen Runner gleichzeitig
betreiben; parallele Schreibläufe sind nicht synchronisiert.

## Ausgabe und Zustandsvertrag

Alle Schreibpfade sind auf dieses Verzeichnis begrenzt. Neue Dateien werden
atomisch mit privaten Rechten geschrieben. Die drei kanonischen JSONL-Mitglieder
werden in **einem** sequenziellen gzip/Tar-Durchlauf gelesen; keine Extraktion,
kein Projektionscache auf Platte. Der importierte Handover-Vertrag erzeugt die
RAM-Projektion und ihre Quelladressierung. Die importierten Reminder- und
Relevanzhelfer verwenden diesen Arbeitsstand; Reminder-Metadaten einschließlich
relativer Fristbezüge kommen zusätzlich aus dessen reiner Journalprojektion.
Notizen werden nach kanonischer Prüfung an diesen Helper übergeben.

| Datei | Inhalt / Grenze |
| --- | --- |
| `digest.md` | Importierter Reminder-Digest, einschließlich Sperrfristen |
| `relevance.jsonl` | Alle projizierten Aufgaben und separate Verpflichtungskandidaten; regelbasierte Klassen und Gründe |
| `uebersicht.md` | Höchstens 60 Zeilen: Klassen, überfällige Aufgaben, Top 10 wichtige Aufgaben mit Frist/Stillstand, neue/geänderte Aufgaben, Paketlinks |
| `pakete/paket-NN.md` | Höchstens 5; bestehender Generator: höchstens 150 Zeilen, 20.000 UTF-8-Bytes und 400 Zeichen pro Zeile |
| `delivery.json` | Betreff, E-Mail-Text aus Digest höchstens 3.000 Zeichen, Push höchstens 140 Zeichen; `sent=false` |
| `run.json` | Archivname, Version-/Vertragslabels, Schrittstatus und Sekunden, Gesamtdauer, dargestellte Digest-Einträge, Zähler, Delta-IDs, Paketauswahlbelege |
| `state.json` im Ausgabeverzeichnis | Beleg des Zustands für diesen Versuch |
| `daily/state.json` | Verzeichnisübergreifender letzter Versuch/Erfolg, strukturierter Aufgabenvergleich, Aufgabe/Regel-Sperrfristen |

Die Ausgabeversion ist `daily-v1`; die anderen Versionsangaben sind ausdrücklich
Import-Vertragslabels und die verwendete Relevanzkonfiguration, keine behaupteten
unveränderlichen Quelldatei-Hashes. Die bestehenden kanonischen Datensatz-
Integritätsprüfungen bleiben erhalten. Es werden keine Außenverzeichnis-
Baselines, Unverändertheitsnachweise oder Hashlisten erzeugt.

**Paketwahl:** Eine Aufgabe muss neu oder fachlich verändert gegenüber dem
letzten **erfolgreichen** Lauf, offen (`open` oder `waiting`) und als `wichtig`
klassifiziert sein. Zusätzlich braucht sie eine eindeutig bestimmte Frist bis
einschließlich Auswertungstag + 14 Tage (überfällige Fristen zählen mit) **oder**
den positiv festgestellten Stillstand nach der bestehenden Reminder-Regel.
Unklare/fehlende Frist, unbekanntes Änderungsdatum oder fehlende Klasse begründen
keine Ausnahme. Kandidaten gelten nicht als offene Aufgaben. Sortierung nach
Frist, danach stabiler ID; höchstens fünf. `package_selection` unterscheidet
positive Eignung, unbekannte Evidenz, negative Gründe, unveränderte Aufgaben und
Mengenbegrenzung. Vollständige Delta-IDs stehen in `run.json`; die Übersicht
zeigt bis zu 20 davon und benennt den verbleibenden Zähler.

## Wiederholung, Ausfälle und Beleggrenzen

Ein erfolgreich gespeicherter Archivstand mit weiterhin vorhandenen Pflicht-
Artefakten wird wiederverwendet. Identität: Archivname, Größe und Mtime; keine
Dateiinhalts-Hashliste. Derselbe Tag und Archivstand schreibt **keine** Dateien
neu, auch keine Dauern oder Zustandsdaten. **Ohne neues Archiv erfolgt auch beim
Datumswechsel kein Neuaufbau**: Der Runner verweist intern auf das ursprüngliche
Ausgabeverzeichnis. Digest und Übersicht behalten ihren ursprünglichen
Bewertungsstand; sie behaupten keine neue Tagesauswertung. Ein neuer `--out`-
Ordner wird bei diesem Cache-Treffer nicht angelegt. Beschädigter Zustand wird
nicht still zurückgesetzt. Fehlender Erfolgsbeleg oder fehlendes Pflichtartefakt
sperrt das Überspringen und führt zur erneuten Berechnung.

Archivlesen läuft in einem separaten Prozess mit aktiver Deadline. Einzelne
Importschritte laufen in kurzlebigen Kindprozessen mit aktiver Deadline; ein
überlanger Kindprozess wird beendet, die gemeinsame RAM-Projektion bleibt für
die anderen Schritte verfügbar. Fehler erscheinen abstrakt in `run.json`;
feasible Schritte laufen weiter. Ohne Projektion bleiben abhängige Schritte
explizit übersprungen, die Übersicht bleibt als unbekannter Stand möglich.
Ohne Relevanz gibt es keine Paketauswahl, ohne Digest keinen Delivery-Entwurf.
Auch Ausgabefehler bei Übersicht und Delivery werden isoliert vermerkt.

Exitcode **0** bedeutet sämtliche lokalen Schritte erfolgreich; **1** bedeutet
Teilergebnis oder Fehler. Fehlgeschlagene Läufe aktualisieren nur den letzten
Versuchsstatus, niemals den erfolgreichen Archivbeleg, den Aufgabenvergleich
oder neue Sperrfristen. Bei erneutem/neuerem Lauf im selben Ausgabeverzeichnis
werden ausschließlich nicht mehr aktuelle Runner-Dateinamen entfernt, damit
keine älteren Pakete/Digests als aktuelles Ergebnis erscheinen. Zustandsdateien
werden einzeln atomisch ersetzt; ein Abbruch vor dem gemeinsamen Erfolgsbeleg
kann eine erneute Berechnung erlauben. Cache-Existenz ist kein erneuter
Inhaltsintegritätsnachweis. Sperrfristen beziehen sich auf erfolgreiche lokale
Erzeugung, nicht auf tatsächliche Zustellung.

## Zustellung vorbereiten

Für einen später separat autorisierten Zeitplan ist vorgesehen: täglich 07:30
Europe/Berlin nach erfolgreichem Mac-Archiv-Pull den zweiten Aufruf ausführen.
Ein separat autorisierter Gmail-Entwurf kann `delivery.json` verwenden; Empfänger
und konkrete Entwurfsaktion sind vorher festzulegen. Compliance für Gmail oder
Scheduled Tasks ist vor Einrichtung bzw. Entwurfsaktion zu klären. Dieser Auftrag erstellt
nur die lokale Vorbereitung, keinen Scheduled Task und keinen Gmail-Entwurf,
und versendet weder E-Mail noch Push. Ein Entwurf ist keine Zustellung und keine
menschliche Abnahme.

## Lokale Prüfung und Rückweg

Das Testpaket prüft die offene Frage, ob Delta-/Sperrfrist-/Cacheentscheidungen,
Fehlerisolation, tatsächliche Timeouts, Auswahlvoraussetzungen und Limits den
Auftrag erfüllen. Es benutzt synthetische Miniarchive und Schritt-Mocks,
entbehrliche Dateien ausschließlich innerhalb `daily/`, ohne Netzwerk, API,
Secrets, externe Pakete oder Produktivzugriff. Ein grüner Lauf belegt lokale
Funktionsprüfung; echter Archivlauf und unabhängiges GOAL_GATE-Review bleiben
separate Lead-Nachweise. Git-Versionierung und äußere Statusdokumente sind durch
die ausdrückliche Schreibgrenze nicht Teil dieses Pakets.

Rückweg: Aufrufe/den gegebenenfalls später autorisierten Zeitplan stoppen und
**ausschließlich** `working-memory/tools/daily/` entfernen. Beispiel aus dem
Repo: `rm -rf -- working-memory/tools/daily`. Dieser Rückweg entfernt Code und
lokale Ergebnisse einschließlich Sperrfristen; er betrifft weder Geschwister-
werkzeuge noch Archive oder Produktion. Eine spätere Neuinstallation beginnt
mit frischem Zustand und kann Meldungen wiederholen. Keine Wiederherstellung
externer Systeme wird behauptet.

Lokaler Prüfstand vom 13.10.2026: 45/45 synthetische Tests bestanden. Der echte
Archivlauf und seine Cache-Wiederholung endeten jeweils mit Exitcode 0;
sechs Schritte waren erfolgreich. Der unabhängige GOAL_GATE-Reviewer hat
diesen lokalen Meilenstein ohne offene Pflichtblocker akzeptiert.
Die gemessenen Zahlen stehen in [validation.json](validation.json) und
[run.json](out/2026-10-13/run.json). Die externe Gesamtdauermessung umfasst
auch Prozessstart und abschließende Dateischreibung.

Numerisches Abschlussformat des Leads, in dieser Reihenfolge: (1) Tests
bestanden/gesamt; (2) Sekunden `archive`, `reminders`, `relevance`, `handover`,
`overview`, `delivery`; (3) Aufgaben, `wichtig`, `standard`, `kleinigkeit`;
(4) dargestellte Digest-Einträge (`digest_entry_count`), Paketanzahl;
(5) Ausgabeordnerbytes (Gesamtordner, danach Unterordner `pakete`);
(6) gemessene Gesamtdauer (`total_seconds`, ergänzend
externe Prozessmessung einschließlich der letzten Metrik-Dateischreibung). Das sind gemessene lokale Kennzahlen,
keine Schätzung einer menschlichen oder produktiven Abnahme.

Lokaler Builder-Prüfstand vom 13.10.2026: **45/45** synthetische Tests bestanden,
Aufruf `python3 -I -B working-memory/tools/daily/test_daily.py`, gemeldete
Gesamtlaufzeit **0,628 Sekunden**. Darin enthalten: reale synthetische
Mini-Archivverarbeitung mit importierter Paketerzeugung, geprüftes Weiterlaufen
der Relevanz nach tatsächlich beendetem Reminder-Timeout und die atomaren
Dateischreibpfade. Echter Archivlauf und unabhängige Abnahme sind oben separat
belegt; sie werden nicht aus der synthetischen Testzahl abgeleitet.
