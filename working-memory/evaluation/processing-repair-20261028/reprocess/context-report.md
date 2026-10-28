# Source16: providerfreier Kontext-Capture

Auftrag: Nur den bislang nicht versandten `compact-0`-Prompt aus vorhandenen Antworten und Suchergebnissen rekonstruieren und messen. Keine Produktkorrektur, keine neue Modell- oder Tokenzählanfrage.

## Umsetzung

- `capture_context.py` exportiert den Stand 355 mit ausschließlich `REPEATABLE READ READ ONLY`-Transaktionen. Es führt keinen Such-RPC aus. Exakte PostgreSQL-/pgvector-Suchschlüssel binden gespeicherte Queryvektoren an vorhandene Suchergebnisse.
- Der neueste vorhandene Suchsnapshot ist lediglich ein Kandidat: der Replayprozess muss seine berechnete ID und vollständige geordnete Dokumentliste exakt bestätigen. Jeder fehlende Indexeintrag, Snapshot, Suchtreffer-Cache oder Modellbeleg stoppt.
- `capture_worker.py` besitzt keinen Provider. Ein Importfilter verbietet Providerbibliotheken; ein OS-Audithook verbietet Netzwerk und Unterprozesse. Schreibzugriffe sind auf seinen neuen privaten Diagnoseordner begrenzt; SQLiteänderungen bleiben in der eigenen historischen Kopie beziehungsweise im Speicher.
- Der normale Prozessor verwendet exakt gespeicherte Request-/Responsebelege. Der vorhandene, bereits geprüfte 48k-Extraktionsrequest wird über seinen ursprünglichen 24k-Requesthash gebunden. Unbekannte Anfragen sind nicht ausführbar.
- Der originale Kontextguard wird nicht abgeschaltet. Bei `compact-0` werden vor jedem Providerzugriff ausschließlich Maße und Hashes gespeichert; der Diagnoseprozess endet unmittelbar danach.

## Bisherige Belege

`python3 -m unittest discover -s meeting-os/working-memory/evaluation/processing-repair-20261028/reprocess -p test_capture.py`: 6 Tests, Exit 0. Syntaxprüfung aller drei Pythondateien: PASS.

Realer lesender Export: Revision 355; 123 vollständige Request-/Responsebelege mit korrekten Hashes; 244 vorhandene Suchergebnisse. Kandidat-Snapshot: `4673459d8130fdcf9ea40723d5427ff1de26cce45078f9159c508202abf5a92d`.

Der vollständige Capture wurde danach erfolgreich ausgeführt, Exit 0. Historische Generationen bis Stand 355 wurden über die installierten Verifikationsfunktionen rekonstruiert; alle 123 Modellantworten und 244 Suchantworten ausschließlich aus vorhandenen Daten wiederverwendet. Der errechnete Snapshot stimmt exakt mit dem gespeicherten Snapshot und seiner Dokumentliste überein. Kein Provideraufruf, keine Tokenzählanfrage und keine produktive Mutation.

Gemessenes `compact-0`: 958.227 Zeichen / 968.641 UTF-8-Bytes, Schema 30.139 Bytes, Ausgabelimit 59.736, Reserve 4.096; konservative Summe **1.062.612**, also **12.612** über 1.050.000. Unveränderter originaler Guard lehnt ab.

Prompt-SHA-256: `d4c9b6455bc0e221b1e87ab34fe2b713f121631cb236daa3db7c34641f039073`; Schema-SHA-256: `c5c64bd2012db4c6c937910cce3782f8e30e8457868e7cdf9595257f2fc71f07`.

68 Beobachtungen, 402 Arbeitskandidaten, 1.818 Treffer, 122 Suchthemen. Nachträglich aus dem bereits gespeicherten Prompt mit JSONDecoder.raw_decode gemessen, ohne weiteren Replay: Kandidatenkatalog 784.167 Bytes; 493 Originaleinheiten 88.915 Bytes; vorläufige Beobachtungen 76.809 Bytes. Entpackter Arbeitskatalog 254.591 Bytes, gepackte Archivnavigation 593.573 Bytes; diese Einzelmaße wegen gemeinsamer Textinternierung nicht addieren.

Katalog + Schema + Ausgabe + Reserve: **878.138**, unter 1.050.000. Gesamtkontext ohne Original: **973.697**, ebenfalls darunter. Damit überschreitet der Katalog allein die Grenze nicht. Über andere Quellen ohne deren Messung wird nichts behauptet.

Lokaler Metadatenbeleg: `../audit/private/source16-context/result.json`. Der vollständige Rohprompt bleibt ausschließlich serverprivat in `compact-prompt.json`. Die vor der Verarbeitung gespeicherte `historical.sqlite` ist durch `historical-receipt.json` an vollständigen Journaleingang, Quelldatum und Datei-SHA gebunden.

## Private Ausgaben

Container: `.../worker-reprocess22/9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7/attempts/e9a2a394-dab8-5585-b7ee-7570223ac4b8/context-capture/`.

Host: `/opt/dashboard-memory-canonical-draft/.local/recovery/reprocess22-20261028/context-capture/`. Rohprompts und Originale bleiben ausschließlich dort beziehungsweise im privaten Containerordner. Keine Hochladung, kein Commit.

## Historischer SQLite-Beleg

`historical.sqlite`: 69.398.528 Bytes, SHA-256 `8075f2e775e82719a8bb898230b3f2a2f9d25fd252aaf6c266ba6323dda6451d`. `historical-receipt.json.binding`: `6c8d2c22f7492158fac76abedf4238f8234c5960b39fd07a5167d1d7ded034b0`.

Die Bindung ist SHA256 der kanonischen JSON-Kodierung `[ursprüngliche SQL-Journalzeilen mit gejointen Quellversionen, Quelldatum]`, nicht der bereits normalisierten `generation_base`-Liste. Der normale Algorithmus `_logical_entries` und sämtliche Generationprüfungen wurden darauf ausgeführt. Ein unmittelbarer Gleichheitsnachweis zu anders geformten Gatewaytransportdaten oder ein daraus folgender Operator-Schnellpfad wird nicht behauptet.

## Abschluss dieses Diagnosepakets

Alle Kriterien des Capture-Auftrags erfüllt. Vier neue öffentliche Paketdateien (drei Pythondateien, dieser Bericht), private Metadatenausgabe; etwa zwölf gezielte Runtime-/Hilfsdateien und SQL-Verträge gelesen. Keine bestehende Paketdatei geändert, kein Commit, kein Deploy. Die produktive Fortsetzung und das Gesamtziel 22/22 bleiben beim Lead.
