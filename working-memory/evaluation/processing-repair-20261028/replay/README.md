# Zwei gespeicherte Prüfablehnungen: Offline-Reproduktion und Kandidat

## Ergebnis

Die beiden echten Ablehnungen sind ohne neue KI-Aufrufe reproduziert:

| Quelle | historischer Stand | gespeicherte Beobachtungen | letzte Prüfung |
|---|---:|---:|---|
| GCO JF `7b4057c2` | 313 | 31 | `memory.apply`: Work update belongs to a different matter |
| Reporting `a77d73b4` | 314 | 36 | dieselbe Prüfung |

Der vollständige Bestandskatalog wurde aus den gespeicherten kompakt gepackten Anfragen rekonstruiert. Alle
Aufgabenaliase sind eindeutig zum historischen Bestand zugeordnet. Die daraus rekonstruierten
Abschlussprüfungskandidaten stimmen exakt mit den unveränderlichen gespeicherten Anfragen überein. Request- und
Response-Hashes aller 123 gespeicherten Aufrufe wurden geprüft. Die vollständigen Ergebnisse bestehen die
Abschlussprüfung und die zeitliche Schutzprüfung; erst die Übernahme scheitert.

Die KI hatte jeweils eine widersprüchliche Referenz gewählt:

- GCO: `source_index=1`, Aufgabe `W366` gehört zu `M53`, gewählt wurde `M368`.
- Reporting: `source_index=13`, Aufgabe `W229` gehört zu `M205`, gewählt wurde `M31`.

Das ist bereits in der ursprünglichen gespeicherten KI-Antwort enthalten, kein nachgewiesener Decoderfehler. Die
Abschlussprüfung hat beide Zuordnungen ausdrücklich mit `unsupported` abgelehnt. Beide Beobachtungen sind prüfpflichtig,
enthalten eine konkrete Unsicherheit und haben Änderungsbelegstufe 0. Sie dürfen keine Aufgabe ändern.

## Konkreter Implementierungsfehler und minimale Korrektur

Der vorhandene Vertrag in `memory.apply` lautet: unklare/abgelehnte Änderungen bleiben Wissen und ändern keine Aufgabe.
Die bestehende Regression `test_review_flag_blocks_closure_even_with_positive_gate` sichert diesen Schutz ab. Die
Bereichsprüfung behandelt eine bereits gesperrte Änderung dennoch vorher wie eine ausführbare Aufgabenänderung und lehnt
dadurch die ganze Quelle ab.

`overlay/memory.py` korrigiert nur diese Reihenfolgeauswirkung: Bei einer bereits blockierten Aktion und einer
bekannten, ausdrücklich gewählten anderen Bereichs-ID bleibt die Beobachtung als Wissen in ihrem ursprünglichen Bereich
erhalten. Die referenzierte Aufgabe wird weder verändert noch als richtiger Bezug bestätigt. Wirksame Änderungen in
fremden Bereichen werden weiterhin abgelehnt. Unbekannte Aufgaben, unbekannte Bereiche, Originalbelege, bedingte
Auflösung und alle bisherigen Schutzprüfungen bleiben erhalten. Fehlende Bereichs-ID und identische Bereiche behalten
das bisherige Verhalten, damit akzeptierte historische Prüfsummen nicht driften.

Ponytail full: vorhandene Python-/SQLite-Funktionen und gespeicherte Originalantworten verwendet; keine Abhängigkeit und
kein neuer Modellaufruf. Kein Produktcode außerhalb dieses Pakets geändert. Die Testdaten liegen ausschließlich in
`private/` (0700, Git-ausgeschlossen); private Originale/Prompts stehen nicht in diesem Bericht.

## Ausgeführte Prüfungen

Vom übergeordneten Projektordner:

```text
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/replay/replay.py
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/replay/validate_saved.py
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/replay/validate_saved.py --candidate
python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/replay -p test_scope.py
python3 meeting-os/working-memory/evaluation/processing-repair-20261028/replay/check_memory.py
```

- Historische Projektionen 313 und 314: beide PASS, alle akzeptierten Ergebnisprüfsummen geprüft.
- Baseline: beide echten Gesamtvorschläge scheitern am belegten Bereichsfehler; der Reproduktionstest erwartet diesen Fehler und endet mit Exit 0.
- Kandidat: beide Gesamtvorschläge bestehen (31 und 36 Beobachtungen); pro abgelehntem Kandidaten 0 Aufgabenereignisse, Wissensbereich bleibt erhalten; Exit 0.
- Sechs gezielte Regressionen: PASS. Darunter wirksame fremde Bereichsänderung weiterhin abgelehnt, wirksame gleiche Bereichsänderung weiterhin ausgeführt, unbekannte Aufgabe und erfundener Beleg weiterhin abgelehnt, blockierter Bezug ohne Bereichs-ID historisch unverändert.
- 17 bestehende `test_memory.py`-Tests: PASS; `check_memory.py` prüft vor Start ausdrücklich, dass `overlay/memory.py` geladen ist.
- Reproduktion/Übernahmevorschau verbieten Netzwerk und Unterprozesse per Python-Auditfunktion, nachdem der rein lesende Datenexport abgeschlossen ist.

