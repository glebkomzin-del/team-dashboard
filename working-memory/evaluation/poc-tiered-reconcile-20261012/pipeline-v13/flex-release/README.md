# Flex-Release, Paket 1

Auftrag FLEX-RELEASE: ausschließlich dieses Verzeichnis; Stdlib und `python3 -I -B`;
keine Netzwerk-, API-, Server-, Secret-, Git- oder Deploymentoperationen. Preise
und Kapazitätsmessung sind Eingaben des Auftrags, keine hier nachgemessenen Werte.
Das Paket liefert zwei austauschbare Produktionsdateien und einen Offline-Buildkontext.
Lokale Mock-Abnahme und tatsächliche Container-/Produktionsabnahme bleiben getrennt.

## Dateien und Prüfstand

- `openai_provider.py`, `call_budget.py`: von den maßgeblichen Produktionsdateien abgeleitet.
- `overlay/`: bytegleiche Kopien dieser zwei Dateien und `Dockerfile`.
- `make_manifest.py`: erzeugt `overlay/build-manifest.json` aus einem übergebenen Produktionsmanifest.
- `offline_check.py`: 14 einzeln gemeldete Prüfungen, Exitcode 1 bei Fehlern.
- `run_tests.py`, `test_provider.py`, `test_budget.py`, `test_manifest.py`, `test_offline.py`: Offline-Unittests.
- `TEST-RESULTS.txt`, `OFFLINE-RESULTS.txt`: tatsächlich ausgeführte Abschlussprüfungen.
- `REVIEW.md`: unabhängiges Read-only-Abnahmeergebnis.

Tatsächlicher Prüfstand: **31/31 Unittests**, **14/14 Offlineprüfungen**, jeweils
`python3 -I -B`; Ausgabe in den beiden Ergebnisdateien. Alle HTTP-Ergebnisse waren
synthetische Mocks. Container-/Live-Ausführung und Produktionsmanifest bleiben offen.
Unabhängiges Review: **ACCEPT für den vereinbarten Offlineumfang**, 16 gezielte
Providertests selbst ausgeführt; Befunde und Grenzen in `REVIEW.md`.

| Datei | Zeilen insgesamt | Gegenüber Produktion hinzugefügt | Entfernt |
| --- | ---: | ---: | ---: |
| `openai_provider.py` | 444 | 206 | 9 |
| `call_budget.py` | 121 | 2 | 2 |

Providerdiff: optionale Tarifvalidierung, Metadatum für Versuche, ausschließlich
positive 429-Kapazitätsentscheidung und gemeinsame Frist/Zulassungssperre.
Budgetdiff: tatsächlicher Flex-Tarif erlaubt und dessen Input-/Outputpreis halbiert;
Reservierungsfunktion und übrige Modellpreise bleiben produktionsgleich.
Keine Git-Versionierung, weil `.git` außerhalb der erlaubten Schreibgrenze liegt.
Keine Außenverzeichnis-Baselines, Zeitstempelvergleiche oder Integritätsnachweise.

## Transport und Umgebungsvariablen

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `DASHBOARD_SERVICE_TIER` | `default` bei unset | `default` oder `flex_fallback`; andere Werte sind Konfigurationsfehler. |
| `DASHBOARD_FLEX_RETRIES` | `2` | Zusätzliche Flex-Versuche; nichtnegative ganze Zahl. |
| `DASHBOARD_FLEX_TIMEOUT_SECONDS` | `480` | Gesamte Flex-/Fallback-Kette; größer 0 und höchstens 480. |

Unset/default bewahrt Produktions-Requestbytes, Validierung, Socketfrist 60 s,
Streamfrist 420 s und Fehlerbehandlung. Nur das generative Ergebnis erhält zusätzlich
`flex_attempts=0`. Flex-Variablen werden in diesem Modus ignoriert. Tokenzähler und
Embeddingpfad behalten ihr Produktionsverhalten.

