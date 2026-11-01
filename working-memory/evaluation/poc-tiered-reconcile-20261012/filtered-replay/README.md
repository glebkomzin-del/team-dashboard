# Gefiltertes Sol-Replay

## Restlauf Run 2 — Stand 2026-10-13

Der erste reale Lauf ist in `results-filtered-run1.jsonl` und `server-run1.log` erhalten. Er hatte einen erfolgreichen Aufruf, stoppte aber wegen unbekannter Kosten. Die folgenden älteren Abschnitte beschreiben den historischen Paketstand vor diesem Fix. Originalauswahl, ursprüngliches Transferarchiv und Serverskript bleiben unverändert.

Ursache im unveränderten ursprünglichen Bundle: `replay_common.py:66-67` lieferte bei positiven Cache-Schreib-Tokens `None`; `run_filtered.py:329` übernimmt diese Kostenermittlung, der Unknown-Pfad in Zeilen 357-359 beendet den Lauf konservativ. Die Produktionsvorlage `../../sol-operational-release-20261006/backend/call_budget.py` validiert Cached-/Write-Zähler, zieht beide vom normalen Input ab und rundet die Summe mit `ROUND_CEILING`. Run 2 berechnet Standardinput 2,00, Cached Input 0,10, Cache-Schreiben 2,50 und Output 10,00 Mikro-USD je Token. Fehlende oder ungültige Usage bleibt unbekannt und stoppt nach voller Reservierung. Reasoning ist bereits im Output enthalten.

Produktionsform: Top-Level `prompt_cache_options: {"mode": "explicit"}`, ohne Breakpoints, für gefilterte und Kontrollaufrufe. Positiv belegt durch die einzeln temporär extrahierte `runtime/openai_provider.py:149-155` im Archiv `~/Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz`, insbesondere Zeile 153, und durch `../../production-cost-20261012/durable_calls.py.patch:9` / `README.md:39`. Es wurde nur diese eine Archivdatei ins vorgegebene Scratchpad extrahiert.

Die vorhandene Usage des ersten Aufrufs ergibt **123539 Mikro-USD (0,123539 USD)**: `(36808-36805)*2 + 36805*2,5 + 3152*10`, aufgerundet. Historische Ergebnisse werden nicht umgeschrieben. `compare_filtered.py` kann diese Kosten bei bestätigter finaler Standard-Usage beim Einlesen ableiten. Identische Ergebnisduplikate werden einmal gezählt; widersprüchliche Ergebnisse derselben `replay_id` werden abgelehnt.

Alle neun verbleibenden Aufrufe benötigen beim Schreibpreis **3,325889 USD** Schätzreserve. Deshalb wurde genau der größte gefilterte Aufruf entfernt, wie beauftragt; die ursprünglichen drei Kontrollen bleiben vollständig erhalten. `selection-summary-run2.json` belegt **8 Aufrufe (5 gefiltert + 3 Kontrolle)**, **2,557724 USD** insgesamt, davon **1,616434 USD** gefiltert und **0,941290 USD** Kontrolle. Gesamtdeckel des Restlaufs: 3,20 USD. Zusammen mit den ermittelten historischen Kosten: 2,681263 USD Schätzreserve. Der entfernte Aufruf war der zuvor vorgesehene Pflichtfall; die ausdrücklich beauftragte Regel „größte gefilterte zuerst weglassen“ hat für diesen Restlauf Vorrang. Seine fachliche Auswertung bleibt offen. Die Zeichen/3,6-Schätzung ist weiterhin eine heuristische Obergrenze, keine Tokenizer-Garantie.

```sh
python3 -I -B select_calls.py --requests selected_requests.jsonl --skip-done results-filtered-run1.jsonl --max-usd 3.20 --output selected_requests-run2.jsonl --summary selection-summary-run2.json
python3 -I -B run_filtered.py --requests selected_requests-run2.jsonl --skip-done results-filtered-run1.jsonl --max-usd 3.20
python3 -I -B -m unittest discover -s . -v
```

