# Regelbasierte Relevanz für Working Memory

Dieses lokale Werkzeug markiert Aufgaben als `wichtig`, `standard` oder
`kleinigkeit`. Es löscht, versteckt oder verändert keine Aufgaben und schreibt
keine Produktionsdaten. Nicht angenommene und verworfene Verpflichtungskandidaten
bleiben im Ergebnis separat auffindbar. Die Ausgabe ist ein Vorschlag, kein
Wahrheitsmaßstab: Es gibt bislang keine ausgefüllte Bewertungsliste. Elf
menschliche Aktionen sind kein gelabelter Relevanzmaßstab.

## Ausführung und Grenzen der Schreibfreigabe

Im Verzeichnis dieser README:

```sh
python3 -I -B relevance.py --archive auto --out relevance.jsonl --report report.md
python3 -I -B -m unittest -v
python3 -I -B calibrate.py
```

Der dritte Befehl verwendet ausschließlich ein synthetisches Beispiel. Die
Implementierung benötigt Python-Stdlib und das lokal vorhandene `tar`; sie
installiert keine Pakete und verwendet weder Netzwerk noch Modellaufrufe.
`auto` wählt das Archiv mit der jüngsten Dateimodifikationszeit aus
`~/Library/Application Support/Dashboard Job Backup/archives/dashboard-*.tar.gz`.
Nur `canonical/journal.jsonl` und `canonical/notes.jsonl` werden mittels
`tar -xzOf` gelesen; das Archiv wird nicht entpackt.

Schreibziele der Relevanz-CLI liegen ausschließlich neben diesem Skript. Die
Konsole und `report.md` enthalten nur technische Metadaten, Zählungen und
Verteilungen. `relevance.jsonl` enthält IDs, Status, Klassen, Punkte und generische Merkmale,
aber keine Titel. Titel stehen ausschließlich in `stichprobe.md`; Gründe
verwenden generische Merkmale und Punktebeiträge, keine Zitate oder Meetingtexte.
Die CLI erzeugt diese Stichprobe standardmäßig; `--sample DATEINAME` erlaubt
einen anderen lokalen Dateinamen.

## Rekonstruktion und Beleggrenzen

Die Backend-Logik wird lesend aus
`../../evaluation/sol-operational-release-20261006/backend/` verwendet.
Bestehende Generations- und Ergebnisprüfungen bleiben aktiv. Ersetzende
Generationen werden nicht zusätzlich als Aufgaben gezählt; aktuelle Aufgaben,
Lebenszyklus und menschliche Entscheidungen werden aus dem Journal projiziert.
Bytecode-Schreiben für diese Backend-Imports ist deaktiviert. Die für den
historischen Snapshot fehlende Regeldatei wird im Prozess auf die vorhandene
Originalquelle `../../evaluation/source-corrections.json` gebunden; kein
leeres Ersatzregelwerk wird verwendet.

Das echte Archiv hat direkte Journal- und Notizdatensätze; der beschriebene
`record_json`-Umschlag wird zusätzlich unterstützt. Notizen bleiben eine
separate Archivquelle und werden nicht ungeprüft als weitere aktuelle Aufgaben
gezählt. Wissensbeobachtungen vom Typ Verpflichtung ohne projizierte Aufgabe
erscheinen als `record_type=candidate`. Fakten werden nicht zu Aufgaben.
Abgewiesene/abgebrochene Aufgaben und Kandidaten werden erhalten. Aufgaben und
Kandidaten haben separate Verteilungen; das 80-Prozent-Kriterium gilt für die
projizierten Aufgaben insgesamt.

Offen/wartend/erledigt entsprechen dem tatsächlichen Aufgabenstatus
`open`/`waiting`/`done`; eine fremde offene Aufgabe wird nicht allein wegen ihrer
Dashboard-Gruppe als wartend gezählt. Weitere Status bleiben separat sichtbar.

## Regeln, Konfiguration und Annahmen

`score(task, context)` und `extract_features(task, context)` sind reine
Funktionen. Kontext enthält Konfiguration, Stichtag und belegte Themenstatistik;
die Bewertung liest weder Dateien noch die Uhr. Die CLI stellt den Kontext
bereit. Punkte sind die Summe aus Merkmalswert mal Gewicht, gerundet auf vier
Dezimalstellen. Ab der unteren Schwelle gilt `standard`, ab der oberen
`wichtig`; darunter gilt `kleinigkeit`. Gleichheit gehört zur höheren Klasse.
`config.json` enthält Gewichte, Schwellen, Sättigungsgrenzen und Kommentare.
Fehlende Merkmale tragen null bei, auch fehlende Verpflichtungsstärke.