Belege: `results.json`, `saved-results.json`, `candidate-results.json`; aktuelle Bestandsprüfung/Übernahmevorschau
separat in `current-preview-results.json`.

## Grenzen

Keine produktive Datei/Datenbank geändert, keine neue KI-Anfrage, keine Quelle neu gestartet, kein Commit. Die 22
Empfangsfehler werden damit nicht wiederhergestellt. Die zwei Quellen sind bis zur ausdrücklich freigegebenen
produktiven Übernahme weiterhin unvollständig. Spätere Quellen und menschliche Änderungen dürfen nur über die vorhandene
geprüfte chronologische Wiederherstellung erhalten werden; kein blindes Zurücksetzen der alten Aufträge.

## Aktueller Bestand und ausschließlich lokale Übernahmevorschau

`current_preview.py`: Journalstand 338 mit dem finalen Kandidaten vollständig rekonstruiert; sämtliche historischen
Akzeptanzprüfsummen PASS. Kandidaten-SHA-256: `e822eb293d6d87cc74f0df5671e4d656c060c81ccce6502860b7c142803c2316`. Die
lokale Generation erhält 324 bestehende Quellen und alle 11 menschlichen Entscheidungen und fügt genau die zwei
gespeicherten Ergebnisse hinzu. `compile_generation` und anschließendes `verify_generation` PASS. Vorschau-SHA-256
`e08daf7d17803966307ba67a304a35440b7cc2e2bda2370c81e05ebc99a7605b`. 531.663 UTF-8-Bytes liegen unter der vorhandenen
Grenze von 3.700.000 Bytes. Privater Entwurf: `private/generation-preview.json`; technischer Beleg:
`current-preview-results.json`. Kein produktiver Entwurf wurde angelegt.

## Zwei getrennte geprüfte Übernahmen samt Zusammenfassungen und Rückweg

`sequential_preview.py` ist mit Exit 0 abgeschlossen. Alle folgenden Vorschauen wurden vollständig lokal kompiliert und
durch `verify_generation` erneut geprüft. Sie verwenden den bereits vollständig geprüften Ausgangsstand 338 und den oben
benannten unveränderten Kandidatenhash.

| Schritt | gebundener Auftrag | erwarteter Stand | Folgestand | geprüfter Vorschauhash |
|---|---|---:|---:|---|
| 1 | GCO `7b4057c2` | 338 | 339 | `4c9bd49460fa0bd814052a1ffd82efe537a4a74c34c18214ae208bee20fe57bc` |
| 2 | Reporting `a77d73b4` | 339 | 340 | `3cc0076570e4e0dfd2992cf50ace305960fd82cd52c5ede3f0dd099944eaee60` |

Jeder Schritt bindet genau seinen einen Auftrag und fügt genau seine eine Quelle hinzu. Alle 325 vorherigen Quellen
sowie Inhalt/Reihenfolge aller elf menschlichen Entscheidungen bleiben erhalten. Die vorhandene
`wm_generation_decide`-Schnittstelle schließt genau einen gebundenen Auftrag ab; deshalb ist die vorherige kombinierte
Vorschau **nicht** der Übernahmeablauf.

**Zusammenfassungen:** Rein lesende Produktionsabfrage ergab null vorhandene Archivnotizen für diese zwei Dokumente. Aus
den gespeicherten Extraktionsantworten wurden sechs beziehungsweise vier Absätze rekonstruiert und mit
`future_summary.from_response` gegen Originalpassagen sowie `verify_note` gegen Dokument-/Inhalts-/Notizhash geprüft.
Beide Notizen sind im jeweiligen neuen Quellenpaket als `archive_note` enthalten. Es erfolgte kein Notizschreibaufruf.

- GCO Notiz-ID: `693c8e3cf067f1965c6565e2437a6d3e5133e9f793cf15154dffe4f04b1e668e`.
- Reporting Notiz-ID: `28354e64592f5bff7ea80d56ff1feee0eff86ee2afc63fbe52d8dc8002729098`.

Frische, versiegelte Artefakte: `private/fresh338/` mit `manifest.json`; ältere Nachweise bleiben in `private/frozen337/`. Privat vorbereitet: `private/sequential-7b4057c2.json` und `private/sequential-a77d73b4.json`, jeweils mit Notizenhülle,
konkreter `stage_request`, konkreter `decide_request`, erwarteter letzter Jobänderung und vollständig geprüftem
Vorschaupaket. Stabile Review-/Entscheidungskennungen erlauben ausschließlich identische Wiederholung. Beleg:
`sequential-preview-results.json`.