`--skip-done` akzeptiert mehrere Pfade und wiederholte Optionen in Auswahl und Runner. Alle vorhandenen gültigen Ergebnisidentitäten, einschließlich bezahlter Fehler, werden übersprungen; ungültige oder widersprüchliche Identitätsfelder verhindern die Ausführung. Das inhaltlich leere `run1-completed.jsonl` enthält die aus dem unveränderten Run-1-Ergebnis abgeleiteten Identitäts-/Statusfelder für die zusätzliche Serversicherung. Der Restplan enthält diese bezahlte Identität bereits nicht mehr. Der Ergebnisvergleich liest nach Rückübertragung von Run 2 beide Dateien; `comparison_requests-run2.jsonl` enthält exakt die neun tatsächlich betrachteten Identitäten (Run 1 plus Restplan), ohne den ausgelassenen Aufruf:

```sh
python3 -I -B compare_filtered.py --requests comparison_requests-run2.jsonl --results results-filtered-run1.jsonl results-filtered-run2.jsonl
```

Transfer: `transfer/filtered-replay-bundle-run2.tar` in ein neues Serververzeichnis entpacken und dort `sh run_on_server_run2.sh` ausführen. Genau fünf ausführungsnotwendige Dateien: Runner, gemeinsame Helfer, Restplan, Run-1-Identitätsmarker und neues Skript. Das Skript protokolliert nach `run2.log`, prüft zuerst offline und startet ausschließlich bei Exitcode 0 mit `--execute --max-usd 3.20 --results results-filtered-run2.jsonl`. Es verlangt `OPENAI_API_KEY` aus der Umgebung und liest keine Credential-Dateien. Bestehende Ergebnisdateien werden wegen exklusiver Neuanlage abgelehnt. Vergleich und Tests sind lokal vorhanden und nicht im Ausführungsarchiv.

Lokal tatsächlich vollständig ausgeführt: **62 Unittests, grün**, einschließlich Mock-Transport und inertem Shell-Mock, in `test-run2-output.txt`. Auswahl und Dry-Run: Exitcode 0, 0 API-Versuche; Nachweise in `select-run2-output.txt`, `dry-run-run2-output.txt` und `run2-verification.json`. Archivinhalt, entpackter Offline-Dry-Run, Shellsyntax, Originalhashes und Außenmetadaten werden separat geprüft. Netzwerk, API und Serverausführung sind nicht Teil dieses Auftrags. Der Bestand ist ohne Git an SHA-256 im Prüfbericht gebunden. Rückweg für spätere Ausführung: ursprüngliches Run-1-Bundle ist erhalten; Ergebnisse niemals löschen oder erneut bezahlen.

Stand: 2026-10-13. Dieses Paket misst später die Wirkung von A=30,k=5 auf gespeicherte Abgleichanfragen, einschließlich Modellrauschen. Entwicklung und Prüfung erfolgen ausschließlich offline mit Python-Stdlib und Mock-Transport. Es wurde kein echter Modelllauf ausgeführt. Meetingtexte stehen ausschließlich in den benötigten JSONL-Daten, niemals in den Konsolenausgaben oder diesem Bericht.

## Ablauf

Alle Befehle im Verzeichnis dieses Pakets ausführen. `python3 -I -B` unterbindet benutzerweite Python-Konfiguration und Bytecode-Dateien. Keine Installation erforderlich.

```sh
python3 -I -B build_filtered_requests.py
python3 -I -B select_calls.py
python3 -I -B run_filtered.py
python3 -I -B -m unittest -v
```

Erst der Mensch führt später auf dem Server den kostenpflichtigen Lauf aus. Das Archiv `transfer/filtered-replay-bundle.tar` in ein eigenes Serververzeichnis entpacken und dort `sh run_on_server.sh` aufrufen. Es enthält ausschließlich `run_filtered.py`, `replay_common.py`, `compare_filtered.py`, `selected_requests.jsonl` und `run_on_server.sh`. `filter-decisions.jsonl` ist für Runner und Vergleich nicht erforderlich; beide lesen die Filtermetadaten aus den ausgewählten Anfragen. Das Skript startet zuerst den Offline-Dry-Run und führt nur bei Exitcode 0 den bezahlten Lauf aus. `run.log` und `results-filtered.jsonl` liegen im entpackten Verzeichnis. Das Skript wird bei der lokalen Prüfung nicht ausgeführt. `OPENAI_API_KEY` muss bereits sicher in der Prozessumgebung gesetzt sein; dieses Paket liest weder Credential-Dateien noch andere Secret-Quellen.

