# Delta-v2-Replay · Release 2

Stand: 2026-10-13. Paketversion `v13:release2:replay-v2:1`. Ausschließlich offline
erstellt, Stdlib, Python `python3 -I -B`. Die spätere bezahlte Ausführung erfolgt
durch einen Menschen auf dem Server. Keine Modellqualität oder produktive
Integration aus den lokalen Tests ableiten.

Offene parallele Änderung um 15:14 Europe/Berlin: `replay_v2.py` wurde außerhalb
der Lead-Änderungen auf `CAP=2500000` und Default 2,50 USD geändert. Herkunft
und Freigabe sind ungeklärt; die konkrete Nutzerfrage ist offen. Diese Änderung
wurde nicht zurückgesetzt. Wrapper und ursprünglicher Plan bleiben 1,30 USD.
Die 1,30-USD-Vertragstests schlagen deshalb aktuell fehl. Die Dateiänderung ist
kein Freigabenachweis; eine konsistente Paketabnahme bleibt offen. Der folgende
1,30-USD-Budgetbefund gilt für den Originalauftrag und den unveränderten Wrapper.

## Aktueller Stand und offene Vorgaben

8 echte finale Referenzaufrufe, 1.248 Work-Kandidaten, 58 Beobachtungen.
Die unveränderten Pflichtlimits ergeben eine Reservierung von **2,420262 USD**
gegen **1,30 USD**. Allein die 134.012 reservierten Ausgabetokens kosten 1,340120
USD. Daher stoppt der Standard-Dry-Run mit Exit 2, `estimated_budget`, 0 Calls und
0 Transportversuchen. Die geforderte erfolgreiche Acht-Call-Budgetabnahme ist
mit diesen gleichzeitig verlangten Limits unmöglich. Kein Ausgabelimit, Fall
oder Tarif wurde zum Erreichen eines grünen Dry-Runs abgeschwächt. Eine Änderung
der Grenze benötigt eine konkrete neue Nutzerentscheidung; sie ist hier nicht
erfolgt. Das Paket ist vorbereitet, seine Ausführung bleibt gesperrt.

Vorhandene erforderliche Kontrollen: `b5e4fddb:13`, `2d34a51a:18`.
`8bdacbe2` fehlt in beiden gespeicherten Ergebnisdateien. Zusätzlich vorhanden:
`f91105a3:16`, ausdrücklich separat und ohne Ersatzfunktion. `control_metrics.json`
berichtet 2/3, `complete=false`; die Qualitätsabnahme bleibt deshalb unbekannt.
Kein neuer Kontrolllauf. Für die verfügbaren beiden Kontrollen: gemeinsame
Entscheidung 11/15 = 73,3333 %, update_target 13/15 = 86,6667 %;
Lifecycle-Positive 0/2, zusätzliche Flags 1. Die gemeinsame Entscheidung meint
gleichzeitige Übereinstimmung von update_target, update und matter_id; sie ist
strenger als die historische reine Zielquote. Die 2-Pp-Schwelle wird erst bei
positiv belegter vollständiger Kontrollbasis freigegeben.

## Quellen und Erzeugung

`build_v2_requests.py` liest `../../../model-replay/requests.jsonl` und
`/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl`.
Die Quelldateien bleiben Eingaben. `load_release()` lädt direkt
`../overlay/hybrid_schema.py:70` (`delta_schema`) und
`../overlay/compact_reconcile.py:199-217` (`DELTA_INSTRUCTION`, `delta_prompt`).
Import-Stubs ersetzen lediglich unbenutzte Importnamen; beide aufgerufenen
Transformationen sind der tatsächliche Release-Code. Die tatsächliche gespeicherte
Vollschema-Anfrage wird über `delta_schema` transformiert; eine neue Katalog- oder
Schema-Rekonstruktion erfolgt nicht. Der gespeicherte Prompt erhält exakt die
Release-Transformation. Der gesamte Abschnitt ab `Vorläufige Beobachtungen`
bleibt als Zeichenfolge erhalten, einschließlich Beobachtungen, Katalog und
Original. Die Referenz verwendet den vollständigen gespeicherten `reference_text`
mit `coverage_notes`, nicht die verkürzte Archivprojektion.

