# Release 2: Offline-Overlay auf prod2

Stand: 2026-10-13. Auftrag: Diagnose sowie Delta v2 und Hot-Set für den aktuellen v11-Produktionspfad vorbereiten. Kein Build, Push, Deployment, Server- oder Providerzugriff. Alle Schreibarbeiten dieses Pakets liegen in `release2/`; Git-Versionierung entfällt wegen dieser ausdrücklichen Schreibgrenze. Version und Manifest binden den Paketstand, nicht einen Git-Commit. Der bestehende Flex-Fallback bleibt aus dem Basisimage erhalten.

Abschluss: Offlinepaket implementiert und lokal geprüft. Frisches unabhängiges read-only GOAL_GATE-Review: abnahmefähig, keine belegten Pflichtblocker; bestehende rote Tests, Produktionsassets und tatsächlicher Containerlauf ausdrücklich getrennt. Dies ist ein durchgeführtes Review, kein Nachweis einer technischen Laufzeitsperre. Bearbeitungszeit etwa 18 Minuten; Paket nach Scratchbereinigung 344 KiB.

## Dateien und Kontext

`overlay/` ist der vollständige kleine Docker-Buildkontext:

| Datei | Änderung |
| --- | --- |
| `canonical_worker.py` | Eine sichere stderr-Diagnose nach bestätigter bestehender Job-Isolation; neue Fingerprintmodule |
| `compact_reconcile.py` | Opt-in Delta-Instruktion, Schema und Decoder vor bisherigen Prüfungen |
| `hybrid_schema.py` | Delta-v2-Schema; bestehende Schemafunktionen unverändert |
| `hybrid_pipeline.py` | Opt-in Hot-Set, separate Work-Suchreihenfolge, Fingerprints und Featuresuffixe |
| `candidate_filter.py` | Geprüfte v12-Auswahlregel, konservativ bei unbekanntem Datum |
| `delta_codec.py` | Explizite Entscheidungen, vollständige disjunkte Coverage, getrennte Archivprojektion |
| `offline_check.py` | Container-Prüfer ohne Netzwerk; Exit ungleich 0 bei Fehlern |
| `default_contract.json` | Synthetische erwartete Prompt-/Schema-/Requestbytes aus prod2 sowie AUS-Kennung |
| `build-manifest.json` | Produktionsmap mit genau acht aktualisierten/ergänzten Runtimepayloads |
| `Dockerfile` | `ARG OLD_TAG`, Basisimage, root-COPY mit UID/GID 10001, Rückkehr zu 10001 |

`make_manifest.py` aktualisiert nur die acht tatsächlich nach `/app/` kopierten Payloads. Alle anderen übergebenen Einträge bleiben gleich, auch `openai_provider.py` und `call_budget.py`. Das Dockerfile ist Buildrezept und wird selbst nicht nach `/app/` kopiert; sein alter Runtime-Manifesteintrag bleibt deshalb erhalten. Das Manifest enthält keine eigene Selbsthashreferenz.

Außerhalb des Buildkontexts: `tests/`, `run_tests.py`, `roundtrip.py`, `local_support.py`, `generate_contract.py`, CLI-Wrapper `offline_check.py` und numerische Prüfergebnisse. Keine echten Antworten werden kopiert. Kein Zusatzpaket, keine Dependencyinstallation.

## Schalter und Aktivierung

Aktivierung ausschließlich über den vorhandenen Compose-`environment:`-Block; keine Änderung einer Compose-Datei gehört zum Paket:

```yaml
environment:
  DASHBOARD_DELTA_OUTPUT: "0"
  DASHBOARD_HOTSET_FILTER: "0"
  DASHBOARD_HOTSET_AGE_DAYS: "30"
  DASHBOARD_HOTSET_RANK: "5"
```

Für B beziehungsweise C den jeweiligen Wert auf `"1"` setzen. Fehlend und jeder andere Wert bedeuten AUS. Beide Optimierungen gelten wie die geprüfte v12-Integration ausschließlich für `compact=True`, also Produktion `MEMORY_PROMPT_VERSION=v11`; der v10-Pfad ignoriert sie. Negative oder ungültige aktive Hot-Set-Parameter scheitern ausdrücklich; ausgeschaltet werden sie nicht gelesen.