```sh
python3 -I -B run_filtered.py --execute --max-usd 3.50 --results results-filtered.jsonl
python3 -I -B compare_filtered.py --results results-filtered.jsonl
```

## Budget (angepasst): Kontrolldeckel 0,95 USD, autorisiert durch den Auftraggeber

Die ausdrückliche menschliche Budgetänderung vom 2026-10-13 hebt die bisherige Budgetblockade auf. Die Auswahl enthält 7 gefilterte und 3 Kontrollaufrufe: geschätzt 2,390154 USD gefiltert, 0,849032 USD Kontrolle und 3,239186 USD insgesamt. Der gefilterte Deckel bleibt 2,50 USD, der Gesamtdeckel 3,50 USD. Volle Ausgabereserve und vollständig ungekachter Input bleiben unverändert. `select_calls.py` erzeugt einen ausführbaren Plan; der Runner verweigert weiterhin überschrittene Kontroll- oder Gesamtbudgets. Lokal erfolgen ausschließlich Dry-Run und Tests; der tatsächliche Serverlauf ist hier nicht ausgeführt.

Der Standard ohne `--execute` ist ein Offline-Dry-Run. Ergebnisse dürfen nicht überschrieben werden. Für einen neuen menschlich beauftragten Lauf eine neue Ergebnisdatei innerhalb dieses Pakets über die CLI-Option verwenden. Rohantworten und Fehler bleiben vollständig in Ergebnisdateien; Konsolenausgaben enthalten ausschließlich technische Zählwerte. Diese Dateien und das Paket enthalten vertrauliche Eingaben und dürfen nur in der vorgesehenen Serverumgebung liegen.

## Quellen und Annahmen

