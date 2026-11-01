# Release 3: Wartende Hot-Set-Aufgaben behalten

Stand: 2026-10-13. Offline-Erweiterung von Release 2 um genau eine Filterregel. Basisimage: `dashboard-memory:release2-20261013`. Implementiert und lokal geprüft; kein Build, Containerlauf, Push, Deploy, Server-, Netzwerk- oder Providerzugriff. Nur Stdlib und `python3 -I -B`. Schreibgrenze ausschließlich dieses Verzeichnis; daher kein Git-Commit. Versionsbindung durch bestehende Quellfingerprints und Buildmanifest.

## Dateien

`overlay/` enthält nur geänderte Runtime-Dateien plus Buildrezept und Manifest:

| Datei | Änderung |
| --- | --- |
| `candidate_filter.py` | Optionales `keep_waiting=False`: exakter Status `waiting` erfüllt eine weitere ODER-Regel; stabiler Eingabeorder und unveränderte Objekte |
| `hybrid_pipeline.py` | Neuer Schalter, Konfigurationsfehler und Kennungssuffix; Übergabe an Filter |
| `offline_check.py` | Wartend-Regel, neue Schalterprüfung und Suffixreihenfolge; vier Manifestpayloads |
| `default_contract.json` | Ausschließlich `pipeline_version` angepasst; synthetische Prompt-/Schema-/Requestreferenzen entsprechen Release 2 |
| `build-manifest.json` | Lokales Manifest aus Release-2-Manifest mit vier aktualisierten Payloads |
| `Dockerfile` | `ARG OLD_TAG`, `FROM ${OLD_TAG}`, root-COPY mit UID/GID 10001, anschließend USER 10001:10001 |

Außerhalb des Overlays: `make_manifest.py` wiederverwendet die Validierungs-/Update-/Versionslogik aus `../release2/make_manifest.py`; nur `TARGETS`/`EXISTING` betreffen jetzt die vier kopierten Payloads. `local_support.py` übernimmt Release-2-Offlineunterstützung mit Release-3-Schreibroot und read-only Release-2-Fallback. `run_tests.py` führt die bestehenden Release-2-Testdateien unverändert aus; nur deren temporäre Ausgabe-/Overlaypfade und Modulauflösung werden umgebogen. `tests/test_waiting.py` ergänzt synthetische Fälle. `offline_check.py` im Paketroot ist der vorhandene CLI-Wrapper. Die numerischen Belege liegen in `before-tests.json`, `after-tests.json`, `new-tests.json` und `offline-results.txt`.

## Schalter und Auswahl

```text
DASHBOARD_HOTSET_FILTER=1
DASHBOARD_HOTSET_AGE_DAYS=30
DASHBOARD_HOTSET_RANK=8
DASHBOARD_HOTSET_KEEP_WAITING=1
```

Nur der exakte Wert `1` aktiviert die neue Regel, und nur bei `compact=True` und `DASHBOARD_HOTSET_FILTER=1`. Fehlender Wert entspricht `0`. Jeder explizite andere Wert als `0` oder `1` ist ein `ValidationError`, auch bei ansonsten inaktiver Regel; Prüfung vor Jobregistrierung. Die bisherigen Schalter und deren Release-2-Verhalten werden nicht verändert.

Jede dem Filter übergebene Aufgabe mit `status == 'waiting'` bleibt erhalten, unabhängig von Alter, Work-Suchrang oder exakter ID-Erwähnung. Die bestehenden Regeln sind weiterhin ODER-verknüpft. Status fehlt, ist null oder anders geschrieben: kein Wartend-Schutz; bestehende Alters-/Rang-/ID-Regeln greifen unverändert. `stats['waiting']` zählt bei aktivierter Regel unabhängig von überlappenden Gründen jede behaltene wartende Zeile einmal. Bei AUS fehlt dieser neue Schlüssel, damit bisherige Statistikbytes erhalten bleiben.

Annahme zum Umfang: „jede Aufgabe“ bezeichnet die vorhandene Filtereingabe aus der bisherigen Kandidatenauswahl. Nicht gefundene/unselektierte Aufgaben werden durch diese Änderung nicht zusätzlich gesucht oder aufgenommen. Die bisherige vorgelagerte Auswahl bleibt unverändert.

## Kennung, Fingerprints und Manifest

Suffixreihenfolge bleibt Hot-Set, zusätzliche Wartend-Regel, Delta, anschließend bestehender Canonical-Suffix:

```text
:hotset1:age=30:rank=8:wait1:delta2:canonical1:<fingerprint>
```

Ohne neue Regel ist der Featuresuffix exakt der Release-2-Suffix. Explizite Kennungen werden nach bisheriger Logik einmal mit dem vollständigen aktuellen Featuresuffix ergänzt. Standardwerte für Alter/Rang bleiben 30/5; Rang 8 ist nur das Auftragsbeispiel.

Die bestehenden Quelllisten in `hybrid_pipeline.version()` und `canonical_worker.pipeline_version()` enthalten bereits `candidate_filter.py` und `hybrid_pipeline.py` und bleiben unverändert. Geänderte Quellen führen deshalb auch bei AUS zu anderen Revisionsfingerprints. Byteidentische Kennung gegenüber Release 2 wird bei **gleichem Fingerprint-Eingabestand** geprüft: beide Versionsfunktionen lesen dieselben Quelldateien. Zusätzlich werden im vollständigen synthetischen Pipelinefluss identische explizite Kennungen, Prompts, Ergebnisse und Statistikbytes gegen direkt geladenen Release-2-Code geprüft, für Filter AUS/AN und Delta AUS/AN. Release-2- und Release-3-Revisionshashes werden nicht künstlich gleichgesetzt. `default_contract.json` ändert nur die daraus abgeleitete erwartete Kennung.

