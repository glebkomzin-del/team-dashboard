# Flex-Kopie: Implementierung und Offline-Abnahme

Stand: 2026-10-13. Auftrag FLEX-TRANSPORT / FLEX-ACCOUNTING: ausschließlich diese
Kopie erweitern; kein Rollout und keine produktive Ausführung. Autoritative
Abnahme: `python3 -I -B -m unittest` hier im Verzeichnis. Teststatus wird nach dem
abschließenden Gesamtlauf unten ergänzt. Alle Eingaben in Tests sind synthetisch;
Transport und Schlüsselbeschaffung sind gemockt. Preise stammen aus dem Auftrag,
nicht aus einer aktuellen Providerabfrage.

## Dateien und Diff-Zusammenfassung

- `openai_provider.py`: opt-in Flex, begrenzte Retries, genau ein Standard-Fallback;
  längere Flex-Timeouts, versuchsbezogene Tarifvalidierung, bereinigte HTTP-Diagnose.
- `call_budget.py`: Flex-Preise anhand des zurückgegebenen Tarifs; Standardpreise
  für jede Vorabreservierung; zusätzlicher gpt-6-luna-Kostenweg.
- `test_flex_transport.py`: Mock-Transport, Tarifprüfung, Retry-/Fallbackregeln,
  HTTP-Diagnose, Timeouts und direkter Bytevergleich mit dem Quelladapter.
- `test_flex_accounting.py`: Preise, Reservierung, Ledger-Abrechnung und
  Wiederverwendung bezahlter Antworten; Versionskennung bei Tarifwechsel.
- `DEPLOY-NOTES.md`: Aktivierung, Rückweg, Annahmen, Einschränkungen und Prüfstand.
- `TEST-RESULTS.txt`: tatsächliche Ausgabe des abschließenden Gesamtlaufs.

Weitere Python-Dateien sind kopierte Backend-Abhängigkeiten. `evaluation/`
enthält kopierte Prompt-/Schema-Ressourcen für deren Versionsberechnung. Kopiert
wurden ausschließlich reguläre Python-Dateien und diese Prompt-/Schema-Dateien;
keine lokalen Schlüsseldateien. Keine zusätzlichen Pakete sind erforderlich.

## Aktivierung und Transportvertrag

Für eine spätere, separat freizugebende Integration:

```sh
export DASHBOARD_SERVICE_TIER=flex_fallback
export DASHBOARD_FLEX_RETRIES=2
export DASHBOARD_FLEX_TIMEOUT_SECONDS=900
```

Ohne `DASHBOARD_SERVICE_TIER` oder mit `default` bleibt der Standard-Requestbody
byteidentisch; genau ein Versuch, 60 s Socket-Timeout und 420 s Streamfrist.
Die neue Ergebnis-Metadatenpflicht erweitert die normalisierten Resultate; deren
vollständige JSON-Bytes können deshalb nicht gleichzeitig dem Original gleichen.
Die Standard-Tariffehlermeldung sowie fachliche Inhaltsprüfungen bleiben erhalten.

`flex_fallback` sendet `flex`. `DASHBOARD_FLEX_RETRIES` zählt Wiederholungen
zusätzlich zum Erstversuch: Standardwert 2 ergibt höchstens 3 Flex-Versuche.
Backoff: 2 s vor dem zweiten, 5 s vor dem dritten und jedem weiteren Versuch.
0 bedeutet einen Flex-Versuch und danach gegebenenfalls Standard. Annahme:
weitere ausdrücklich konfigurierte Wiederholungen bleiben bei 5 s Backoff.
Ungültige Modi, negative/nicht-ganzzahlige Retrywerte und nicht-positive oder
nicht-endliche Flex-Timeoutwerte führen zu einem Konfigurationsfehler. Flexwerte
werden im Standardmodus ignoriert. Kein automatischer Wechsel auf Flex.

Wiederholbar sind ausschließlich HTTP 429 mit `error.code` `flex_unavailable`
oder `resource_unavailable` beziehungsweise `error.type` `resource_unavailable`,
HTTP 500–599 und nachgewiesene Timeouts einschließlich gekapselter URLError-
Timeouts und Streamfristüberschreitungen. Andere HTTP-/Transportfehler, falsche
Tarife, Verweigerungen, fehlende/ungültige Inhalte und nicht abgeschlossene
Antworten lösen keine Wiederholung aus. Nach erschöpften Flex-Versuchen folgt
genau ein `default`-Versuch mit den bisherigen Standardfristen; auch sein Fehler
wird nicht wiederholt.

