# Offline-Auftragspakete aus dem Arbeits-Memory

Der Generator erstellt kompakte Markdown-Auftragspakete mit YAML-Front-Matter.
Er verwendet ausschließlich Stdlib und die vorhandene lokale Rekonstruktion
unter `../../evaluation/sol-operational-release-20261006/backend/`.
Archivlesen erfolgt mit `tar -xzOf` als Stream, ohne Entpacken. Die Projektion
liegt im RAM. Es gibt keine Netzwerk-, API- oder Modellaufrufe.

## Verwendung

Im Verzeichnis `working-memory/tools/handover/`:

```sh
python3 -I -B handover.py --archive auto --task '<ID oder eindeutiger Suchtext>' --out out/einzelpaket.md
python3 -I -B -m unittest
python3 -I -B prove_real.py
```

`auto` liest das jüngste `dashboard-YYYYMMDDTHHMMSSZ.tar.gz` unter
`~/Library/Application Support/Dashboard Job Backup/archives/`.
Eine explizite Archivdatei ist möglich. Unterstützt werden direkte kanonische
JSONL-Records und Hüllen mit `record_json`. Vorhandene Integritätsprüfungen der
Archivrecords und der akzeptierten Generationen bleiben bestehen.
Die exakte Aufgaben-ID hat Vorrang; mehrdeutige Textsuche wird abgelehnt.
Ausgaben auf der Konsole enthalten Zahlen beziehungsweise abstrakte Fehlercodes.
Inhalte und Aufgabenidentitäten stehen ausschließlich in den privaten Dateien.
Ausgabedateien werden mit Modus 0600 erstellt; vorhandene Dateien werden nicht
überschrieben. Für einen erneuten Batch die fünf eigenen Paketdateien entfernen.

## Format und Auswahl

Jedes Paket hat höchstens 400 Zeichen je physischer Zeile, 150 Zeilen und
20.000 UTF-8-Bytes. Annahme: 20 KB bedeutet konservativ 20.000 Bytes.
JSON-kompatible YAML-Flow-Werte werden ausschließlich zwischen Tokens umgebrochen.
`belege` ist eine YAML-Aufzählung: `B1 Quelle → Aussage`.
Alle übrigen Listen sind lesbare, umgebrochene Flow-Listen.

- Belege: höchstens zwölf unterschiedliche kanonische Quellenadressen,
  direkte Aufgabenquellen zuerst, danach die jüngsten ausgewählten Meetings,
  anschließend weitere Quellen. Die Aussage ist höchstens 200 Zeichen lang.
  Ausgelassene Quellen werden mit „… und N weitere“ ausgewiesen.
- Vorgespräche: höchstens fünf, absteigend nach Datum; je Meeting Titel,
  Datum und eine wörtliche Passage von höchstens 300 Zeichen.
  Gesamtzahlen der Suchtreffer stehen ausschließlich als Zahlen in `trefferzahlen`.
- Verwandte Aufgaben: höchstens acht Titel mit eigener Reife und Quellenbindung.
- Wiederverwendung: höchstens fünf Bestandsangaben; ihre Eignung bleibt
  ohne expliziten Nachweis `unbekannt`.
- Kontext: Thema und höchstens fünf Personen. Meetings werden nur einmal
  im Feld `vorarbeiten_und_vorgespraeche` dargestellt.

Die Rekonstruktion bleibt vollständig im Speicher. Vollständige Verläufe,
Hashes, Quellversionen und doppelte Meetingobjekte werden nicht im Paket
wiederholt; `verlauf_ereignisse` nennt nur die Ereigniszahl. Quellenadressen
behalten Archivname, kanonischen Member und Zeilennummer. Assertionen verwenden
`B1` bis `B12`; bei ausgelassenen Beleglisteneinträgen bleibt die erste direkte
Quellenadresse erhalten. Weitere Quellen je Aussage werden numerisch gezählt.