Flex sendet `service_tier=flex`. Nur HTTP 429 mit vollständig geparstem JSON und
`error.code == 'flex_unavailable'` oder `error.type == 'resource_unavailable'`
erlaubt einen weiteren Dispatch. Backoff: 2 s, dann 5 s; weitere konfigurierte
Wiederholungen ebenfalls 5 s. Zwei Retries erlauben drei Flex-Versuche, danach
höchstens einen Standardversuch. Ein vorhandenes Zeitfenster ist für jede
Zulassung eines Versuchs erforderlich. Zulassung, Deadlineprüfung und Abbruch sind
durch eine gemeinsame Sperre geordnet; nach Abbruch wird kein weiterer Versuch zugelassen.
HTTP 429 anderer Art, Timeout, Verbindungsabbruch, 5xx, unvollständiger Stream,
fehlender oder falscher Tarif erlauben weder Retry noch Fallback.

Der HTTP-Fehlerkörper wird nur für diese Entscheidung begrenzt gelesen (65536 Bytes).
Ungültiges, übergroßes, mehrdeutiges JSON mit doppelten Schlüsseln oder ungültigen
Konstanten erlaubt keine Wiederholung. Code, Typ und Meldung werden weder geloggt
noch als zusätzliche HTTP-Diagnose im Ergebnis gespeichert. Erfolgreiche Antworten
akzeptieren nur den Tarif des jeweiligen Versuchs. `requested_service_tier` beschreibt
den abschließenden Versuch, `returned_service_tier` dessen tatsächlichen Tarif und
`flex_attempts` die Anzahl zugelassener Flex-Versuche. Beide Requestarten behalten
`prompt_cache_options: {'mode': 'explicit'}`.

## Fristen und Lease

Produktionsbelege (Alias `PROD` unten): `openai_provider.py:212` Socket 60 s,
`:213` Stream 420 s, `:125` Deadlineprüfung nach gelesener Zeile. Ein langsam
ankommender Teil einer SSE-Zeile kann die reine Socket-Inaktivitätsfrist umgehen.
`hybrid_pipeline.py:167` erneuert die lokale Stage-Lease auf 600 s.
`compact_reconcile.py:176` ruft genau diese `stage()` auf und setzt keine eigene
Adapterfrist; die Compact-Aufrufe verwenden somit dieselbe Stream-/Lease-Kette.
Die SQL-Quelle `working-memory/supabase/migrations/20260908113112_extend_working_memory_model_call_slots.sql:30`
verlangt eine gültige Lease; `:54` verlängert neue Reservationsslots um zehn Minuten.
Kein SQL-Deploymentstatus wurde geprüft. `durable_calls.py:69` reserviert vor Versand;
der Adapter erneuert während des Transports keine Lease.

900 s sind schon für einen einzelnen Flex-Versuch nicht lease-kompatibel. Deshalb
ist 480 s der neue Flex-Standard und die Obergrenze; die Gesamtfrist enthält alle
Flex-Versuche, Backoffs und den Standardfallback. Dessen Streamfrist beträgt höchstens
420 s und wird durch die verbleibende Gesamtfrist verkürzt. Ein separater wartender
Aufrufer begrenzt auch blockierende Teilzeilen und Fehlerkörper auf die Gesamtfrist.
Bei Ablauf wird `TimeoutError`/Unknown zurückgegeben und weitere Versuchszulassungen
werden gesperrt. Ein bereits zugelassener daemonisierter Versuch kann seinen
tatsächlichen HTTP-Versand erst später beginnen oder noch auslaufen. Er gehört zum
Unknown-Ausgang; physischer Transportabbruch wird nicht behauptet. Weder sein spätes
Resultat noch weitere Wiederholungen erreichen die Konsumenten oder Veröffentlichung.
Der Defaultpfad bleibt ohne diesen Thread unverändert.