`delta_codec.py` ist die Kopie des Release-Decoders `../overlay/delta_codec.py:94`.
`hybrid_schema.py` ist eine lokale Kopie für synthetische Tests. Beide Quellen
werden nicht geändert. Die übertragenen Requests sind bereits fertig erzeugt;
der Server benötigt keine Release- oder Workspace-Dateien.

Auswahl: zwingend `8bdacbe2:24` (W130/M116), `a8c4b587:26` (W73),
`2d34a51a:18` (W8), `b5e4fddb:13` (W5); drei kleinste finale Aufrufe ohne
Lifecycle-Positive und ohne nichtleeres update_target: `740b1eb7:1`,
`acc34319:2`, `570858c5:2`. Diese drei besitzen keine Beobachtungen und testen
den leeren Quellenvertrag; sie belegen keine Zuordnungsqualität.
Großer Aufruf: `d825f68c:33`, 103.263 beobachtete Inputtokens. Die A8-Referenz
ist die gespeicherte Endform nach den historischen Nachforderungen 24/25; die
Replayantwort kann wiederum Nachforderung oder Endform sein. Es wird keine
automatische zweite Runde ausgeführt.

Der Builder legt `selected_requests.jsonl` exklusiv neu an und verhindert
versehentliches Überschreiben. Er wird im ursprünglichen Workspace ausgeführt:

```sh
python3 -I -B build_v2_requests.py
```

## Ausführung und Auswertung

```sh
python3 -I -B run_tests.py
python3 -I -B replay_v2.py --max-usd 1.30
python3 -I -B compare_v2.py
```

Nur `--execute` erzeugt einen Transport. Schlüssel ausschließlich aus der bereits
gesetzten Umgebungsvariable `OPENAI_API_KEY`; keine Credential-Datei. Modell
`gpt-6.1-sol`, Reasoning `medium`, Standardtarif `service_tier=default`,
`prompt_cache_options={"mode":"explicit"}`. Ausgabelimit exakt
`max(Referenz-max_tokens, 16000)`, einschließlich Reasoning.

Vor jedem Transport: synchronisierte Reservierung im vollständigen
`replay_ledger.jsonl`. Der Rohstream wird inkrementell nach `raw-attempt-NNN.sse`
geschrieben und synchronisiert, und im Versuch samt geparster Response, Text,
Usage und Transportergebnis festgehalten. Geheimnisechos werden ausschließlich
um den Umgebungskey redigiert. Jede versuchte Identität wird bei Neustart
übersprungen, auch bezahlte Fehler. Inhaltliche Fehler werden nie wiederholt.
Unklare Usage oder unterbrochene Reservierungen sperren weitere Calls.
`replay.lock` verhindert Parallelstarts; nach Crash nicht ohne Ledgerklärung
entfernen. Der Proxy reserviert Referenzinput plus positive UTF-8-Zuwächse von
Prompt/Schema plus 4.096 Framingtokens. Das ist kein garantierter Tokenizer-
oder tatsächlicher Kostenhöchstwert; insbesondere ein unterschätzter aktueller
Call kann nicht nachträglich unbezahlt gemacht werden. Gemessene Mehrkosten
sperren den nächsten Call. Keine Cachetreffer werden vorausgesetzt.

Annahmen: Offlinepreise aus dem vorhandenen Filter-Replay: Input 2,00,
Cache-Read 0,10, Cache-Write 2,50, Output 10,00 USD/Mio. Keine Livepreisprüfung
wegen des Netzwerkverbots. Cached und Write sind disjunkte Teile des Gesamtinputs;
Reasoning ist im Output enthalten. Mikro-USD werden aufgerundet. Ungültige oder
unklare Usage erzeugt keinen erfundenen Kostenwert. Der spätere Operator muss
Preisgültigkeit und eine konkret freigegebene Budgetänderung separat klären.

`compare_v2.py` prüft positive, konsistente Provider-/Ledger-Evidenz, Delta- und
rekonstruiertes Vollschema, dann den tatsächlichen Release-Decoder. Pro Aufruf:
Endform/Nachforderung, Quellenabdeckung, die drei Entscheidungsfelder einzeln
und gemeinsam, Lifecycle nach Alias+Aktion, positive Recall, zusätzliche Flags,
Outputtokens samt Reasoning, Referenzkosten und Verhältnis. Ausgabekosten und
Input-/Cacheeffekte bleiben durch Usage nachvollziehbar. Erfolg verlangt
vollständige Ergebnis- und Kontrollbelege, keine Decoderfehler, 100 % Abdeckung
aller ausgewählten Endformen, gemeinsame Entscheidung mindestens Kontrollwert
minus 2 Pp und **je Aufruf** höchstens 40 % Referenzausgabetokens. Lifecycle wird
separat berichtet und nicht durch ein zusätzlich erfundenes Gate bewertet.

