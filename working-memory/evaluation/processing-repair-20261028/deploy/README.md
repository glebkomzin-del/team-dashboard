# Geprüfte Übernahme: bestehender Dienst und zwei Quellen

Auftrag vom Lead: die ausdrücklich freigegebene Übernahme vorbereiten; produktive Ausführung ausschließlich durch den Lead. Keine neuen KI-Aufrufe, keine direkten Änderungen an Aufträgen oder Journal, keine fremden Änderungen überschreiben. Ponytail full: bestehender Compose-/Docker-/Postgres-Weg und Python-Standardbibliothek, keine neue Abhängigkeit.

## Dateien und Prüfungen

- `run.py`: sendet ausschließlich den geprüften Kandidaten und versiegelte frische Artefakte nach Stand 338 über SSH-Standardeingabe. Produktive Phasen benötigen zusätzlich `--execute`.
- `remote.py`: eng begrenzte Phasen `deploy`, `adopt`, `resume`, `verify`; Zustand und private Fehlerprotokolle bleiben im vorhandenen serverseitigen Sicherungsbereich.
- `test_deploy.py`: Offline-Prüfungen gegen Shell-/SQL-Sonderzeichen, Kandidat-/Revisionsdrift und ungehaltene Verarbeitung.

Ausgeführt: `python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/deploy -p 'test_*.py'`.
Rein lesend ausgeführt: `python3 meeting-os/working-memory/evaluation/processing-repair-20261028/deploy/run.py preflight`, Exit 0. Bestätigt: Stand 338, vom Lead gehaltene Verarbeitung, alte Codehashes und unveränderte überprüfte SQL-Funktionen.

Nach dem ersten echten Startversuch korrigiert: Der gehaltene Dienst muss zusätzlich `MEMORY_ORIGINAL_DELETION_ENABLED=0` setzen, weil dessen tatsächliche Startprüfung die Original-Löschfunktion in einem schreibgeschützten Dienst ablehnt. Dieser Konflikt ist mit dem unveränderten Startprüfungs-AST rot und mit dem fünften Halteflag grün reproduziert. Der Lead hat den vorübergehenden Neustartkonflikt bereits behoben; bis dahin wurde weder ein neues Image gebaut noch ein Ergebnis übernommen.

Wiederholungen erhalten zwingend die beim ersten Versuch gespeicherten ursprünglichen Flags. Bei älteren vierteiligen Protokollen wird ausschließlich das fehlende fünfte Flag aus der ursprünglichen Compose-Konfiguration ergänzt; aktuelle Haltewerte überschreiben nie die Originalwerte. Insgesamt sieben Offline-Tests bestanden, Exit 0, einschließlich dieser beiden Regressionen.

## Konkrete Ausführung durch den Lead

Vom Projektordner, nacheinander und nur bei Exit 0:

```text
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/deploy/run.py deploy --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/deploy/run.py adopt --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/deploy/run.py resume --execute
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/deploy/run.py verify --execute
```

`deploy` verlangt den bereits vom Lead vollständig zurückgelesenen Datenbankdump mit SHA-256 `19662added3659ea456c68084ef76f2813998f98075d87ec849740244acd2178`. Es sichert Compose und betroffene Hostdateien, prüft das alte Image, hält den Dienst zusätzlich schreibgeschützt und ohne Worker/Intake/Fragen, baut vom vorhandenen Image ein neues mit genau zwei geänderten Pythondateien und abgeleiteten Versionsmetadaten. Am bisherigen Standardvertrag wird ausschließlich `pipeline_version` aktualisiert; alle anderen Felder bleiben gleich. Manifest und vollständiger bestehender Offline-Containercheck werden geprüft. Anschließend wird die neue Pipelinekennung unter Revisions-/Konfigurationsvergleich gebunden; Verarbeitung bleibt gehalten.

`adopt` verwendet zwei jeweils atomare, serialisierbare Transaktionen: Notiz schreiben, geprüften Entwurf anlegen, Entscheidung mit Revision/Vorschauhash/zuletzt geändertem Auftrag annehmen. Schritt 1 erwartet 338→339, Schritt 2 erwartet 339→340. Es nutzt ausschließlich `public.wm_archive_note_put`, `public.wm_generation_stage`, `public.wm_generation_decide`. SQL-Texte/Quellmaterial erscheinen nicht in der normalen Ausgabe. Neue Modell-/Fragenaufrufeinträge werden nach jedem Schritt ausgeschlossen.

`resume` setzt ausschließlich nach beiden bestätigten Übernahmen die ursprünglichen Compose-Flags wieder ein und stellt die ursprüngliche Aktivierung mit neuer Pipelinekennung her. Die ursprüngliche Kosten-/Datums-/Budgetkonfiguration muss unverändert sein. `verify` liest Codehashes, Pipeline, Aufträge und Aufrufzähler zurück. Die abschließende reale Browserabnahme bleibt Aufgabe des Leads.

## Grenzen und Fehlerbehandlung

Es wurden durch den Builder keine produktiven Phasen ausgeführt. Ein Fehler lässt die bereits genehmigte Verarbeitungspause bestehen und meldet einen generischen Fehler; private Diagnose liegt unter `deploy/private/` sowie serverseitig `.../processing-repair-20261028-lead/deployment/`. Nicht blind erneut ausführen: Nach einem unterbrochenen Commit kann ein Auftrag bereits übernommen sein, während die lokale Phasenmarkierung fehlt. Dann zuerst Revision/Entscheidungskennung prüfen; keine neue Entscheidung erzeugen und keine Aufträge per SQL zurücksetzen.

Vor Datenübernahme ist der alte Dienststand aus Image-/Compose-/Dateisicherung verfügbar. Nach Datenübernahme ist das alte Image allein kein sicherer Rückweg. Die bereits vorbereitete Gegengeneration betrifft logische Inhalte, nicht alle Auftrags-/Auditmetadaten oder separat gespeicherte Archivnotizen. Keine automatische Datenrücknahme und kein Löschen.

Gelesen: vorhandene Reparatur-/Replayberichte, gezielte Runtime-/Deploydateien und rein lesende Live-Metadaten. Geschrieben: ausschließlich dieses Verzeichnis. Keine Secrets ausgegeben, keine Anbieteranfrage, kein Commit.