**Späterer vorhandener Übernahmeweg, nur nach ausdrücklicher Freigabe:**

1. Ausschließlich den geprüften `memory.py`-Unterschied in den bestehenden Dienst übernehmen. Alten Imageverweis, Codehash, Konfiguration und vollständige Sicherung vorher erhalten/prüfen. Keine Modell-/Kosten-/Wiederholungsänderung. Weil die vorhandene Pipelinekennung Codehashes einschließt, muss die vorhandene regelkonforme Konfiguration zum neuen Dienststand passen; sonst kann der Prozessstart blockieren. Kein neuer Infrastrukturweg und keine blinde Änderung.
2. Aktuelle Revision, beide Auftragsstände, Originalhashes und Kandidatenhash erneut lesen. Jede Abweichung von den vorbereiteten Grenzen stoppt die Übernahme; dann eine neue lokale Vorschau erzeugen und prüfen.
3. Die GCO-Notiz mit dem bestehenden idempotenten `archive_note_put` schreiben, danach vorhandenes `generation_service.stage` → `inspect` → `decide` mit den exakt vorbereiteten Daten und GCO als `job_id`. Ergebnis und Jobzustand zurücklesen. Erst bei bestätigtem Stand 339 entsprechend Reporting ausführen.
4. Notiz und Quellenpaket müssen zusammenpassen; die Notiz-ID entsteht aus Originaldokument, Ursprungsauftrag und Inhaltshash. Bereits identisch gespeicherte Notizen liefern `repeated=true`; veränderte Inhalte unter derselben Identität oder gelöschte Originale werden abgelehnt.
5. Nach jedem Schritt mindestens erwartete Revision, Reviewhash, gebundenen Jobzustand, persönliche Entscheidungen und Quellen zurücklesen. Abschließend reale Dashboardanzeige und beide aktiven Quellzusammenfassungen prüfen. Keine KI-Aufrufe notwendig. Keine direkten Updates an `wm_jobs`/`wm_journal`.

Die vorhandenen **Live**-Definitionen von `wm_generation_stage`, `wm_generation_decide` und `wm_archive_note_put` wurden
rein lesend exportiert. Bestätigt sind Revisions-/Vorschauhash-/letzte-Jobänderungsprüfung, unveränderliche
Originalprüfung, Notizhashprüfung und identische idempotente Wiederholung. Beleg: `live-adoption-routines-results.json`;
keine Funktion wurde verändert.

**Geprüfter Rückweg:** Aus der lokal angenommenen zweiten Generation wurde eine Gegengeneration zum Entfernen
ausschließlich dieser zwei neu übernommenen Quellen kompiliert und erneut verifiziert. Das Ergebnis entspricht exakt
allen ursprünglichen logischen Einträgen von Stand 338; alle elf persönlichen Entscheidungen bleiben erhalten.
Rückweg-Vorschauhash: `67e87246aa80766ee1d931c35f55ba4f6c89f05baf0bdf643d78b78ed7f3f582`. Privat:
`private/rollback-generation.json`. Dieser Weg ist nur gegen den unveränderten simulierten Folgestand 340 vorbereitet;
spätere Quellen/Entscheidungen erfordern zwingend eine neue geprüfte Vorschau. Journal und Entscheidungsaudit werden
nicht gelöscht; eine Gegengeneration fügt einen nachvollziehbaren neuen Stand hinzu.

**Vor** Datenübernahme kann der alte Dienststand wieder verwendet werden. **Nach** Datenübernahme muss zuerst die
geprüfte Gegengeneration erfolgen; das alte Image allein würde die neuen Cross-Bereichs-Wissensbeobachtungen erneut
ablehnen. Kein blindes Einspielen einer alten Sicherung. Neu geschriebene Archivnotizen bleiben als unveränderliche
Ableitungen erhalten; ihre Aktivierung folgt dem Quellenpaket.

Alle produktiven Schreibwege bleiben unbenutzt und benötigen weiterhin Glebs explizite Freigabe. Die hier belegte
Leistung ist die lokale Vorbereitung und Prüfung, nicht die tatsächliche erfolgreiche Übernahme oder Browserabnahme.

Gelesen: Laufzeitsnapshot der Pythonmodule/Schema-/Promptdateien, gezielt ca. 12 Quelldateien, gespeicherte
Requests/Responses und historische Journalquellen. Geschrieben: zwei Collector-Skripte, drei Replay-/Prüfskripte, sechs
Regressionen, Kandidat `memory.py`, technische Ergebnisdateien und dieser Bericht.