Verwendet werden Besitzeridentität, belegte Verpflichtungsstärke,
Fristvorhandensein und sicher bestimmbare Nähe, begrenzte Ereignis- und
Meetingzahlen, aktive Aufgaben und letzte Aktivität im Thema, belegte
Personenzahl, Claim-Länge und Konkretheit, schwache Verbsignale sowie Alter
seit letzter belegter Aktivität. Themen werden nur über bestehende IDs
zugeordnet; keine neue semantische Zusammenführung. Meetings zählen anhand
der Quellidentität, nicht anhand der Anzahl ihrer Versionen. Personen werden
nicht aus freiem Text erfunden.

Eine textuelle Frist belegt Vorhandensein, aber nicht zwingend ein Datum.
Relative oder unvollständige Ausdrücke erhalten ohne sichere Auflösung keinen
Nähebonus. Unbekannter Besitzer ist neutral. Status allein senkt die Relevanz
nicht: erledigte Aufgaben können wichtig gewesen sein. Länge, Verben und
Artefaktnennungen sind schwache Hinweise, keine semantische Prüfung. Wiederholte
Erwähnung beweist keine Bedeutung. Sättigung begrenzt diese Effekte.

## Spätere Kalibrierung

```sh
python3 -I -B calibrate.py \
  --ratings ../../evaluation/poc-tiered-reconcile-20261012/m1-bewertung/aufgaben-bewertung.md \
  --scores relevance.jsonl
```

Die vorhandene Tabelle definiert `W=wichtig`, `K=Klacks`, `U=unklar`.
`U` und leere Bewertungen werden ausgeschlossen; `U` ist kein Label für
`standard`. Verknüpfung erfolgt ausschließlich über `task-id` in den
HTML-Kommentaren, nicht über Titel oder Zeilennummern. Fehlende bewertete IDs
werden gezählt und sperren den Rastersuchvorschlag. Doppelte widersprüchliche
Labels und ungültige Tabellen führen zu einer inhaltsfreien Fehlermeldung.

Ausgegeben werden Übereinstimmung und Konfusionsmatrix. Unter 30 verwertbaren
Labels gibt es ausschließlich Metriken und einen Hinweis, keinen Vorschlag.
Bei ausreichend vielen W- und K-Labels sucht das Werkzeug ein kleines Raster:
je Schwelle −2/−1/0/+1/+2 und jeweils ein Gewicht ×0,75/1/1,25.
Es maximiert zunächst den Mittelwert der klassenweisen Trefferquoten und dann
die gesamte Übereinstimmung; Gleichstände bevorzugen geringe Änderungen.
Es ändert `config.json` nicht automatisch. Die Messung auf denselben Labels
ist keine unabhängige Güteprüfung. Für `standard` fehlt in dieser Liste ein
positives Ziel-Label; dessen Qualität ist damit nicht bestimmbar. Eine spätere
ausdrücklich um `standard` erweiterte Bewertungsdefinition benötigt einen
angepassten Parser. Gespeicherte Merkmale erlauben Gewicht-/Schwellenänderungen;
geänderte Extraktionsparameter erfordern einen neuen Archivlauf.

## Einbindungsvorschlag und Rückweg

Ein Digest oder Auftragspaket kann ID, Klasse, Punkte und generische Gründe als
zusätzliches Tag aufnehmen. Eine Review-Reihenfolge kann `wichtig` vor
`standard` und `kleinigkeit` sortieren. Alle Klassen und verworfenen Kandidaten
müssen weiterhin auffindbar sein; eine automatische Ausblendung oder Löschung
ist nicht Teil dieses Werkzeugs. Eine produktive Integration ist nicht erfolgt.

Die drei Ergebnisdateien lassen sich entfernen und mit dem obigen Befehl neu
erzeugen. Für denselben Archivstand und Stichtag kann der Archivpfad explizit
mit `--archive` und der Stichtag mit `--as-of` angegeben werden. Das ersetzt
keinen Datenwiederherstellungsnachweis. Die Schreibgrenze umfasst auch `.git`:
kein Commit, Push, Deployment und keine Änderung globaler Projektdateien.
Es werden keine Hash-/Zeitstempel-Baselines oder Scope-Nachweise angelegt.
Governance-Regeln sind Prozessvorgaben; eine neue technische Laufzeitsperre
wurde nicht eingerichtet.

