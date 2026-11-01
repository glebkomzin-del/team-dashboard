# Gespeicherte Abgleich-Aufrufe offline vorbereiten und nachspielen

Stand: 2026-10-12. Dieses isolierte Harness nutzt ausschließlich Python-Stdlib.
Alle Befehle laufen mit `python3 -I` im Verzeichnis `model-replay/`.
Produktionsdateien, Git, Credentials-Dateien und Installationen werden nicht benötigt.
Die Entwicklung und Abnahme erfolgen offline; der Mensch führt `--execute` erst
nach Freigabe auf dem Server aus. Es wurde kein echter Provideraufruf ausgeführt.

## Ablauf

```sh
python3 -I extract_requests.py
python3 -I replay.py --requests requests.jsonl --model gpt-6-luna --service-tier standard --max-usd 1.50
```

Der Extraktor startet genau `tar -xzOf <archive> canonical/queue.jsonl` und liest
eine Zeile nach der anderen. Er entpackt das Archiv nicht. Das Standardarchiv ist
`~/Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz`;
`--archive` ersetzt den Pfad. Die Reihenfolge des Archivstreams bleibt erhalten.
Er berücksichtigt nur `kind == "call"` mit dem exakten Prompt-Merkmal
`Bereits geöffnete Original-IDs`. Das Datum kommt aus einer Zeile
`Datum: YYYY-MM-DD`; es ist kein zusätzlicher Datumsfilter.
Die Ausgabe enthält die sieben beauftragten Felder. Prompt, Schema und
Referenztext bleiben unverändert. Es wird nur die kleine Auswahl gespeichert,
keine vollständige Queue. Atomare Veröffentlichung erfolgt erst nach erfolgreichem
Tar-Abschluss. Vorhandene Ausgaben werden nicht überschrieben.

Eine optionale Auswahl erfolgt mit `--only-index-file selection.jsonl`:

```json
{"job_id":"synthetic-job","call_index":0}
```

Jede Zeile benennt genau ein Paar; alternativ ist ein JSON-Array solcher Objekte
zulässig. Fehlende ausgewählte Paare, doppelte Identitäten und beschädigte Queue-Zeilen
führen zum Abbruch ohne veröffentlichte Ausgabe. `--output` erlaubt einen anderen
Ausgabenamen innerhalb dieses Verzeichnisses. `--queue -` ist für synthetische
Queue-Zeilen über stdin vorgesehen.

Nach Freigabe auf dem Server und mit bereits gesetztem `OPENAI_API_KEY`:

```sh
python3 -I replay.py --requests requests.jsonl --model gpt-6-luna --service-tier standard --max-usd 1.50 --execute
python3 -I compare.py --requests requests.jsonl --results results.jsonl
```

`--limit N` begrenzt die Anzahl ursprünglicher Aufrufe, nicht die Transportversuche.
Der Standard ist immer DRY-RUN. Dieser liest keinen API-Schlüssel, baut keinen
Transport und benötigt kein Netzwerk. Nur `--execute` liest die Umgebungsvariable;
es existiert keine Datei-Fallbacksuche. `--results` ersetzt den Ausgabenamen,
ebenfalls nur innerhalb dieses Verzeichnisses. Bereits vorhandene Ergebnisse werden
abgelehnt; ein neuer Name beginnt ein neues Budget und ist kein kostenfreier Resume.
Es gibt keine Nachfrage während des Ablaufs.

## Request und Produktionsvorlage

Vorlage, relativ zu `model-replay/`:
`../../sol-operational-release-20261006/backend/`.

* `openai_provider.py:149-154`: identisches User-Input-Envelope, striktes
  `json_schema` mit Namen `meeting_result`, `truncation: disabled`.
* `openai_provider.py:194-208`: Responses-Endpunkt, `max_output_tokens`,
  `store: false`, `stream: true` und Bearer-Authentifizierung.