- Die Struktur und Funktionen von `replay_common.py`, Runner und Vergleich stammen aus `../model-replay/`. Quellvermerke stehen in den jeweiligen Modulen; `source-hashes.json` bindet gelesene Eingaben an SHA-256. Originale bleiben unverändert.
- Filterentscheidungen stammen aus den bereits geprüften `codex-rank/metrics.json`-Zeilen und `selector/RANK-VALIDATION.md`. Der Rang ist die ursprüngliche nullbasierte Position der separaten Produktions-Work-Suche, minimiert über die Beobachtungen. Kein Neuranking und keine gemischte Suchliste. Behalten wird `age <= 30 OR best < 5 OR exact`. Die direkte Transkript-ID-Prüfung war für diese Stichprobe leer; `exact=False` stammt aus diesem Nachweis, nicht aus einer neuen Textsuche. Die archivierte Produktionsrekonstruktion wird nicht erneut ausgeführt, weil die vorhandenen Zwischenergebnisse alle geeigneten Aufrufe abdecken.
- Alias-Identitäten gelten ausschließlich innerhalb eines Aufrufs; die Zuordnung über Job-Präfix und Aufrufindex muss eindeutig sein. Die referenzierte Datei enthält 41 Anfragen; die Rangdatei umfasst 36 Aufrufe mit Beobachtungen. Fehlende Entscheidungen für einen geeigneten Aufruf werden als Fehler behandelt.
- Nur Referenzen in Endform mit mindestens einer tatsächlich genutzten Aufgabe werden ausgewählt. Öffnungsrunden, fehlende Referenzen und unbekannte Work-Slots gelten nicht als `unchanged`. Vier Zwischenrunden enthalten bereits im Original ein leeres `source_index`-Enum; sie sind keine geeigneten Endantworten. Der Pflichtfall `4e7b6e03`, Aufruf 54, W349 wird budgetseitig reserviert.
- `work_index` und W-Alias bleiben stabil. Das äußere Textarray wird konsistent reduziert; der getrennte gepackte Textspeicher unter `metadata.archive_navigation` bleibt unverändert. Promptpräfix und -suffix bleiben bytegleich als Python-Zeichenfolgen erhalten. Der Vergleich validiert die Referenz gegen das Originalschema und die neue Antwort gegen das jeweilige gefilterte beziehungsweise Kontrollschema.
- Alle 41 Anfragen enthalten `request_json.transport.reasoning_effort=medium` und `service_tier=default`. Diese gespeicherte Einstellung hat Vorrang; widersprüchliche Einstellungen sind Fehler. Der dokumentierte Provider-Fallback ist ebenfalls `medium`. Ausgabe wird mit `max(Referenz max_tokens, 16000)` reserviert.
- Preisvorgabe des Auftrags: Standardinput 2,00, Cacheinput 0,10, Ausgabe 10,00 USD/Million Tokens. Für Vorausplanung wird wie im kopierten Harness `ceil((Promptzeichen + Schemazeichen)/3.6)` mit vollständig ungekachtem Input und voller Ausgabe verwendet. Das ist eine **geschätzte** Obergrenze, kein Tokenizer- oder API-Nachweis. Tatsächliche Tokenkosten können die Einzelschätzung überschreiten; der Runner stoppt vor weiteren Aufrufen, wenn die erfassten Kosten beziehungsweise Reservierungen den Deckel verletzen. Ein laufender API-Aufruf kann nicht nachträglich an einem exakten Geldbetrag abgeschnitten werden. Es wird kein Tokenzähl-Endpoint verwendet.
- Gefilterte Auswahl bleibt bei höchstens 2,50 USD Schätzung; drei Kontrollaufrufe verwenden die Originalanfragen der drei kleinsten ausgewählten Aufrufe und bleiben bei höchstens 0,95 USD. Der gemeinsame Runnerdeckel beträgt standardmäßig 3,50 USD. Kontroll- und Filtervariante desselben Aufrufs haben getrennte Ergebnisidentitäten. Inhaltliche Fehler lösen keine Wiederholung aus.

## Bewertung und Grenzen

Lebenszyklus-Recall verlangt dieselbe Aliasidentität **und dieselbe Aktion**, nicht bloß irgendeine Änderung. Alle im gefilterten Katalog verbleibenden Referenzänderungen müssen wiedergefunden werden; keine referenzierte Änderung darf durch den Filter verschwinden. Zusätzliche Flags, Beobachtungsziel, `update` und `kind` werden getrennt gezählt. Die gefilterte Zielübereinstimmung muss mindestens Kontrollübereinstimmung minus zwei Prozentpunkte erreichen. Fehlende, ungültige oder nicht abschließende Ergebnisse und fehlende Kontrollen sind kein positiver Nachweis. Der Vergleich ist ein Referenzvergleich, keine menschliche Bewertung der fachlichen Wahrheit. Drei Kontrollen und eine budgetbegrenzte Teilmenge liefern keine statistische Zuverlässigkeitsgarantie.

Die Stdlib-Strukturprüfung unterstützt den vorhandenen JSON-Schema-Teilumfang, lehnt unbekannte Schlüssel und externe Referenzen ab und ersetzt keine vollständige allgemeine Metaschema-Implementierung. Der echte Providertransport wird durch Mocks geprüft; Serverintegration und reale Modellqualität bleiben bis zum menschlichen Lauf offen.

## Wiederherstellung und Schreibgrenze

Alle neuen Dateien befinden sich in diesem Paket. Rückkehr zum Ausgangszustand: nach Sicherung gewünschter Ergebnisse dieses neu angelegte Verzeichnis entfernen. Keine Git-Befehle, Commits, Installation, Netzwerkzugriffe oder Änderungen an anderen Projektdateien sind Teil des Auftrags. `outside-baseline.json` und die abschließende Verifikation dokumentieren den beobachteten Zustand außerhalb des Pakets; eine vorbestehend nicht lesbare Datei bleibt ausdrücklich außerhalb des Prüfnachweises. Elternverzeichnis-Metadaten ändern sich zwangsläufig durch das Anlegen dieses Verzeichnisses.