Lokaler geprüfter AUS-Stand:

```text
v11:compact1:gate1:gpt-6.1-sol:b44964adc67bfefb:canonical1:d6198b7958d46e3e
```

Das beiliegende Manifest ist lokal aus `../release2/overlay/build-manifest.json` erzeugt. Später auf dem Server muss das dortige Produktionsmanifest als Eingabe verwendet werden, keine hier angenommene Servermap. Aus `release3/`:

```sh
python3 -I -B make_manifest.py /app/build-manifest.json
```

Dies ist eine spätere Anleitung, kein ausgeführter Serverbefehl. Das Skript aktualisiert genau die vier COPY-Payloads und erhält andere Manifestwerte unverändert; das Manifest enthält keine Selbsthashreferenz. Das Dockerfile ist kein Runtimepayload. Als `OLD_TAG` ist `dashboard-memory:release2-20261013` zu übergeben. Kein Dockerbau wurde ausgeführt.

## Tatsächlich ausgeführte lokale Prüfung

Befehle aus `release3/`:

```sh
python3 -I -B run_tests.py before
python3 -I -B make_manifest.py ../release2/overlay/build-manifest.json --local-version
python3 -I -B run_tests.py after
python3 -I -B run_tests.py new
python3 -I -B offline_check.py --local
```

| Prüfung | Bestanden / Gesamt | Failure / Error / Skip |
| --- | --- | --- |
| Unveränderte Release-2-Tests vor Erweiterung | 79 / 79 | 0 / 0 / 0 |
| Unveränderte Release-2-Tests mit Release-3-Overlay | 79 / 79 | 0 / 0 / 0 |
| Neue Release-3-Tests | 19 / 19 | 0 / 0 / 0 |
| Gemeinsamer Teststand nach Erweiterung | 98 / 98 | 0 / 0 / 0 |
| Containerprüfer lokal | 10 / 10 | Exit 0 |

Neue Tests: Wartend allein, exakter Status und fehlende/null Voraussetzungen, sämtliche 16 Kombinationen der vier Gründe, Reihenfolge/Objektidentität/Nichtmutation, AUS-Filterbytes gegen Release 2, Nullschwellen, ungültige Parameter, vollständiger synthetischer Pipelinefluss einschließlich Wartend+Delta, unveränderte AUS-Prompts und Kennungen, inaktiver Schalter, Konfigurationsfehler vor Registrierung, Suffixreihenfolge und Manifest/COPY-Vertrag. Keine Meeting-Inhalte in Berichten; nur Test-IDs, Zahlen und Fehlerklassen/Dateipositionen.

Container-Einstieg später: `PYTHONPATH=/app python3 -I -B /app/offline_check.py`. Der Prüfer setzt `/app` selbst in `sys.path`, weil `-I` PYTHONPATH ignoriert. Er erzwingt AUS-Werte für die Referenzprüfungen und prüft die aktivierten Schalter in isolierten Umgebungen. Mocktransport führt keinen Netzwerkzugriff aus. Lokale Fallbackassets stammen wie bei Release 2 aus den vorhandenen Evaluationdateien; deren Gleichheit mit tatsächlichen Imageassets ist nicht durch einen Containerlauf nachgewiesen. Die allgemeine prod2-Bestandssuite mit historischen Fehlern ist nicht die hier beauftragte Release-2-Suite und wurde nicht erneut ausgeführt.

Unabhängiges frisches read-only GOAL_GATE-Review abgeschlossen: kein relevanter Befund, keine belegten Pflichtblocker. Der Reviewer prüfte Originalcode, Tests und Belege, bestätigte vier aktualisierte Manifestpayloads und den Buildvertrag; keine wiederholten Testläufe, kein Container- oder Produktionsnachweis. Dies belegt ein durchgeführtes Review, keine technische Runtime-Gate-Durchsetzung. Die 79 bestehenden Testoutcomes unterscheiden sich vorher/nachher in 0 Fällen. Der Offlineauftrag ist abgeschlossen; Build, Deployment und produktiver Nutzerfluss bleiben außerhalb dieses Auftrags.

## Rückweg und Risiken

Feature-Rückweg: `DASHBOARD_HOTSET_KEEP_WAITING` auf `0` setzen beziehungsweise entfernen; damit gelten sofort bei nächster Konfigurationsübernahme die bisherigen Filterregeln. Keine Compose-/Serveränderung ist Teil dieses Pakets. Die Release-3-Quellrevision bleibt dabei sichtbar. Vollständiger Code-Rückweg: Basisimage `dashboard-memory:release2-20261013` und Schalter `0`. Kein Daten-/Schemaformat verändert; frühere verarbeitete Ergebnisse werden nicht rückwirkend entfernt.

Risiken: Aktiviert können alte wartende Kandidaten Katalog-/Promptgröße und spätere Verarbeitungskosten erhöhen. Nicht wartende Kandidaten unterliegen weiterhin den bisherigen Filterrisiken. Bestehende Wartend-Aufgaben außerhalb der Kandidateneingabe werden nicht zusätzlich gefunden. Bytegleichheit der AUS-Prompts ist mit synthetischen Fällen belegt; lokale Checks sind weder produktive Ausführung noch menschliche Fachabnahme. Runtime-Gate-Durchsetzung und Datenwiederherstellung werden durch dieses Offlinepaket nicht behauptet.