* `openai_provider.py:109-145,209-223`: SSE-Terminalereignisse,
  HTTP-/Transportfehler, 60 Sekunden Socket-Timeout und 420 Sekunden Gesamtdauer.
* `openai_provider.py:36-106`: abgeschlossene Antwort, Modell-/Tier-Prüfung,
  genau eine vollständige Assistant-Nachricht, keine Refusal-Blöcke.
* `call_budget.py:47-76`: Usage-Prüfung, gecachter Input, Decimal-Rechnung und
  Aufrundung auf ganze Mikro-USD; Output enthält bereits Reasoning-Tokens.

Direkte Imports werden vermieden: der Provider importiert lokale Produktionsmodule,
beschränkt Modelle und enthält eine Credential-Dateisuche (`:13,157-163,195-196`);
die Budgetvorlage hat abweichende Preise und produktive Reservierungslogik.
Es gibt keine Verbindung zu Produktionsdatenbanken oder Budgettabellen.
Der gespeicherte `scope`/`transport` bleibt in `requests.jsonl`, ist wie in der Vorlage
kein zusätzlicher API-Parameter.

Modell und Parameter werden gezielt ersetzt: `gpt-6-luna` oder `gpt-6.1-sol`,
Reasoning `low`, Standard-Tier auf der API als `service_tier: default`.
`max_output_tokens = max(16000, Referenz-max_tokens)`; fehlt `max_tokens`, gelten
16000. Größere Referenzlimits bleiben erhalten; ungültige Werte werden abgelehnt.
Das großzügige Limit und niedrige Reasoning sollen genügend Platz für die vollständige
strukturierte Ausgabe lassen. Ob beide Modelle diese Parameter auf dem Server
akzeptieren, wurde absichtlich nicht live geprüft.

## Kosten und Abbruch

Die Preise sind die Vorgaben dieses Auftrags, keine live verifizierte Preisauskunft.
Unterstützt wird ausschließlich Standard:

| Modell | Input USD/Mio. | Cached Input USD/Mio. | Output USD/Mio. |
| --- | ---: | ---: | ---: |
| gpt-6-luna | 0,10 | 0,01 | 0,50 |
| gpt-6.1-sol | 2,00 | 0,10 | 10,00 |

DRY-RUN zählt Prompt-Zeichen plus Zeichen des gespeicherten Schemas nach
`json.dumps(schema, ensure_ascii=False)`. Input-Schätzung:
`ceil(Zeichen / 3,6)`. Für Output wird das volle konfigurierte Limit reserviert,
für Input kein Cachevorteil angenommen. Jede Kostenrechnung wird auf Mikro-USD
aufgerundet. Alle genehmigten Schätzungen werden summiert; passt die nächste nicht
unter `--max-usd`, wird vor diesem Aufruf mit Exitcode 2 gestoppt.
Bei 40 Aufrufen und jeweils 16000 Output-Tokens beträgt allein die Outputreserve
für Luna 0,32 USD; Input und größere Referenzlimits kommen hinzu.

Execute reserviert vor jedem Versuch die gleiche Schätzung gegen das noch offene
Budget. Nach jeder Antwort werden tatsächliche Input-/Cached-/Output-Tokens
abgerechnet. Bei Erreichen oder Überschreiten des Deckels erfolgt sofort ein harter
Stopp vor jedem weiteren Versuch. Fehlende/ungültige Usage oder ein abweichendes
Modell/Tier sind keine Nullkosten: die Schätzung bleibt als unsichere Belastung
reserviert, während `actual_micro_usd` `null` bleibt. Der Vergleich zeigt dann
`UNKNOWN`; die bekannte Teilsumme im Run-Summary ist keine vollständige Rechnung.
Unbekannte Cache-Write-Preise werden nicht erfunden.