## Lokale Nachweise

Budgetanpassung am 2026-10-13: `python3 -I -B -m unittest -v` tatsächlich ausgeführt: **39 Tests, 0.196 Sekunden, OK**, Exitcode 0. Die vollständige unveränderte Ausgabe liegt in `test-output.txt`. Der neue Test prüft den tatsächlichen Auswahlplan ohne Budgetblockade, eine ausschließlich simulierte Ausführung unter dem angepassten Kontrolldeckel, Abbruch bei überschrittenem Deckel und Ablehnung unbekannter oder unzulässig erhöhter Kontrollgrenzen. Ein falsches `feasible`-Flag ersetzt keine Kostenprüfung. Auch der CLI-Dry-Run liefert bei überschrittenem Gruppen- oder Gesamtbudget einen Fehlerexitcode, damit das Serverskript den bezahlten Lauf nur nach erfolgreicher Vorprüfung startet.

Die neu gesicherten Ausgaben `select-output.txt`, `selection-summary.json`, `selected_requests.jsonl` und `dry-run-output.txt` belegen 10 Aufrufe (7 gefiltert, 3 Kontrolle), 2.535 → 1.541 Kandidaten und 2.894.727 → 2.341.918 Promptzeichen. Geschätzte Kostenobergrenze: **3,239186 USD insgesamt**, davon **2,390154 USD gefiltert** und **0,849032 USD Kontrolle**. Nur gefilterte Aufrufe: 1.943 → 949 Kandidaten. `feasible=true`, `budget_blocked=0`; 0 API-Versuche, 0 tatsächliche Kosten. Auswahl und Dry-Run: Exitcodes 0 und 0. Der vorhandene Build-Nachweis bleibt unverändert: 23 geeignete Aufrufe, 8.608 → 4.291 Kandidaten; Build wurde für diese Budgetanpassung nicht wiederholt.

`offline-execution.json` und `verification.json` binden die lokalen Prüfungen und die Datei-SHA-256 an diesen Paketstand. Die erneute Schreibgrenzenprüfung verwendet `budget-change-outside-baseline.json`: ausschließlich Dateimetadaten außerhalb des Pakets, ohne Secret- oder andere Dateiinhalte zu lesen. Bei 76.140 Dateien außerhalb des Pakets sind Größe, Änderungszeit, Inode und Modus unverändert; keine hinzugefügten oder entfernten Dateien. Bei `working-memory/.gitignore` hat sich nur die Statuszeit (ctime) verändert; Ursache unbekannt. Es gab keinen auf einen Außenpfad gerichteten Schreibbefehl. Dateiinhalte außerhalb wurden nicht gelesen oder gehasht; eine bereits nicht zugängliche Stelle bleibt ausdrücklich ungeprüft. Es wurden keine Git-Befehle, Netzwerk-, API- oder Serveraufrufe ausgeführt. Serverintegration und reale Modellqualität bleiben ungeprüft.

Das frühere unabhängige Read-only-Review hat alle 23 Transformationen auf Präfixe/Suffixe, Archiv-Navigation, Work-Indizes und Alias-Schemaabdeckung geprüft; diese Transformationen wurden nicht geändert. Seine damalige Budgetblockade ist durch die ausdrückliche Budgetänderung und die neuen Offline-Nachweise überholt. Dieses historische Review wird nicht als erneute Prüfung des geänderten Paketstands ausgegeben.

Die Suche nach alten Budgettextstellen in Code, Tests, Dokumentation und Prüfberichten ergibt keine Treffer (Such-Exitcode 1). In den gespeicherten Original-Prompttexten bleiben 62 beziehungsweise 20 fachfremde Zahlenvorkommen des Suchmusters erhalten; diese Quelltexte werden nicht für eine Budgetanpassung verändert. Archivinhalt mit `tar -tf` geprüft: genau fünf Dateien, Exitcode 0. Separat entpackter Archiv-Dry-Run: Exitcode 0, identische Kosten und Zählwerte; Shell-Syntaxprüfung: Exitcode 0.