A ist immer aktiv und besitzt absichtlich keinen Ausschalter. Genau beim bestehenden bestätigten `isolated=True`-Review-Return wird eine JSON-Zeile geschrieben. Pausen, unbestätigte Isolation und sonst weiterhin propagierende Ausnahmen ändern ihr bisheriges Verhalten nicht. Keine neue Fangregel, Datenbankänderung oder Isolation. `stage` ist der letzte ermittelbare Traceback-Funktionsname, sonst null. Meldungen verlieren Steuerzeichen und den Teil ab erstem Anführungszeichen/Doppelpunkt; maximal 240 Zeichen. stderr-Fehler verändern das Ergebnis nicht.

B übernimmt pro `source_index` zwingend `decision={update_target,update,matter_id}` einschließlich explizitem null. Nur übrige Abweichungen stehen in `changes`. Endformen benötigen jede Beobachtung genau einmal und eine vollständige, disjunkte Vereinigung von `work_results` und `unchanged_work_indices`; erst danach werden unchanged-Plätze ergänzt. Nachforderungen bleiben mit `open_ids`, leeren Beobachtungen und null-`work_results` erlaubt. Rekonstruktion erfolgt vor Aliasauflösung, Original-, Confidence-, Lifecycle- und Gate-Prüfungen.

C prüft die bisherigen ausgewählten Work-Kandidaten: Alter höchstens A Tage ODER nullbasierter Work-Suchrang kleiner k in einer Beobachtungsanfrage ODER ID im Original. Eine gesonderte Work-Suche liefert die Rangreihenfolge; gemischte Archivsuche bestimmt den Rang nicht. Verworfene Work-Einträge und Work-Suchtreffer fehlen im Modellkatalog und nachfolgenden Gate. Bei unbekanntem/ungültigem Datum wird konservativ behalten. Broad-Topic-Suchanfragen allein gewähren keinen Rangschutz.

## Kennung und Manifest

Beide neuen verhaltensrelevanten Module fließen bei compact auch ausgeschaltet in `hybrid_pipeline.version()` ein und zusätzlich in die eigene Liste von `canonical_worker.pipeline_version()`. Prompt-Version und Schema-Version bleiben v11/v9; die Quellfingerprints ändern sich zwangsläufig:

```text
v11:compact1:gate1:gpt-6.1-sol:3bc96d89c6534c1a:canonical1:294c117212937b9c
```

Aktiv ergänzt die Hybridkennung `:hotset1:age=30:rank=5`, `:delta2` oder beide in dieser Reihenfolge, vor `:canonical1:...`. Explizit übergebene Pipelinekennungen bekommen die Suffixe einmal. AUS-Kennung aus tatsächlicher Versionsfunktion, unabhängig aus den Quelllisten berechneter Kennung, `make_manifest.py --local-version` und Offlineprüfung stimmen überein. Das Manifest enthält SHA-256-Dateifingerprints, keine Pipelinekennung als zusätzlichen Map-Eintrag.

## Lokale Prüfungen

Alle Befehle aus `release2/`, ausschließlich Stdlib:

```sh
python3 -I -B make_manifest.py /private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/prod2/build-manifest.json --local-version
python3 -I -B run_tests.py release
python3 -I -B roundtrip.py
python3 -I -B offline_check.py --local
python3 -I -B run_tests.py before
python3 -I -B run_tests.py after
python3 -I -B run_tests.py compare
```

Im vorbereiteten Container: `PYTHONPATH=/app python3 -I -B /app/offline_check.py`. Der Prüfer setzt `/app` selbst in `sys.path`, da `-I` PYTHONPATH ignoriert. Kein Dockerlauf wurde ausgeführt. Der Prüfer kontrolliert Syntax/Importe, konkrete Kennung, AUS-Contractbytes, Diagnose, Delta, Filter, Kombination B+C, acht Manifestpayloads und Schalterkennungen. Er setzt die relevanten Flags für AUS-Prüfungen deterministisch auf 0; aktives Modellverhalten wird lokal synthetisch simuliert.