Ein laufender Request kann seinen erst nachträglich bekannten Preis über den Deckel
heben. Zeichen/3,6 ist keine garantierte Token-Obergrenze; dieses lokale Harness ist
kein providerseitiges Ausgabenlimit. Nachträglich fehlen bei einem Prozessabbruch
gegebenenfalls abrechenbare Usage-Daten. Budget gilt pro Prozesslauf einschließlich
aller seiner Wiederholungen, nicht über mehrere unterschiedliche Ergebnisdateien.

Nur Transportfehler werden höchstens zweimal wiederholt (maximal drei Versuche).
HTTP-Fehler einschließlich 429/5xx, Refusals, ungültiges JSON, Schemafehler und
unvollständige SSE-/Providerantworten werden protokolliert und nicht wiederholt.
Anschließend läuft die nächste gespeicherte Anfrage bis Ende/Limit/Kostendeckel.
Timeouts und abgebrochene Verbindungen können bereits Kosten verursacht haben.

`results.jsonl` enthält je Versuch vollständigen HTTP-/SSE-Text in `raw_response`,
die terminale Providerantwort, extrahierten Text, Usage, HTTP-Status, Fehlerdetails,
Kosten, Versuchszähler und Laufzeit. Jede Zeile wird sofort geflusht und im CLI
per `fsync` gesichert. Der API-Schlüssel wird nie gespeichert; sollte der Provider
ihn wörtlich zurückliefern, wird diese Stelle ausnahmsweise durch
`[REDACTED_API_KEY]` ersetzt. Stdout zeigt nur Zähler und Kosten, keine Meetingprosa.

Replay-Exitcodes: 0 = vollständig/Limit ohne endgültig fehlgeschlagene Calls,
1 = Eingabe-/I/O-/Credentialfehler oder endgültige Callfehler, 2 = Budgetstopp.

## Vergleich und Annahmen

Alle Versuche zählen bei den Kosten; Entscheidungen stammen vom letzten Versuch
je `(job_id, call_index)`. Vergleich bedeutet Referenzübereinstimmung, keine
fachliche Wahrheit oder menschliche Produktabnahme. Die Tabelle enthält jeden
angefragten Call sowie eine mikroaggregierte TOTAL-Zeile:

* Parsebares JSON und Gültigkeit gegen das gespeicherte Schema, einschließlich
  lokaler `$ref`, `$defs`, `anyOf`, erforderlicher Felder und erlaubter Eigenschaften.
  Der Stdlib-Validator unterstützt die dokumentierte Schema-Teilmenge in
  `replay_common.py`; unbekannte Keywords oder externe Referenzen scheitern sicher.
* Beobachtungen nach `source_index`: literale Alias-/Null-Gleichheit von
  `update_target`, zusätzlich `update` und `kind`.
* `work_results` nach nummeriertem Schlüssel: `"unchanged"` versus jede
  Änderungsentscheidung mit `action`. Bei synthetischen Listen gilt die Position
  als `work_index`. Recall zählt die wiedergefundenen Referenz-Änderungen,
  zusätzliche Flags zählen neue positive Kandidaten. Es gibt keinen Vergleich
  freier Begründungstexte.
* Fehlende, zusätzliche oder doppelte Indizes und unbekannte/fehlerhafte Antworten
  verhindern PASS, auch wenn isolierte Quoten gut aussehen. `work_results: null`
  bei Archiv-Navigation hat Lifecycle-Recall N/A und wird nicht als 100 % gewertet.
* Tatsächliche Kosten aller Versuche versus gespeicherte Referenzkosten, Delta,
  Tokenzahlen und Abdeckung unbekannter Kosten/Usage. Unbekannte Kosten bleiben
  UNKNOWN, nicht 0; sie sind kein alleiniger fachlicher Fehlentscheidungsbeweis.

Default-Gates auf TOTAL: bei genau 64 Referenz-Änderungen mindestens 62 Treffer,
sonst mindestens 97 % Recall; mindestens 95 % `update_target`-Übereinstimmung.
Dies ist die dokumentierte Interpretation des genannten `62/64 ODER 97 %` für
andere Stichprobengrößen. Parameter:

```sh
python3 -I compare.py --min-recall 0.97 --min-recall-count-64 62 --min-update-target 0.95
```

Exitcode 0 bedeutet PASS, 1 verfehlte/unbekannte Vergleichskriterien, 2 ungültige
Eingaben/Parameter. Update-/Kind-Quoten und Zusatzflags sind ausgewiesene Metriken,
keine zusätzlich erfundenen Gates.

Die strukturelle Archivstichprobe zeigte gespeicherte Fehlerantworten mit leerem
`content`. Solche passenden Anfragen bleiben erhalten: `reference_text: null`
und ein Zähler `unknown_references`; fehlende Usage wird `null` und gezählt.
Der Vergleich meldet die Referenzlücke statt eine Antwort zu erfinden. Fehlende oder
ungültige Datumszeilen bleiben `meeting_date: null` mit Zähler `unknown_dates`.
Es werden weder historische Antworten nachgeneriert noch unbekannte Werte geglättet.

Der abgeschlossene Extraktionslauf las 38015 Queue-Zeilen und 4821 Call-Records.
Er speicherte 41 passende Aufrufe (rund 19 MiB), davon einen ohne Referenztext;
alle 41 Datumszeilen und Usage-Objekte waren vorhanden. Der Vergleich über die
volle Auswahl kann deshalb keinen vollständigen Referenznachweis liefern.
Eine bewusst festgelegte Teilmenge kann über `--only-index-file` extrahiert werden;
die fehlende Referenz wird nicht automatisch aus dem Vergleich entfernt.
Dies sind strukturelle Extraktionszähler, keine Bewertung der Meetinginhalte.

## Offline-Prüfung und Rückweg

```sh
python3 -I -m unittest -v
python3 -I replay.py --requests synthetic_requests.jsonl --model gpt-6-luna
```

Die synthetischen Tests prüfen Request-Erhalt, Kosten und Cachepreise,
Budgetgrenzen, Fehler-/Rohdatenprotokollierung, Transportwiederholungen,
Schema-/Vergleichsmetriken sowie Extract → Mock-Replay → Compare.
Die echte Modellqualität und Serverausführung bleiben ungeprüft.
Abschließender Lauf: **49 von 49 Tests bestanden** (`Ran 49 tests in 0.115s`, `OK`).
Der separate synthetische CLI-DRY-RUN beendete eine Anfrage mit null
Transportversuchen und einer Schätzung von 12007 Mikro-USD (0,012007 USD).
Ein frisches unabhängiges GOAL_GATE-Review nahm das Offline-Paket ohne offene
Pflichtblocker an. Ein dabei gefundener Teilbyteverlust bei `IncompleteRead` wurde
behoben und für HTTP-/SSE-Pfade erneut geprüft. Empfangene Teilbytes und Lesefehler
bleiben auch bei abgebrochenen Antworten erhalten.
Die vollständige abschließende Testausgabe steht in `test-output.txt`, der
synthetische CLI-Lauf in `dry-run-output.txt`; `verification.json` bindet den
geprüften Quellstand mit SHA-256. Lokale Prüfung ist keine Veröffentlichung.

Der Arbeitsauftrag untersagt Git und Änderungen außerhalb dieses Verzeichnisses;
deshalb gibt es keine Commits, Produktionsstatusänderungen oder Graph-/CI-Pflege.
Der benutzerweite Governance-Skill wurde unter
`/Users/glebkomzin/.agents/skills/project-governance/SKILL.md` gelesen und innerhalb
dieser Grenzen angewandt. Es wird keine technische Runtime-Gate-Durchsetzung behauptet.
Ein Rückweg besteht darin, ausschließlich das neu angelegte `model-replay/` zu
entfernen; Backup-Archiv und Produktionssystem wurden nicht verändert.