Lange Texte werden als wörtliche Präfixe mit „…“ und `gekuerzte_zeichen`
ausgegeben, niemals als erfundene Zusammenfassung. Whitespace wird normalisiert.
Aliaslisten sind auf zwölf Begriffe begrenzt; ausgelassene Begriffe werden gezählt.
Annahme: optionale Detailmetadaten dürfen zugunsten des Arbeitskerns entfallen.
Feste Textbudgets 240/300, 140/200 und 80/120 Zeichen (Arbeitskern/Passage)
werden der Reihe nach auf die Gesamtgrenzen geprüft. Ausgewählte Einträge und
Pflichtfelder werden dabei erhalten; nicht darstellbare Pakete scheitern mit
`E_SIZE`. Die Front-Matter enthält keine vollständige Archivkopie.

## Pflichtfelder und Bedeutung

Erhalten bleiben `worum`, `naechster`, `fertig_wenn`, `art`, `bearbeitungsweg`,
`scope`, `wiederverwendung`, `alias_begriffe`, `kontext`,
`vorarbeiten_und_vorgespraeche`, `offene_fragen`, `abnahme`, `belege` und `reife`.
Jede dargestellte Aussage hat `wert`, `reife` und `belege`; zusätzlich bildet
`reife` jeden dargestellten Aussagepfad auf seinen Status ab.
Nicht belegbare fachliche Angaben lauten `unbekannt`. Art, Bearbeitungsweg und
Suchzuordnungen bleiben deterministische Annahmen, keine Ausführungsfreigaben.
Die Schlüsselwortregeln stehen ausschließlich in `RULES` in `handover.py`.
Explizite Aufgabenfelder beziehungsweise taskgebundene Labels werden mit ihrem
Nachweis übernommen. Eine allgemeine Zusage erzeugt keine Fertig-Bedingung.

`belegt` bedeutet im gesicherten Memory enthalten, keine fachliche Wahrheit,
keine Live-Verifikation und keine menschliche Abnahme. `keine gefunden` ist nur
bei einer ausgeführten Suche belegt; ein nicht bestimmbarer Zeitstand bleibt
`unbekannt`. Zugriff und Eignung gefundener Artefakte werden nicht behauptet.
Das Zielbild ist [M4/B7](../../../archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md).

## Batch, Prüfung und Stand

`prove_real.py` wählt fünf unterschiedliche offene Aufgaben, neueste zuerst.
Verschiedene Themen werden bevorzugt; Annahme: erforderlich sind unterschiedliche
Aufgaben-IDs, keine fünf disjunkten Themen. Ein Batch lädt das Archiv einmal und
schreibt `out/paket-01.md` bis `out/paket-05.md`. Die Messungen lesen anschließend
die tatsächlichen Dateien. Reifezahlen zählen ausschließlich die dargestellten
Assertionen einmal, nicht die vollständigen internen Rekonstruktionsobjekte.

Abschlusszahlen: zuerst bestandene/gesamte Tests; danach je Zeile Paketnummer,
Zeilen, Bytes, längste Zeile, belegt, Annahme, unbekannt.
Die synthetischen Tests prüfen Rekonstruktion, Quellenbindung, unbekannte
Pflichtfelder, Kürzungszählung, Belegreihenfolge, Limits und parsebare Flow-Werte.
Der Stand dieses Umsetzungsauftrags ist lokal; keine Änderung von Git-Metadaten,
kein Push und kein Deployment innerhalb dieses Mandats.
Die vorhandenen Kopien unter `recovery/` bilden keinen vollständigen Rückweg
für die übernommene Generatorversion. Ein vollständiger Restore ist nicht geprüft.
Eine Lieferung über OneDrive, Git oder E-Mail sowie menschliche Rückfragefreiheit
bleiben außerhalb dieses lokalen Generierungsnachweises.

Lokaler Prüfstand: 32/32 Tests bestanden. Fünf offene Aufgaben wurden tatsächlich
generiert; die Dateien enthalten 55–59 Zeilen, 12.202–12.583 Bytes und
höchstens 400 Zeichen je Zeile. Die benannten Altlasten wurden anschließend entfernt.

## Beleggebundene Synthese v1 (2026-10-13)

`synthesize.py` ergänzt den vorhandenen Generator um einen prüfbaren
Auftragsentwurf. Die lokale Vorbereitung und alle Tests verwenden ausschließlich
Stdlib und `python3 -I -B`, synthetische Fixtures und Mock-Transport.
Der lokale Auftrag umfasst keinen Modellaufruf und keine Serverausführung.