## Bestandslauf und Stichprobe

Annahmen für diesen Auftrag: „jüngstes Archiv“ bedeutet gemäß vorhandener CLI
die jüngste Dateimodifikationszeit; Bewertungsstichtag ist das lokale Laufdatum.
Die 80-Prozent-Grenze gilt für alle projizierten Aufgaben zusammen, einschließlich
weiterer Status; Kandidaten zählen separat. Eine Grenze von genau 80 Prozent
ist zulässig. Verteilungen nach offen/wartend/erledigt stehen als Anzahlen im
Report, weitere Status bleiben in einer eigenen Spalte sichtbar.

Die acht häufigsten Gründe werden nur für Aufgaben gezählt: ein Vorkommen
pro Aufgabe und Merkmal mit einem von null verschiedenen Punktebeitrag,
einschließlich negativer Beiträge. Gleichstände werden nach Merkmalsname
aufgelöst. „Ohne Frist“ bedeutet weder `due_text` noch `due_date`; ein
unaufgelöster textueller Fristausdruck zählt weiterhin als vorhandene Frist.

Die Stichprobe verwendet `random.Random(42)` in der Klassenreihenfolge
`wichtig`, `standard`, `kleinigkeit`, jeweils nach ID sortierte Grundgesamtheiten
und zehn Zufallsziehungen ohne Zurücklegen. Bei weniger als zehn Aufgaben
werden alle ausgewählt. Sie dient ausschließlich der späteren Sichtprüfung
durch den Nutzer. Bis zur Kalibrierung gilt die Markierung als Vorschlag;
eine ausgewogene Verteilung und grüne Tests belegen keine fachliche Güte.

Beim ersten echten Lauf am 2026-10-13 ergaben die Startschwellen 16/36 bei
663 Aufgaben 598 wichtige (90,20 Prozent), 65 standard (9,80 Prozent) und
keine Kleinigkeit. Die 80-Prozent-Grenze war damit verletzt. Alle Aufgaben
besitzen belegte Verpflichtungsstärke: 476 explizite Verpflichtungen und
187 angenommene Anfragen; selbst das Punkteminimum liegt bei 22. Die niedrigen
Startschwellen trennen diesen Bestand deshalb unzureichend.

Die Schwellen wurden gemeinsam um 20 Punkte auf 36/56 angehoben; die Breite
der Standardklasse und sämtliche Gewichte bleiben erhalten. Die untere
Schwelle trennt nun die zuvor niedrig bewerteten 65 Aufgaben ab; die obere
liegt zwischen Median 50 und oberem Punktedezil 67. Damit werden weder
Einzelmerkmale ohne Bewertungsmaßstab umgewichtet noch gleich große Klassen
erzwungen. Dies ist eine begründete Verteilungsanpassung, keine Gütekalibrierung.
Der Schwellen-Test prüft weiterhin beide Grenzgleichheiten und Werte knapp
darunter anhand der konfigurierten Schwellen statt historischer Startwerte.
Rückweg für diese Anpassung: in `config.json` die Schwellen auf 16/36 setzen
und Lauf sowie Tests wiederholen; die frühere Verteilung verletzt jedoch
das aktuelle 80-Prozent-Kriterium.

Abgeschlossener Bestandslauf am 2026-10-13 gegen
`dashboard-20261012T155114Z.tar.gz`: 663 Aufgaben, davon 214 wichtig
(32,28 Prozent), 384 standard (57,92 Prozent), 65 kleinigkeit (9,80 Prozent).
Der Wiederholungslauf dauerte 107,93 Sekunden; keine Klasse überschreitet
80 Prozent. 93 Kandidaten sind separat erhalten. `report.md` enthält
Statusverteilungen, Mittelwert/Median, Fristanteile und die acht häufigsten
Gründe; `stichprobe.md` enthält zehn Aufgaben pro Klasse, insgesamt 30.

Nach dem Wiederholungslauf bestanden mit `python3 -I -B -m unittest`
20 von 20 Tests. Zusätzlich wurden die Reportzahlen gegen die JSONL-Daten,
die Stichproben-IDs gegen die Seed-42-Auswahl, Punkte und Gründe sowie die
Existenz aller drei Ausgabedateien geprüft. Die JSONL-Daten enthalten keine
Titel. Die genannten Altlasten waren nicht vorhanden; alle Python-Aufrufe
verwendeten `-I -B`. Fachliche Sichtprüfung und Kalibrierung bleiben offen.