480 s lassen nominal 120 s bis zur 600-s-Lease für Rückgabe und Persistenz.
Scheduling und Datenbanklatenz sind keine hier bewiesene Garantie. Die tatsächliche
Lease-Konfiguration und Container-/Workerintegration benötigen spätere autorisierte
Prüfung. Die Caller-Frist umfasst auch die eigene Standardfrist `min(Gesamtdeadline,
Standardbeginn + 420)`. Die Sperre vor und nach Versuchszulassung sowie blockierende
synthetische Flex-/Standardtransporte werden gezielt geprüft. Unknown darf nicht
neu gesendet werden. Diese Zulassungsdefinition ist die dokumentierte technische
Annahme: Nur eine vor Abbruch zulässige Anfrage kann später noch übertragen werden.

## Kosten

USD je Million Tokens, ausschließlich `gpt-6.1-sol`:

| Tarif | Input | Cached | Cache-Schreiben | Output |
| --- | ---: | ---: | ---: | ---: |
| Standard | 2,00 | 0,10 | 2,50 | 10,00 |
| Flex | 1,00 | 0,05 | 1,25 | 5,00 |

Reservierungen verwenden unverändert Standardpreise, Schreib-/Long-Context-/Regional-
Reserven und das volle Outputmaximum. Abrechnung verwendet ausschließlich den
tatsächlich zurückgegebenen Tarif, mit produktionsgleicher Aufrundung auf ganzzahlige
Mikro-USD. Unbekannter Tarif oder unbrauchbare Usage ergibt `None`; die Reserve bleibt
belastet. Reasoning wird nicht doppelt berechnet. Andere Modelle bleiben unverändert.
Nur sicher unverarbeitete Kapazitätsablehnungen werden wiederholt; unbekannte
vorherige Versuchskosten werden nicht durch eine billige letzte Antwort verdeckt.

## Identität und Kompatibilität: tatsächliche Grep-Belege

`PROD` bezeichnet:
`/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/prod/`.
`FLEX` bezeichnet das benachbarte `../flex/`. Seine zusätzlichen Backenddateien
sind Referenzen, keine belegten aktuellen Produktionskopien.

| Quelle:Zeile | Gelesene Felder / Identitätsbestandteile |
| --- | --- |
| `PROD/durable_calls.py:54` | `model`, `prompt`, `max_tokens`, `schema` |
| `PROD/durable_calls.py:56` | Festes `transport.reasoning_effort=medium`, `service_tier=default`, `prompt_cache_options.mode=explicit` |
| `PROD/durable_calls.py:47`, `:58`, `:59` | Optional `scope.pipeline`, `scope.revision`; anschließend kanonisches `encode(value)` |
| `PROD/durable_calls.py:69`, `:71` | Reservation und Request-SHA; Ergebnisfelder fließen nicht in die Requestidentität ein. |
| `PROD/durable_calls.py:85`, `:93`, `:98` | Kostenfunktion, `error`, `terminal_status`; Ergebnis wird vollständig gespeichert. |
| `PROD/hybrid_pipeline.py:37`, `:39`, `:170` | `stop_reason`, `content[].type/text`, `usage.input_tokens` in `stage()` |
| `FLEX/canonical_worker.py:124`, `:125` | `primary_responses`, delegiert deren Inhalt an `future_summary.from_response` |
| `FLEX/future_summary.py:33` | Delegiert gelesene `content[].type/text`; neue Tarifmetadaten werden nicht ausgewertet. |
| `FLEX/question_calls.py:38`, `:40`, `:41`, `:53` | Vollständiges Resultat speichern/zurückgeben und Kostenfunktion; keine neue Metadatenpflicht |
| `FLEX/processor.py:207` | `usage`, `elapsed_seconds`, `stop_reason`, `content` |

`durable_calls.py` gehört nicht zum Overlay. Seine festen Identitätsschlüssel werden
nicht verändert. Offline werden beide Modi durch den tatsächlichen Produktions-
`DurableCalls`-Reservationpfad geschickt und Requestbytes/Hashes verglichen. Vorhandene
Antworten werden dabei synthetisch wiederverwendet; es werden keine Receipts geschrieben.
Die Konfiguration ändert die Requestidentität nicht. Codeänderungen können trotzdem
die Pipelinekennung verändern (`PROD/hybrid_pipeline.py:27` bis `:33`);
bezahlte Antworten dürfen deswegen nicht automatisch erneut gesendet werden.