### Lokal vorbereiten und prüfen

`select_synth_inputs.py` lädt das jüngste Dashboard-Archiv mit dem bestehenden
Streaming-Leser einmal in den Speicher und liest `../relevance/relevance.jsonl`.
Es wählt fünf unterschiedliche offene Aufgaben mit Klasse `wichtig`, je einem
anderen Thema und Frist oder mindestens drei verwandten Aufgaben. Gleb wird
bevorzugt. Die ausgewählten Eingaben liegen in `synth/synth-input-01.json` bis
`synth/synth-input-05.json`. Jede enthält die Aufgabe, Belege und den Beleg-Block;
Auswahlkriterien und Kürzungszahlen stehen in derselben Datei.

```sh
python3 -I -B select_synth_inputs.py
python3 -I -B test_synthesize.py
python3 -I -B synthesize.py synth/synth-input-0[1-5].json --max-usd 1.00 --results synth/synth-dry-run.jsonl
```

Die Auswahl überschreibt vorhandene Eingaben nicht. Der erste Befehl ist nur
für eine neue Auswahl nötig; die fünf Eingaben sind bereits erzeugt. Annahmen:
`open` bedeutet offen; `matter_id`, ersatzweise Thema/Betreff, definiert ein
Thema. Verwandtschaft übernimmt die vorhandene Generatorregel (gleiches Thema,
gleicher Besitzer oder Begriffsüberlappung), nicht eine neue fachliche Bewertung.
Ein vorhandenes Fristfeld gilt als Frist; Auswahlklasse und Besitzerpräferenz
kommen aus dem vorhandenen Relevanz-Snapshot. Archivstand und Relevanzstand
werden nicht zu aktuellen Produktivdaten erklärt.

### Serverlauf und Rückgabe

`transfer/synth-bundle.tar` enthält ausschließlich `synthesize.py`, die fünf
Eingaben und `run_on_server.sh`, jeweils ohne externe Python-Abhängigkeiten.
Auf dem Server in ein frisches privates Verzeichnis entpacken und dort starten:

```sh
tar -xf synth-bundle.tar
sh run_on_server.sh
```

`OPENAI_API_KEY` muss bereits in der Umgebung stehen. Das Skript liest keine
Credential-Dateien, setzt `umask 077` und schreibt nach `synth.log`. Zunächst
läuft der Dry-Run nach `synth-dry-run.jsonl`; nur bei Exitcode 0 folgt
`--execute --max-usd 1.00 --results synth-results.jsonl`. Vorhandene Log- oder
Ergebnisdateien sperren einen erneuten Skriptlauf. Ergebnisse samt vollständigen
Rohantworten und Fehlern zurück in dieses lokale Verzeichnis kopieren.

```sh
python3 -I -B synthesize.py synth/synth-input-0[1-5].json --render --results synth-results.jsonl
```

Der Renderlauf bindet Ergebnisse an Aufgabe und tatsächlich verwendete Belege;
Dateinamen allein genügen nicht. Markdown entsteht neben jeder Eingabe.
Vorhandene Markdown-Dateien werden nicht überschrieben. Ergebnisdateien werden
angehängt, deshalb für getrennte lokale Prüfungen unterschiedliche Dateinamen
verwenden. `ground_error` enthält die bereinigte Synthese und die Verstoßzahl,
gilt aber nicht als freigegebenes Renderresultat; `--render` verwendet nur
`completed`. Rohresultate bleiben zur Prüfung erhalten. Es gibt keine
automatischen Wiederholungen bei Transport-, Inhalts- oder Groundingfehlern.

### Beleg- und Kostengrenzen

`belegt` bedeutet direkt im gesicherten Beleg gesagt. `annahme` bedeutet eine
Schlussfolgerung mit IDs und einer Begründung; `unbekannt` bedeutet fehlende
Evidenz. Die Zusammenfassung ist ein Entwurf zur Nutzerabnahme, keine fachliche
Wahrheit oder Ausführungsfreigabe. IDs, Zitate und formale Regeln sind maschinell
geprüft; die inhaltliche Ableitung und tatsächliche Eignung vorhandener Berichte,
Modelle oder Vorlagen prüft der Nutzer. Wiederverwendung braucht einen im Beleg
wörtlich genannten Artefaktnamen und ein passendes wörtliches Zitat.