Eine gültige Nachforderung ist weder Decoderfehler noch Endformabnahme.
`next_round` schätzt ihre zusätzliche Reservierung für einen weiteren gesamten
Call; zusätzlich geöffnete Originaltokens sind unbekannt. Damit ist die Schätzung
keine Gesamtkostenobergrenze einer Öffnungsschleife. Keine zweite Runde wird
automatisch bezahlt. Fehlende Daten werden null/unbekannt, niemals Erfolg.
Exitcode Vergleich: 0 akzeptiert, 1 Kriterien offen/verfehlt, 2 ungültige Eingabe.

## Transfer, Nachweise und Rückweg

`transfer/replay-v2-bundle.tar` enthält nur sieben benötigte Laufdateien im
Archivwurzelverzeichnis: Runner, Common, Vergleich, Release-Decoder, fertige
Requests, Kontrollmetriken und `run_on_server.sh`. Kein Datenquellenarchiv,
Testcode, Schlüssel oder Testresultat. Größenlimit 5.000.000 Bytes.

In ein neues Server-Unterverzeichnis entpacken und dort später ausdrücklich:

```sh
sh ./run_on_server.sh
```

Der Wrapper beginnt mit `cd "$(dirname "$0")"`, schreibt nach `run.out`, führt
erst den Dry-Run aus und nur bei dessen Exitcode 0 `--execute --max-usd 1.30`.
Danach schreibt er den numerischen Vergleich nach `comparison.json` und
`run.out`. Mit diesem Paketstand endet er vor dem Transport mit Exit 2.

Lokale Belege: `test.out`, `run.out`, `selection_summary.json`,
`offline_results.json`. Tests unterscheiden synthetische Mock-Transporte,
8 gespeicherte Referenzrundreisen und den offline geprobten Wrappervertrag.
Ein frisches unabhängiges read-only GOAL_GATE-Review fand Budget und Kontrolle
als offene Abnahmebedingungen sowie einen inzwischen reparierten Wrapper-
Parameter. Es ist ein tatsächliches Review, keine technische Laufzeitsperre.
Die finale Archiv-/Testsprüfung bindet diesen Paketstand ohne Git-Commit:
Git-Versionierung würde die ausdrücklich nur hier erlaubte Schreibgrenze
verletzen. Keine Außenverzeichnis-Nachweise, Baselines oder Hashes.

Letzter numerischer Stand: 64 Testmethoden, 62 bestanden, 2 fehlgeschlagen
(3 Failure-Ereignisse einschließlich Subtest), 0 Errors/Skips. Die beiden
Fehler betreffen ausschließlich die ungeklärte Anhebung des Runner-Limits.
8/8 Referenzrundreisen. Archiv 4.341.760 Bytes, 7/7 aktuelle Laufdateien,
real in ein temporäres Paket-Unterverzeichnis entpackt; dort
`sh ./run_on_server.sh`: Exit 2, 0 Transportversuche. Temporäre Entpackung
anschließend entfernt. Das Archiv enthält den transparent ungeklärten aktuellen
Runnerstand; der feste 1,30-USD-Wrapper sperrt trotzdem vor jeder bezahlten
Ausführung. Paket- und Qualitätsabnahme 0. Der gezielte zweite unabhängige Review
bestätigte den pro-Aufruf-Outputmaßstab und den korrigierten Wrappervertrag;
es erteilt weder Budget- noch Gesamtabnahme.

Rückweg: dieses neue Paketverzeichnis bzw. sein separat entpacktes Server-
Unterverzeichnis verwerfen. Es wurden keine bestehenden Runtime-, Datenbank-
oder Deploymentdateien geändert. Bereits später bezahlte Aufrufe bleiben bezahlt;
ein Code-Rückweg stellt weder Geld noch Modellentscheidungen wieder her.