`requested_service_tier` benennt den letzten Versuch, `returned_service_tier`
dessen bereinigten Antworttarif und `flex_attempts` die gesamte Anzahl Flex-
Versuche. Jeder erfolgreiche Versuch akzeptiert ausschließlich seinen eigenen
angeforderten Tarif; fehlende, unbekannte und abweichende Tarife bleiben Fehler.
HTTP-Diagnose speichert ausschließlich `provider_error_code` und
`provider_error_type`, jeweils 1–80 Zeichen aus ASCII alnum / `._-` oder `None`.
Meldungstexte werden niemals übernommen. Das Lesen des Fehlerkörpers ist auf
65536 Bytes begrenzt; unlesbares/ungültiges JSON ergibt unbekannte Metadaten.
Auch Tokenzähler und Embedding-HTTP-Fehler verwenden diese Bereinigung, ohne
Flex-Retry. Embedding-Request und dessen Timeout bleiben bestehen.
Annahme: Diagnosefelder beschreiben den abschließenden Versuch; frühere
HTTP-Diagnosen werden nach erfolgreichem Retry nicht im finalen Ergebnis behalten.

## Preise und Reservierung

USD je 1 Million Tokens, Reihenfolge Input / Cached Input / Cache-Schreiben / Output:

| Modell | Standard | Flex |
| --- | --- | --- |
| gpt-6.1-sol | 2 / 0,10 / 2,50 / 10 | 1 / 0,05 / 1,25 / 5 |
| gpt-6-luna | 0,10 / 0,01 / 0,125 / 0,50 | 0,05 / 0,005 / 0,0625 / 0,25 |

Annahme aus Auftrag: Flex-Cache-Schreiben kostet 1,25 × Flex-Input. Für Luna
wird mangels angegebenem Schreibpreis derselbe Faktor in beiden Tarifen
angenommen. Die bisherigen Long-Context-Aufschläge für Sol bleiben in beiden
Tarifen erhalten; für Luna wird mangels Vorgabe kein solcher Aufschlag erfunden.
Die Provider-Modellfreigabe bleibt Sol und Embeddings; Luna erhält hier nur den
beauftragten Kostenweg, keine neue Produktions-Modellwahl.

`reserve_micro_usd()` verwendet ausschließlich `RATES` (Standard), mit bisherigen
Sol-Sicherheitsaufschlägen und vollständigem Outputmaximum. Tarifkonfiguration
verändert den Reservierungsbetrag nicht. `usage_micro_usd()` wählt `FLEX_RATES`
nur für einen tatsächlich zurückgegebenen Flex-Tarif. Ein unbekannter/fehlender
Tarif oder ungültige/nicht-finale Usage liefert `None`, niemals Nullkosten;
Ledger und lokale Budgetkontrolle behalten dann den reservierten Betrag.
Ganzzahlige Mikro-USD werden wie bisher aufgerundet; Reasoning wird nicht doppelt
abgerechnet. Erfolgreicher Standard-Fallback wird zum Standardpreis abgerechnet.

## Identität, bezahlte Antworten und Version

`durable_calls.py`, `DurableCalls.__call__()`: `value` enthält Modell, Prompt,
Outputmaximum, Schema und für Sol den bisherigen festen Identitätsmarker
`transport={'reasoning_effort':'medium','service_tier':'default'}`. Dieser Marker
ist ein historischer Identitätsbestandteil, nicht der tatsächlich gewählte
Transporttarif. Er wird weder entfernt noch durch einen Umgebungswert ersetzt.
`request=encode(value)` entsteht vor Provideraufruf und bleibt bei Flex,
Fallback und Standard identisch. Das tarifabhängige Ergebnis wird ausschließlich
in `response_json` abgelegt. Wiederverwendung erfolgt vor Provideraufruf über
reservierten Slot beziehungsweise `prior_calls`; die gespeicherte Antwort wird
ohne bezahltes Resenden gelesen. Für `question_calls.py` gilt derselbe feste
Marker. Beide Dateien benötigen keine Änderung.

`hybrid_pipeline.version()` wird nicht geändert und liest keine Tarifvariable.
Ein Wechsel zwischen `default` und `flex_fallback` in derselben Kopie ändert die
Pipelinekennung nicht. Wichtige Grenze: der bestehende Versionsalgorithmus
bezieht die Inhalte von `openai_provider.py` und `call_budget.py` ein. Diese
Codeänderung gegenüber dem Release kann deshalb die Kennung ändern, auch wenn
die reine Tarifkonfiguration sie nicht verändert. Ein historisches Release-
Versionskennzeichen wird nicht erfunden oder durch einen neuen Algorithmus
überschrieben. Begründung: blindes Entfernen von Versionsbestandteilen könnte
auch fachlich inkompatible Antworten wiederverwenden. Vor einem Rollout müssen
bestehende Jobs/Revisionen und bezahlte Slots gezielt zugeordnet werden; niemals
wegen einer neuen Kennung bereits bezahlte Anforderungen automatisch neu senden.
Die Tests belegen Requestidentität und Wiederverwendung innerhalb eines festen
Pipeline-/Revisionskontexts, keine produktive Migration zwischen Releases.

