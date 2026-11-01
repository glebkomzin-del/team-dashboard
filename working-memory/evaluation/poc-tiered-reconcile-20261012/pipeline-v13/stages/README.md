# Offline-Replay für extract und gate

Stand: 2026-10-13. Ziel ist ein späterer, durch einen Menschen gestarteter Vergleich von `gpt-6-luna` mit gespeicherten Sol-Referenzen. `compact` bleibt unverändert auf Sol. Das Paket entwickelt und prüft Replay und Auswertung offline; Modellqualität, Serverintegration und Produktabnahme sind noch offen. Keine lokale bezahlte Ausführung.

Alle neu angelegten Dateien liegen in diesem Verzeichnis. Die Eingaben werden gelesen. Keine Git-Versionierung: `.git` liegt außerhalb der ausdrücklich erlaubten Schreibgrenze. Der eigenständige Paketstand, die Regeln und Prüfungen sind hier dokumentiert. Rückweg: dieses neu angelegte Paketverzeichnis entfernen; keine produktiven Code-, Deployment- oder Datenänderungen sind Teil des Auftrags. Ein produktiver Restore wurde nicht ausgeführt.

## Ablauf

Python-Standardbibliothek, keine Installation. Auf dem Entwicklungsrechner:

```sh
cd /Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard\ Job/meeting-os/working-memory/evaluation/poc-tiered-reconcile-20261012/pipeline-v13/stages
python3 -I -B extract_stage_requests.py
python3 -I -B -m unittest discover -s . -p 'test_*.py'
python3 -I -B replay_stage.py --requests stage_requests.jsonl --stage both --model gpt-6-luna --select stratified:6 --max-usd 0.80
```

Die Extraktion verweigert das Überschreiben vorhandener Ausgaben. `--archive PFAD` wählt ein anderes Archiv, `--queue -` liest synthetische Queue-Daten über stdin. Standardarchiv: `~/Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz`. Nur `canonical/queue.jsonl` wird mit `tar -xzOf` gestreamt. Es entsteht keine entpackte Archivkopie. Ausgaben: `stage_requests.jsonl` und `extraction-stats.json`.

`--stage extract|gate|both`, `--select smallest:N` (kleinste N je Stufe), `--select stratified:6` (Standard), `--select DATEI` (JSONL mit job_id/call_index/stage), `--select all`. `--limit` ist eine Sicherheitsobergrenze für die gesamte Auswahl; Überschreitung ist ein Fehler, kein stilles Abschneiden. Auswahl und gesamter Kostendeckel werden vor Transport/Kredentialen geprüft. Explizite Auswahl mit falschen/fehlenden Identitäten ist ein Fehler. Automatische Auswahl setzt gültige abgeschlossene Sol-Referenzen voraus. Kein unvollständiger Teilplan wird als erfolgreicher Dry-Run ausgegeben.

Das vorbereitete Transferarchiv `transfer/stages-bundle.tar` enthält **nur die zwölf ausgewählten Anfragen** als `selected_requests.jsonl`, daneben Runner, Vergleich, Helfer, synthetische Tests, README und Serverskript; weder vollständige Queue noch vollständige stage_requests. Es enthält keine Credentials. Ein Mensch kopiert es auf den Server und startet dort:

```sh
tar -xf stages-bundle.tar
cd stages-bundle
# OPENAI_API_KEY muss bereits in der Umgebung gesetzt sein.
sh run_stage_on_server.sh
```

Das Skript schreibt `stage.log`, führt zunächst den Dry-Run aus und startet ausschließlich bei Exitcode 0 die bezahlte Ausführung mit `--execute --max-usd 0.80`. Keine Credential-Datei wird gelesen. Ein vorhandenes Log oder Ergebnis verhindert einen erneuten Start. Ergebnisse werden exklusiv angelegt, jeder vollständige oder fehlerhafte Versuch wird mit Rohantwort, ggf. Teilstream, Usage, Kosten, Status und Fehler gespeichert und mit flush/fsync gesichert. Keine automatischen Wiederholungen. Bei unbekannten Kosten stoppt der Runner nach der gesicherten Antwort sofort; ein manueller neuer Lauf darf bezahlte Identitäten nicht erneut senden.

Nach Rückübertragung der Ergebnisdatei (durch einen Menschen):

```sh
python3 -I -B compare_stage.py --requests selected_requests.jsonl --results stage-results.jsonl --output comparison.json
```