## Manifest und Overlay

Das Produktionsmanifest fehlt lokal. Kein Ersatzmanifest wird erfunden.
`production-cost-20261012/cache-build.json` ist ein Buildreceipt mit `deltas`, nicht
das Produktionsmanifest. `production-cost-20261012/rollout_cache.py:55`, `:57`, `:58`
liest das Manifest als Top-Level-JSON-Objekt und ersetzt `manifest[name]` durch SHA-256.
Annahme: ausschließlich Pfad-Strings als Schlüssel und 64-stellige SHA-256-Strings
als Werte; genau `openai_provider.py` und `call_budget.py` müssen bereits vorkommen.
Verschachtelte Formate, fehlende Einträge und doppelte Schlüssel werden abgelehnt.
Alle übrigen Schlüssel/Werte bleiben unverändert; JSON-Whitespace kann sich ändern.
Es werden nur die zwei gelieferten Overlaydateien gehasht, keine Außenbaselines.

Später, mit einem separat bereitgestellten Manifest, im Paketverzeichnis:

```sh
python3 -I -B make_manifest.py /path/to/production/build-manifest.json
```

Der Buildkontext erbt die vorhandene Imageversion per `ARG OLD_TAG`/`FROM ${OLD_TAG}`.
Er kopiert ausschließlich beide Adapterdateien und das erzeugte Manifest nach `/app/`;
`USER root`, `COPY --chown=10001:10001`, anschließend `USER 10001:10001` entsprechen
dem Produktions-Dockerfile. Kein neues Basisimage oder Runtimepaket wird eingeführt.
Dockerbuild und Containerstart sind in diesem Auftrag nicht ausgeführt.

## Offlineprüfung, Aktivierung und Rückweg

```sh
python3 -I -B run_tests.py
python3 -I -B offline_check.py --local
```

Lokal importiert das Skript die echten zusätzlichen Referenzmodule und die maßgebliche
Produktions-`durable_calls.py`. Für die reale Versionsfunktion wird ausschließlich
das fehlende `evaluation/source-corrections.json` im Speicher durch `{}` ersetzt.
Diese Ausgabe ist ausdrücklich `pipeline_local_asset_stub`, keine Produktionskennung.
Die neuen Adapterdateien gehen in die lokale Versionsberechnung ein.
Im Container, mit vorhandenen vollständigen Produktionsressourcen:

```sh
PYTHONPATH=/app python3 -I -B /path/to/offline_check.py
```

`-I` ignoriert `PYTHONPATH`; das Skript fügt deshalb `/app` selbst ein. Der Containerpfad
verwendet keine Stubs. Syntax, reale Pipelinekennung im Format
`v11:compact1:gate1:gpt-6.1-sol:<16hex>:canonical1:<16hex>`, Standard-Requestbytes,
Flex-/Fallback-/Fehlerpfade, Kosten und Durableidentität werden geprüft. Ein Audit-Hook
sperrt Netzwerkverbindungen; alle Transportchecks mocken Keybeschaffung und HTTP.

Eine spätere, gesondert autorisierte Aktivierung gehört in den Compose-Service:

```yaml
services:
  canonical-draft:
    environment:
      DASHBOARD_SERVICE_TIER: flex_fallback
      DASHBOARD_FLEX_RETRIES: "2"
      DASHBOARD_FLEX_TIMEOUT_SECONDS: "480"
```

Rückweg: `DASHBOARD_SERVICE_TIER: default` setzen oder diese Variable aus Compose
entfernen. Bei Code-Rollback das vorherige `OLD_TAG` samt zugehörigem Manifest verwenden.
Bezahlte Receipts, Unknown-Slots und Kontext-/Pipelinezuordnungen bleiben erhalten.
Produktionsaktivierung, Containerprüfung, Manifestbeschaffung und echte Wiederherstellung
sind nicht Teil der ausgeführten Offline-Abnahme.