Belege: `release-tests.json`, `before-tests.json`, `after-tests.json`, `roundtrip-results.json`, `offline-results.txt`, `manifest-results.txt`. Release-Suite: **79/79**. Offline: **9/9**, Exit 0. Rundreise: **40/40** aus **41** Zeilen: **36** Endformen, **4** Nachforderungen, **1** Fehlerrecord. Zusätzlich **4/4** Live-Nachforderungen. Bestand vor/nach: jeweils **218/236**, **8** Failure- und **10** Error-Ereignisse; **0** unterschiedliche Testoutcomes. **19** Tests mit HTTP-/Serverbedarf wurden wegen des Auftrags identisch ausgeschlossen. Bestehende rote Tests bleiben rot; die gesamte Bestandssuite wird nicht als grün ausgegeben und liefert jeweils Exit 1. Bestehende Tests wurden unverändert ausgeführt, nicht repariert oder für grüne Ergebnisse umgeschrieben.

Wichtige Quellenlücke: prod2 enthält Module/Manifest/Compose/Dockerfile, aber keine `evaluation/`- oder `schema/`-Dateien. Lokale Prüfungen lesen fehlende Evaluationassets aus dem vorhandenen `working-memory/evaluation/`; Filter-Integrationstests nutzen die vorhandene v12-Referenz. Dies ist die dokumentierte plausible Annahme, keine bestätigte Bytegleichheit dieser Assets mit Produktion. Originalmodule für den AUS-Contract werden unmittelbar aus prod2 geladen. `generate_contract.py` regeneriert ausschließlich diese synthetische Referenz; anschließend Manifest erneuern. Im echten `/app` verwendet der Container-Prüfer ausschließlich Imageassets und scheitert bei abweichender erwarteter Kennung/Requeststruktur. Dieser tatsächliche Container-Nachweis bleibt offen. Fehlende Schemaassets und bereits vorhandene Bestandsabweichungen werden nicht durch Stubs als bestanden gewertet.

## Annahmen, Risiken und Rückweg

Die vier gespeicherten Nachforderungen projizieren `work_results=null` auf `{}`. Ausschließlich `archive=True` erhält dies für die exakt typstrenge 40/40-Rundreise mittels privatem Marker. Live-Decoder und Live-Schema erlauben diesen Marker nicht; der Produktionsvertrag bleibt null. Der zusätzliche Fehlerrecord ist kein vollständiger Aufruf und zählt nicht als bestandene Antwort.

Delta spart Ausgabe, garantiert jedoch weder Endform noch richtige Zuordnung. Eine Nachforderung ist keine Endform; die bisherige Öffnungsschleife bleibt entscheidend. Explizites `matter_id` verhindert die frühere stille Vererbung, belegt aber keine fachlich richtige Matter-Zuordnung. Historische Parent-Matter-Aliase und bestehende Originalprüfungen bleiben maßgeblich. Keine Modellqualität oder Serienzuverlässigkeit aus Rundreise/Unit-Tests ableiten.

Filterrestrisiko: Alter 31 Tage und Rang mindestens 5 ohne exakte ID-Erwähnung kann eine fachlich relevante Aufgabe ausschließen. Unbekannte Daten werden behalten. Das wöchentliche Sicherheitsnetz eines Vollabgleichs ist ausdrücklich **nicht Teil dieses Releases**.

Feature-Rückweg: beide Composewerte auf `"0"` setzen; dieses Overlay behält dabei Diagnose und neue Quellkennung. Vollständiger Code-Rückweg: zuvor verwendetes, als `OLD_TAG` übergebenes Basisimage wieder einsetzen und die beiden Featureflags ausschalten. Kein Datenrollback erforderlich, weil kein DB-/Schemaformat geändert wird; bereits erzeugte Ergebnisse werden dadurch nicht rückwirkend entfernt. Kein Wiederaufnahmeretry unbekannter bezahlter Calls gehört zum Paket. Build, Containerabnahme und Deployment sind nicht ausgeführt; deren Freigabe ist kein Teil der Offlineumsetzung.