Immer die **ausgewählten** Requests übergeben. Die vollständige Datei erwartet ansonsten Ergebnisse für alle darin enthaltenen Identitäten. Fehlende/ungültige Antworten, widersprüchliche Modelle, fehlende Kandidatenabdeckung und unbekannte Nenner ergeben keine positive Abnahme. Vergleichsausgabe enthält Metriken und Identitäten/Positionen, keine Quellprosa. Rohantworten und Requests enthalten private Meeting-Inhalte und bleiben nur in den dafür vorgesehenen Dateien.

## Stufenerkennung und Originalbelege

Quellen sind die echten archivierten Call-Strukturen, `../../model-replay/{extract_requests,replay,compare,replay_common}.py`, `../../filtered-replay/{run_filtered,replay_common}.py` und `../../../sol-operational-release-20261006/backend/{hybrid_pipeline,openai_provider}.py`. Relative Pfade beziehen sich auf dieses Verzeichnis. Keine Quelle wurde geändert. `recognition-structure.json` enthält ausschließlich Marker-/Struktur-/Längen- und Modellzahlen.

Erkennungsregel, in dieser Reihenfolge:

1. `Bereits geöffnete Original-IDs` schließt compact aus.
2. `Bestehende Arbeit:` plus `Kandidaten:` und ein Schema mit `verdicts` identifiziert gate.
3. Alle sonstigen Prompts mit `Kandidaten:` werden ausgeschlossen.
4. Ein Schema mit `observations` plus `Extraktion`, `STUFE 1:` oder die Beobachtungsanweisung `Beobachtungen` identifiziert extract.

Der Schemaguard ist entscheidend: fünf Embedding-Aufrufe enthalten das Wort `Extraktion`, sind aber keine Extraktionsstufe. Alte Extraktionsvarianten ohne STUFE-1-Marker werden anhand observations-Schema und Beobachtungsanweisung erhalten. Die archivierten Schemas enthalten bei extract observations/coverage_notes/meeting_summary, jüngere zusätzlich meeting_display_title/search_queries; gate liefert verdicts mit index/verdict/evidence_ids. Erkennung basiert auf dem gesamten Prompt; ein Quelltext mit denselben Markern könnte theoretisch falsch zugeordnet werden. Die Strukturprüfung begrenzt das, ersetzt keine explizite gespeicherte Stage-ID.

Insgesamt: extract 215 (mittlere/maximale Promptzeichen 51242.405/525385), gate 127 (42035.094/150484). Davon request.model Sol: extract 87, gate 59. Terra: extract 128, gate 68. Zwei Sol-extract-Aufrufe haben keine vollständige Antwort und bleiben in der Gesamtextraktion sichtbar, sind für die empfohlene Stichprobe ausgeschlossen. Gültige abgeschlossene Sol-Referenzen: extract 85, gate 59. Request- und Response-Modell stimmen für diese Referenzen überein. Fehlende Kosten oder Datum werden null und gezählt; keine Rekonstruktion erfundener Werte.

## Auswahl und Kostenannahmen

Die Reserve der empfohlenen Auswahl beträgt 212373 Mikro-USD (extract 113760, gate 98613), insgesamt 0.212373 USD bei null API-Versuchen. Empfohlen sind je Stufe sechs gültige Sol-Referenzen: zwei kürzeste Prompts, zwei benachbarte um die Mitte der sortierten Promptlängen und zwei längste. Bei Gleichstand entscheidet die vollständige Identität deterministisch. Dies ist eine Längenstichprobe ohne qualitative Vorauswahl; alle Ergebnisse zählen. Sie belegt keine statistische Serienzuverlässigkeit. `selection-summary.json` bindet die empfohlene Auswahl an Identitäten, Längen und Reserven, ohne Hashes oder Außenverzeichnisnachweise.

Preisvorgabe des Auftrags in USD/Million Tokens: Luna Input 0.10, Cached 0.01, Cache-Schreiben 0.125, Output 0.50; Sol 2.00/0.10/2.50/10.00. Cached und Cache-Schreib-Tokens werden vom normalen Input abgezogen; negative, nicht-ganzzahlige oder widersprüchliche Usage ist unbekannt. Reasoning ist bereits im Output enthalten. Keine Preise wurden online geprüft, weil Netzwerkzugriff ausgeschlossen ist.