Der Belegtext bleibt wörtlich und wird auf 600 Zeichen pro Beleg begrenzt,
der Block auf 12.000 Zeichen. Kürzungen und ausgelassene Belege werden gezählt.
Die Prompt-Regeln behandeln Aufgabe und Belege als Daten, nicht als Befehle.
Ungültige IDs, fehlende erforderliche IDs, falsche Zitate, leere Aussagen und
fehlende Begründungen führen zu gezählten Verstößen und `unbekannt`.
Die Ausgabe enthält YAML-Skalare und lesbare Abschnitte, maximal 400 Zeichen
je Zeile, 150 Zeilen und konservativ 20.000 UTF-8-Bytes (Annahme für 20 KB).
Darstellungskürzungen werden kenntlich gemacht; vollständige Eingaben und
Synthesen bleiben in den JSON-Dateien.

Der Payload entspricht dem lokal geprüften Responses-Muster: `gpt-6.1-sol`,
`service_tier: default`, Reasoning `medium`, striktes `json_schema`, expliziter
Cache ohne Breakpoints. 6.144 Ausgabetokens enthalten auch Reasoning.
Preise laut Auftrag in USD pro Million Tokens: Input 2,00, Cached 0,10,
Cache-Schreiben 2,50 und Output 10,00. Cache-Schreiben ist ein eigener Anteil
innerhalb der gesamten Inputtokens. Reserviert werden konservativ die
UTF-8-Bytes des gesamten serialisierten Payloads plus 512 Tokens und alle
Ausgabetokens, mit Cache-Schreibpreis für den ganzen Input. Dies ist eine
konservative technische Reservierung, keine vom Anbieter garantierte Rechnung.
Vor Beginn wird die gesamte Reservierung gegen den Deckel geprüft; unbekannte
oder widersprüchliche Usage beziehungsweise überschrittene Reservierung stoppen
weitere Aufrufe. Die tatsächlichen Kosten werden separat protokolliert.

### Lokaler Stand und Rückweg

Version: Synthese v1, lokal geprüft; API-, Server- und menschliche Abnahme sind
nicht ausgeführt. Der ursprüngliche `handover.py` bleibt der Generator.
Dieser Auftrag schreibt keine Git-Metadaten. Rückweg: die neue Synthese-Sektion
in dieser README entfernen und die neu erzeugten Synthese-Dateien sowie
`synth/` und `transfer/` entfernen; den bestehenden Generator weiterverwenden.
Ein Serverlauf oder seine Daten werden dadurch nicht rückgängig gemacht.
Es werden keine Außenverzeichnis-, Hash-, Zeitstempel- oder Scope-Baselines
angelegt oder als Nachweis beansprucht.

Prüfstand Synthese v1: 60/60 synthetische Tests bestanden; Protokoll:
`synth/test-results.txt`. Auswahlprüfung: 5/5 offen, 5/5 wichtig, fünf
unterschiedliche Aufgaben und Themen, 5/5 Besitzer Gleb, 5/5 erfüllen die
Frist-/Verwandtschaftsbedingung. Die größten Belegtexte haben 600 Zeichen;
der größte gespeicherte wörtliche Block hat 9.118 Zeichen.
Der finale Fünfer-Dry-Run (`synth/synth-dry-run-final.jsonl`) reserviert
0,528031 USD bei 1,00 USD Deckel, 0 API-Aufrufen und 0 Fehlern.
Das Bundle hat sieben reguläre Dateien und 143.360 Bytes; sein entpackter
Standalone-Dry-Run liefert dieselben Zahlen und Exitcode 0. Shell-Syntax: 0.
Ein frischer unabhängiger Reviewer hat Grounding, Kosten, Rendering und
Offline-Tests nach den gezielten Korrekturen akzeptiert. Dies belegt weder
live ausgeführte Synthesequalität noch eine automatisch erzwungene Laufzeitsperre.
Bei lokalen Aufrufen mit privaten Belegen ebenfalls vorher `umask 077` setzen.