Die Quellkopie enthält kein `evaluation/source-corrections.json`, obwohl die
Versionsfunktion diese Datei erwartet. Sie wird hier nicht durch erfundene
Korrekturdaten ersetzt. Der Versions-Konfigurationstest simuliert nur diese
fehlende Ressource mit `{}`; die übrigen Versionsinputs werden real gelesen.
Eine vollständige Pipeline-Ausführung/Produktions-Versionskennung ist damit
nicht nachgewiesen und benötigt die autoritative Ressource vor einer Integration.

## Fristen, Lease und verbleibende Risiken

Die ursprüngliche 420-s-Streamfrist reicht für einen erlaubten 900-s-Flex-Versuch
nicht. In Flex-Versuchen nutzt `collect_stream()` deshalb die konfigurierte
Flexfrist; der Standard-Fallback nutzt wieder 420 s. Die Socketfrist ist bei
Flex ebenfalls 900 s, bei Standard 60 s. Die Streamdeadline wird zwischen
empfangenen Zeilen geprüft, kein harter Prozess-Wallclock-Abbruch; eine
blockierende Leseoperation kann bis zur Socketfrist zusätzlich warten.

Die gelesenen Quell-SQLs `20260906220626_working_memory_durable_queue.sql`,
`20260906235000_working_memory_job_recovery.sql` und
`20260908165134_working_memory_hybrid_durability.sql` setzen/verlängern Leases
auf 10 Minuten (600 s). Der Providerpfad erneuert während des Streams keine
Lease. Bereits ein 900-s-Versuch kann sie überschreiten; drei Flex-Versuche
plus 7 s Backoff und Standard-Fallback ergeben als Fristenplanung 3127 s,
zuzüglich möglicher blockierender Lesezeit und weiterer Pipelinearbeit.
Ein kleinerer einzelner Flex-Timeout löst daher nicht automatisch das Gesamtproblem.
Vor Produktivaktivierung wäre eine geprüfte Lease-Erneuerung mit verlässlicher
Owner-/Abbruchlogik oder eine ausreichend große, abgestimmte Lease nötig, ferner
Prüfung von Worker-/Proxy-/Gateway-/Streamfristen. Lease/SQL/Streaming-Infra wird
in diesem Auftrag nicht geändert; aktuelle Serverkonfiguration wird nicht geprüft.

Timeout und 5xx beweisen nicht, dass ein Versuch unbezahlt blieb. Der beauftragte
Retry kann bereits bearbeitete, aber nicht empfangene Antworten erneut anfordern.
Keine Idempotenzgarantie wird behauptet. Abrechnung hier bewertet die finale
empfangene Usage, nicht unbekannte frühere Versuchskosten; eine Standard-
Reservierung pro logischem Aufruf garantiert daher keine Obergrenze für kumulierte
Providerkosten mehrerer möglicherweise bezahlter Versuche. Zusätzliche unbekannte
Kosten/Ergebnisse sind vor Produktivaktivierung zu klären. Ein erfolgreich
gespeicherter finaler Call wird anschließend durch den Ledger wiederverwendet.
Der im Auftrag genannte 1/3-Erfolg ist Kontext, kein Zuverlässigkeitsnachweis dieser
Implementierung. Alle Tests sind Mock-Tests; kein Tarifpreis, echter Provider-
Fallback, echtes Streaming oder Live-Ledger wurde ausgeführt.

## Rückweg

Für Transport-Rollback: `DASHBOARD_SERVICE_TIER=default` setzen oder die Variable
entfernen; Flex-Retry-/Timeoutvariablen haben dann keine Wirkung. Aufbewahrte
Antworten und Receipts bleiben zur Wiederverwendung erhalten. Ein Code-Rollback
bei einer später separat genehmigten Integration würde die vor dieser Integration
gesicherten beiden Backend-Dateien wiederherstellen; keine historischen Call-
Slots, Receipts oder Kostenaufzeichnungen löschen. Diese Lieferung ist eine
offline geprüfte Kopie, keine installierte oder veröffentlichte Änderung.

## Prüfergebnis

Abschließender Gesamtlauf: 37/37 Tests bestanden mit
`python3 -I -B -m unittest`, 0,038 s am 2026-10-13 11:48:58 UTC.
Details: `TEST-RESULTS.txt`. Frisches unabhängiges Read-only-Review
`flex_review`: für das begrenzte Offline-Paket abnahmefähig, kein belegter
Zielblocker oder relevante Regression. Der Reviewer führte 32/32 schreibfreie
Tests selbst aus und las den 37/37-Gesamtnachweis; Receipt-Schreibtests wurden
im Review nicht erneut ausgeführt. Die Interpretation terminaler HTTP-Diagnose
und die dokumentierte Versionsgrenze wurden geprüft und akzeptiert. Kosten-
Ungewissheit früherer Versuche, Lease-/Timeoutkonflikt und fehlende Versions-
Ressource bleiben Integrationsrisiken, keine behauptete Produktivabnahme.
Die unabhängige Prüfung ist belegt; eine technische Laufzeitdurchsetzung von
Governance-Gates wurde in diesem Paket weder eingerichtet noch getestet.
Keine Git-Versionierung: Der erlaubte Schreibbereich schließt `.git` aus.
