# Begrenzter Strategiecheck zur Versionierung

Frischer unabhängiger Reviewer `/root/astra_version_plan_review`, angeforderte Laufzeit `gpt-6-astra/high`; das effektive Modell wurde vom Host nicht separat ausgewiesen. Read-only, keine Implementierung oder Delegation.

Auslöser: Zwei Versionierungsversuche erreichten vor jeder Git-Schreiboperation keinen vollständigen Nachweis, weil Git-/Dateireads zeitlich ausliefen. Index und Packed-Refs waren durch FileProvider als `dataless` markiert. Das belegt Dateiverfügbarkeit als Problem, keine Git-Korruption.

Urteil: **CONTINUE_BOUNDED mit Auflagen.** Zuerst gezielt vollständige Bytes und native Git-Lesbarkeit positiv nachweisen. Vor Ref-/Indexänderung den vollständigen Index sichern, HEAD binden und das genaue Own-Dateimanifest einfrieren. Fremde Stage-Einträge, Modi, Stufen und Indexflags erhalten. Commitinhalt bytegenau auf eigene Dateien und ausschließlich eigenen Statusheader auf ursprünglichem Indexblob begrenzen; Arbeitsbaum gesondert erhalten. Den früheren Fallback mit Refänderung vor Indexprüfung nicht unverändert verwenden.

Übernahme: Vollständiger Index am 12.10. um etwa 18:05 MESZ gelesen: 139.005 Bytes, SHA256 `e623092cd008bdb186179fc9c052201c95cd25bcf1120e587e17ffc12c451cbf`. Packed-Refs vollständig gelesen: 112 Bytes, SHA256 `80ca4ae9ecbc0327b8cc3432ff194e06432772a6f588dadfc0f7cc71a4ab8690`. Native `rev-parse HEAD`, `ls-files --stage` und `ls-files -v` erfolgreich. Keine erfundenen CLI-Downloadbefehle und keine FileProvider-Reparatur ausgeführt.

Folgepaket: höchstens ein bounded Commitversuch, Gesamtzeit 180 Sekunden und einzelne native Git-Aufrufe höchstens 20 Sekunden. Originalindex und Fremdflags vorher sichern; Kandidatenindex vor dem echten Refwrite prüfen. Echter Indexlock mit positiver Vergleichsprüfung schützt vor konkurrierenden Indexänderungen; Refänderung verwendet gebundenen alten HEAD. Kein Push. Bei fehlendem Positivnachweis bleibt die Mutation gesperrt.


Gezielter Folgecheck nach dem abgebrochenen 45-Sekunden-Read-only-Batchcheck unveränderter Fremdobjekte: **CONTINUE_BOUNDED** für native `mktree --missing` ausschließlich an den vier Parenttrees, wenn unveränderte Tupel vollständig aus nativen Reads des festen Ausgangscommits stammen. Alle neuen Einträge erhalten positive Typ-/Inhaltsprüfung, Own-Unterbäume bleiben bei normalem `mktree`, erzeugte Parenttrees müssen den erwarteten Tupeln exakt entsprechen. Dies belegt keine vollständige Wiederherstellbarkeit des gesamten fremden Gitbestands.

Weitere Auflage übernommen: Ein Refwrite mit Timeout kann trotzdem wirksam sein. Nach jedem Fehler ab begonnenem Refwrite werden tatsächlicher Ref und Index unabhängig von einem Boolean geprüft. Bei klarem neuen Ref plus unverändertem altem Index und positiv geprüftem Kandidatenlock wird der bekannte Commit konsistent abgeschlossen; bei unbekanntem Zustand bleiben Snapshot, Kandidat und Lock erhalten, kein blinder Folgeversuch. Der äußere Zeitwächter begrenzt auch Python-Dateireads; Zustandsklärung erhält eine eigene Reserve.

Die konkret benötigten Commit-/Parentobjekte wurden danach vollständig gelesen, und alle vier Parenttrees wurden erneut nativ an Commit `3376a277f8c567a28513bfe1c2ac59e39c07131a` gebunden. Root-Tree `3a010847fcb2a3bcda418d01239eca4e7eb4ddce`. Keine Ref- oder Indexmutation war dafür erforderlich.


Der eine freigegebene Parenttree-Versuch endete erneut vor aktuellem Ref-/Indexwrite mit Timeout bei `mktree --missing`. Danach positiv geprüft: ursprünglicher Ref, identischer Indexhash, kein Indexlock und kein vorbereiteter Refwrite. Die genaue interne Ursache des Timeouts bleibt eine Hypothese.

Astra genehmigte danach genau ein materiell anderes Folgepaket: nativer `fast-import` mit `--done`, ohne `--force`, festem ursprünglichem Parent und ausschließlich eigenen eingefrorenen `M`-Einträgen auf zuvor nachweislich freier eigener Kandidatenref. Vor Übernahme bleiben echte Commitblobbytes, vollständige eigene Pfad-/Modus-/OID-Liste, Parentbeziehung, unveränderte Parent-Tupel und fremde Indexstages/-flags positive Pflichten. Auch Importtimeout darf nicht als Abwesenheit der Kandidatenref behandelt werden. Eigene temporäre Ref wird ausschließlich mit passender OID entfernt. Keine Abschaltung von Gitprüfungen, keine manuelle Gitformat-Neuimplementierung und keine neue Nutzerentscheidung.


Der folgende Versuch erreichte den Import noch nicht: eine versehentlich erhaltene Own-`mktree`-Vorberechnung lief zeitlich aus. Diese unnötige Implementierungsabhängigkeit wurde entfernt. Astra bestätigte das minimale Folgepaket: erwartete Own-Blob-OIDs mit nativem `hash-object --stdin` ohne Objektwrite berechnen, ausschließlich eingefrorene Bytes als native `M 100644 inline`-Daten importieren und danach den vollständigen neuen Own-Unterbaum über native Pfad-/Modus-/OID- und tatsächliche Blobbyte-Prüfungen abnehmen. Kein `mktree`, `--missing`, `--literally` oder `--force` im ausgeführten Inlineweg. Eine eigenständige Packdatei oder Umgehung sämtlicher FileProviderzugriffe wird daraus nicht behauptet; Git kann vorhandene Objekte wiederverwenden. Budget und sämtliche Übernahmeguards bleiben erhalten.