Vorausreserve: UTF-8-Bytes von Prompt und serialisiertem Schema als Input-Tokens plus 4096 Framing-Tokens; gesamter Input zum höchsten Luna-Eingabepreis (Cache-Schreiben), volle Output-Erlaubnis. Diese bewusst konservative Reserve ist kein bestätigter Provider-Tokenizer- oder Rechnungsnachweis. Der Gelddeckel schützt die geplante Summe und weitere Aufrufe; einen bereits laufenden Provideraufruf kann das Skript nicht an einem exakten Dollarbetrag abschneiden. Unbekannte tatsächliche Kosten sperren jeden Folgeaufruf. Budgetstandard und Serverskript: maximal 800000 Mikro-USD.

Request-Aufbau: recorded Prompt und Schema, User-Input, reasoning medium (explizite gespeicherte Werte haben Vorrang), truncation disabled, service_tier default, strict json_schema/meeting_result, stream true, store false und `prompt_cache_options: {"mode":"explicit"}`. Wie im vorherigen Replay-Harness wird max_output_tokens mindestens 16000, sonst gespeichertes max_tokens verwendet. Diese Änderung gegenüber kleineren Produktionslimits ist eine dokumentierte Replay-Annahme; sie begrenzt Output-Abbruch und wird vollständig reserviert. Kein neuer Inhalt und keine Promptverkürzung.

## Vergleich und offene Qualitätsabnahme

Standardgrenzen: extract-Verpflichtungs-Recall mindestens 0.95; gate mindestens 0.95 exakte verdict-Übereinstimmung; höchstens ein Fall Sol supported → Luna anders (`--max-gate-losses 1`). Andere verdicts einschließlich ambiguous/already_done/duplicate gelten in diesem Verlustmaß als anders, nicht als supported. Die gate-Zeilen enthalten jeden erwarteten Kandidatenindex mit Sol-/Luna-verdict, Gleichheit und den beiden Verlust-/Zusatzrichtungen; fehlende Entscheidungen bleiben null. Parameter und Matching-Details stehen in `python3 -I -B compare_stage.py --help` und im Vergleichscode.

Beobachtungen werden innerhalb desselben Aufrufs einmalig zugeordnet über überlappende evidence_ids oder Originalbereiche und Zitat-/Textähnlichkeit; diese Heuristik ist kein fachlicher Wahrheitsbeweis. Eine zugeordnete Luna-Beobachtung einer anderen Klasse zählt nicht als zurückgewonnene Verpflichtung. Anzahl, zusätzliche Beobachtungen, Klassengleichheit und Zusammenfassungslängen werden getrennt erfasst. Zusammenfassungspräsenz/Längenverhältnis beweisen keine Inhaltsgleichheit. `comparison.passed` bedeutet ausschließlich erfüllte dokumentierte Metrikgrenzen mit vollständigen gültigen Antworten; es ist keine automatische Freigabe des Modellwechsels und kein Nachweis für vollständig gleiche Inhalte. Sol ist Vergleichsreferenz, keine garantierte menschliche Ground Truth. Tatsächliche Modellantworten und fachliche Prüfung bleiben bis zum späteren Serverlauf offen.

## Prüfung und Status

Lokale Tests verwenden ausschließlich synthetische Fixtures und Mock-Transport. Sie prüfen Erkennung, Auswahl, Budget-/Unknown-Pfade, Requeststruktur, vollständige Fehlerablage, Schema- und Vergleichsmetriken. `test-output.txt` enthält das tatsächliche Gesamtergebnis; `dry-run.json` den echten lokalen Plan gegen aus dem Archiv extrahierte Referenzen. 82/82 synthetische Tests sind bestanden. Zusätzlich wurde für alle zwölf ausgewählten realen Schemata die Replay→durable Ergebnisdatei→Vergleich-Kopplung offline mit einem Mock durchgeführt: der Mock lieferte ausschließlich die gespeicherte Sol-Antwort als simulierte Luna-Antwort und synthetische Usage. Zwölf Schemakontrakte waren gültig; das ist nur Vertrags-/Serialisierungsprüfung, kein Luna-Qualitätsnachweis. Die vorübergehende Mock-Ergebnisdatei wurde entfernt; `mock-contract-summary.json` enthält nur Status/Zahlen. Der Servertransport wurde nicht ausgeführt. `verification.json` nennt Prüfzahlen, Dateigröße und offene externe Schritte. Ein unabhängiges read-only-Paketreview erfolgt vor dem lokalen Abschluss; keine Behauptung einer technisch aktiven globalen Laufzeitsperre.
