# Abschlussbericht des Governance-Umbaus · 2026-11-01

## Vision
Dashboard Job soll Gleb Änderungen, eigene nächste Aufgaben und ausstehende Zusagen aus Meetingquellen sichtbar machen. Das vorhandene Dashboard verbindet Arbeitsplanung, Wissen und Originalbelege. Die vorbereitete Übergabe an eine Arbeits-KI bleibt eine gesonderte Ausbaurichtung mit offenen fachlichen Nachweisen.

## Features
- Anmeldung und Navigation
- Arbeitsübersicht und Aufgabenplanung
- Teamansicht und Teamverwaltung
- Wissen prüfen und korrigieren
- Originale aufnehmen und einsehen
- Notizen fragen
- Verarbeitung und Kostenbelege
- Originalquelltext löschen
- Sicherung exportieren und prüfen
- Geräteeinstellungen und Betriebsübersicht

Zehn Bestandsfeatures mit 40 quellengebundenen Kriterien, 20 einzeln übernommenen Entscheidungen und 23 fachlichen Chronikeinträgen sind zum Import vorbereitet. Die Bestandskennzeichnung ist keine neue reale Produktabnahme.

## Annahmen
- Annahme: Außenbestand wird vor migrate start mit expliziter Dateiliste und Prüfsummen kopiert und versioniert; die originale B3-Pauschalsicherung würde auch ignorierte private Dateien erfassen. Originale bleiben erhalten.
- Annahme: Code und lokale Tests allein belegen weder die aktuelle externe Bereitstellung noch eine angemeldete reale Browserabnahme.
- Annahme: Der am 01.11.2026 ausdrücklich ausgewählte vollständige aktuelle Produktstand ist die Ausgangsbasis; private lokale Daten und Geheimnis-Pfade werden ausgeschlossen.
- Annahme: Der separat bestätigte Build nutzt den lokalen pnpm-Cache ohne Netzwerk; der portable grüne Prüfbefehl umfasst 15 Node- und 55 Python-Tests ohne private Ergebnisdateien.
- Annahme: Der ursprüngliche Git-Index bleibt lokal unter .git/umbau-index-vor-snapshot erhalten; die autorisierte Bestandsaufnahme fasst vorgemerkte und nicht vorgemerkte Produktänderungen in einer Sicherung zusammen.
- Annahme: Die Erprobungsunterlage working-memory/tools/daily/README.md bleibt unveränderter Beleg; ihre Verweise auf bewusst ausgeschlossene lokale Ergebnisdateien sind keine neuen aktiven Wissensverweise.
- Annahme: Die Session übernimmt dort den gegen den Ausgangsstand gemessenen grünen Teil.
- Annahme: Ein belegter Codepfad und lokale Tests allein belegen weder eine aktuelle externe Bereitstellung noch eine angemeldete reale Browserabnahme.
- Annahme: Testbefehl und Klassifikation werden durch die Session bestimmt.
- Annahme: supabase/functions/ingest-transcript/index.ts enthält einen eingebetteten Zugangswert und bleibt unverändert ausschließlich lokal; beide Originalkopien bleiben erhalten, die Datei wird nicht versioniert oder gepusht.

## Archiv
Die Zuordnung umfasst 1962 Ausgangsdateien: 1342 Beleg, 451 Code, 27 Fachdoku, 77 Governance alt, 65 Wissen alt. Wissen alt und Governance alt werden ausschließlich unter archiv/governance-alt/<Originalpfad> archiviert; die Originalbytes bleiben nachweisbar. Die 298 Außenbestandskopien haben SHA-256-Nachweise; die geheimnishaltige alte Edge Function bleibt ausgeschlossen und unverändert lokal. Die äußeren Originale einschließlich vorhandener Altarchive, Geheimnisdateien, eigener lokaler Claude-/MCP-Einstellungen und wissensbezogener Symlinks bleiben unberührt. Der vollständige aktuelle Produktstand ist lokal mit Commit ecca3e5 und Tag sicherung-aktueller-produktstand-20261101 gesichert; der ursprüngliche Index liegt lokal in .git/umbau-index-vor-snapshot.

Andere Zweige und Arbeitskopien: Der bestehende Zweig codex/working-memory-redesign bleibt erhalten; die Ausgangsinventur weist nur die Hauptarbeitskopie meeting-os aus. main lag 104 Commits hinter dem Arbeitszweig, vor der zusätzlichen Produktsicherung. Die vom Kit erstellten Rückwege werden in zustand.json protokolliert. Graphify-Ausgaben sind unverversioniertes Streugut. Weitere 3591 lokale Pfade beziehungsweise Ergebnisartefakte sind im Ausschlussmanifest dokumentiert und bleiben erhalten; darunter .codex-deploy/, .design-workflow/, .interface-design/, working-memory/oauth-info/ und erzeugte Werkzeugergebnisse. Keine übrigen Arbeitskopien wurden verändert.

## Offen
- Aktueller Git-Zweig ist codex/working-memory-redesign; HEAD allein belegt keinen vollständigen versionierten Produktstand.
- Annahme: Code und lokale Tests allein belegen weder die aktuelle externe Bereitstellung noch eine angemeldete reale Browserabnahme.
- Das Zielbild nennt frühere, für die Optimierung relevante Gespräche außerhalb des damals zugänglichen Kontexts als fehlend.
- Das Zielbild nennt frühere, für die Optimierung relevante Gespräche außerhalb des damals zugänglichen Kontexts als fehlend. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:134
- Das vorgeschlagene Hot-Set und ein wöchentlicher Vollabgleich waren zum 13.10.2026 weder produktiv freigegeben noch in ihrer Wirksamkeit ausreichend nachgewiesen.
- Das vorgeschlagene Hot-Set und ein wöchentlicher Vollabgleich waren zum 13.10.2026 weder produktiv freigegeben noch in ihrer Wirksamkeit ausreichend nachgewiesen. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:91
- Den eingebetteten Zugangswert der alten Edge Function ingest-transcript gesondert bereinigen und seine Gültigkeit beziehungsweise erforderliche Rotation klären; keine Änderung externer Zugänge im Umbau. Quelle: _umbau/geheimnis-vorpruefung.json.
- Der Agent hat nach der Reparatur weder einen Abruf mit angemeldeter Nutzersitzung noch die Passwort-Zurücksetzung technisch verifiziert. Belegt sind die 22 Übernahmen, der tatsächlich aktuelle Backendcache und öffentliches Health HTTP200; die angemeldete Browserabnahme bleibt davon getrennt offen. Der frühere Nutzerscreenshot ist kein nachträglicher Agententest. Beleg: Reparaturkapsel README.md.
- Der Betriebsroutentest tests/planning-route.test.mjs:9 ist rot: Erwartung einer eigenen Betriebsroute widerspricht der Weiterleitung nach Einstellungen. Quelle: tests/planning-route.test.mjs:7; src/features/working-memory/planning.ts:28.
- Der Test für eine eigenständige Betriebsroute widerspricht dem aktuellen Routing: Der Test verbietet die Behandlung von #betrieb, der Code leitet diese Route nach Einstellungen/Verarbeitung um.
- Der lokale Indexaufbau wurde im Zielbild mit etwa 100 Sekunden beschrieben; ein persistenter Cache fehlte damals.
- Der lokale Indexaufbau wurde im Zielbild mit etwa 100 Sekunden beschrieben; ein persistenter Cache fehlte damals. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:149
- Der verpflichtende Hot-Set-Fall Alter 25 Tage/Rang 12 und die Prüfung an neuen Meetings waren zum 13.10.2026 offen.
- Der verpflichtende Hot-Set-Fall Alter 25 Tage/Rang 12 und die Prüfung an neuen Meetings waren zum 13.10.2026 offen. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:143
- Der ältere Strukturbericht bezeichnet supabase/ als Backend- und meeting-os/ als Frontend-Ort; ein Deploy über Vercel aus meeting-os/ wird dort beschrieben.
- Die Abnahme der Auftragspakete und die Unterscheidung unbelegter Annahmen von unbekannten Angaben waren offen.
- Die Abnahme der Auftragspakete und die Unterscheidung unbelegter Annahmen von unbekannten Angaben waren offen. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:47
- Die Dockerdatei erwartet Backenddateien relativ zum Buildkontext; ihre sichere Übernahme erfordert den vollständigen Satz und getrennte Erhaltung lokaler Daten.
- Die Dokumentation bezeichnet den Release-/Automatikstatus und zugehörige Unterlagen als Betriebsquelle; die Aktualität wurde nicht an der realen Anwendung geprüft.
- Die Fachvorgabe beschreibt einen unabhängigen Testsatz und Quellzuordnung als Qualitätsziele; die frühere Annahme perfekter Vergleichsfälle als Voraussetzung für den technischen Betrieb wurde später ausdrücklich geändert.
- Die Fachvorgabe beschreibt einen unabhängigen Testsatz und Quellzuordnung als Qualitätsziele; die frühere Annahme perfekter Vergleichsfälle als Voraussetzung für den technischen Betrieb wurde später ausdrücklich geändert. Quelle: working-memory/docs/NEXT-OPERATIONS.md:343
- Die HTTP-Tests zum kanonischen Archiv und zur Eigentümergrenze sind bei der aktuellen Suite teilweise rot; Ursache und Folgen sind gesondert zu prüfen.
- Die Kalibrierung des Relevanz-Gates anhand von Nutzerbewertungen war im Zielbild vom 13.10.2026 offen.
- Die Kalibrierung des Relevanz-Gates anhand von Nutzerbewertungen war im Zielbild vom 13.10.2026 offen. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:41
- Die genaue ursprüngliche Ursache der 22 alten ValueError-Streamabschlüsse ist weiterhin nicht belegt; die vorhandene Streamdiagnose belegt nur die sichere technische Korrektur, nicht die historische Ursache.
- Die hier inventarisierten Nutzerhandlungen sind aus dem Code abgeleitet; eine echte angemeldete Browser- oder Produktionsprüfung ist in dieser Inventur unbekannt.
- Die vollständige Python-Suite ist vor dem Umbau rot: erster Lauf 521 Tests mit sieben Fehlern, Wiederholung 521 Tests mit sechs Fehlern; Archiv-HTTP und kompakte Pipeline-Integration sind betroffen. Ursache und Stabilität sind gesondert zu prüfen. Quelle: _umbau/python-basis.txt.
- Ein Teil der Python-Regressionen benötigt absichtlich unversionierte private Ergebnisdateien, etwa evaluation/source-corrections.json; diese werden nicht in den Umbau importiert. Der portable grüne Prüfbefehl enthält nur ohne diese Daten ausführbare Tests. Quelle: working-memory/README.md:38.
- Ein Zusammenhang zwischen Sandbox und IO_ERROR bleibt eine Hypothese; die vorliegenden Abschlussbelege stellen ihn nicht als nachgewiesene Ursache fest.
- Ein vollständiger Wiederaufbau nach physischem Serververlust wurde im Restore-Runbook vom 04.10.2026 nicht als durchgeführt ausgewiesen.
- Ein vollständiger Wiederaufbau nach physischem Serververlust wurde im Restore-Runbook vom 04.10.2026 nicht als durchgeführt ausgewiesen. Quelle: working-memory/docs/RESTORE-RUNBOOK.md:209
- Ein wiederholter identischer Frontend-Build endete nach 120 Sekunden ohne Abschluss. Der erste isolierte TypeScript-/Vite-Build ist mit 103 identischen Quellprüfsummen grün belegt; die Ursache der instabilen lokalen Laufzeit ist offen. Quelle: _umbau/isolierter-build.json; _umbau/build-quellen.json.
- Eine aktuelle angemeldete Browserprüfung einschließlich Passwortwiederherstellung und Produktionsabnahme ist im Umbau nicht belegt. Quelle: _umbau/vorpruefung.md.
- Für das Memory waren eine fachliche Goldfragen-Abnahme und der Nachweis des Abrufs aus VS Code offen.
- Für das Memory waren eine fachliche Goldfragen-Abnahme und der Nachweis des Abrufs aus VS Code offen. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:44
- Historisch offen zum 2026-10-29T00:27:44: Ein Zusammenhang zwischen Sandbox und IO_ERROR bleibt eine Hypothese; die vorliegenden Abschlussbelege stellen ihn nicht als nachgewiesene Ursache fest. Quelle: wissen/verarbeitung/H-20261029-002744-2619-sandbox-io-error.md:13
- Historisch offen zum 2026-10-29T00:31:33: Der Agent hat nach der Reparatur weder einen Abruf mit angemeldeter Nutzersitzung noch die Passwort-Zurücksetzung technisch verifiziert. Belegt sind die 22 Übernahmen, der tatsächlich aktuelle Backendcache und öffentliches Health HTTP200; die angemeldete Browserabnahme bleibt davon getrennt offen. Der frühere Nutzerscreenshot ist kein nachträglicher Agententest. Beleg: Reparaturkapsel README.md. Quelle: wissen/verarbeitung/F-20261029-003133-5c3b-browser-und-passwortabnahme.md:13
- Historisch offen zum 2026-10-29T00:31:33: Welche konkreten Ursachen die 22 ursprünglichen ValueError-Streamabschlüsse hatten, bleibt ungeklärt: ihre eigentlichen Streamfehler wurden damals nicht ausreichend gespeichert. Der später bei Quelle16 nachgewiesene Tokenlimit-Abschluss belegt nicht die Ursachen aller alten Fehler. Die erfolgreiche erneute Verarbeitung ersetzt diesen historischen Ursachenbeleg nicht. Beleg: Reparaturkapsel README.md. Quelle: wissen/verarbeitung/F-20261029-003133-2c14-historische-streamursachen-unbekannt.md:13
- Lieferweg zur Arbeit und Zulässigkeit des Datenflusses Arbeitsmeetings → privates System → Arbeits-KI waren ungeklärt.
- Lieferweg zur Arbeit und Zulässigkeit des Datenflusses Arbeitsmeetings → privates System → Arbeits-KI waren ungeklärt. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:129
- Ob bestehende Supabase-Deploy- und Restoreabläufe spezifisch den äußeren supabase/-Pfad benötigen und ob eine zusätzliche Kopie in meeting-os/ als Quelle gewählt würde, ist nicht belegt.
- Ob das Dashboard im angemeldeten Browser erfolgreich lädt, bleibt unbekannt; es ist kein angemeldeter Browserabruf belegt und Zugangsdaten wurden dort nicht eingegeben.
- Welche konkreten Ursachen die 22 ursprünglichen ValueError-Streamabschlüsse hatten, bleibt ungeklärt: ihre eigentlichen Streamfehler wurden damals nicht ausreichend gespeichert. Der später bei Quelle16 nachgewiesene Tokenlimit-Abschluss belegt nicht die Ursachen aller alten Fehler. Die erfolgreiche erneute Verarbeitung ersetzt diesen historischen Ursachenbeleg nicht. Beleg: Reparaturkapsel README.md.
- Wiederherstellungswerkzeuge bestimmen den äußeren supabase/-Pfad über zwei Elternverzeichnisse; die unveränderten Originalpfade bleiben bestehen. Die Kopie im Repository ersetzt keinen geprüften Deploy-/Restoreweg. Quelle: working-memory/restore_schema.py:23.
- Zustellung von Erinnerungen und deren Compliance waren offen.
- Zustellung von Erinnerungen und deren Compliance waren offen. Quelle: working-memory/docs/ZIELBILD-PHASE1.md:43
- Zwei kompakte Pipeline-Integrationstests endeten in der aktuellen Suite mit Fehlern; Ursache und Folgen sind gesondert zu prüfen.

Die umfassende Testsuite ist bereits vor dem Umbau rot. Als unveränderte grüne Vergleichsbasis dienen 15 Node- und 55 portable Python-Tests; private Originale und Ergebnisfixtures werden dafür nicht veröffentlicht. Der separat bestätigte isolierte Frontend-Build ist kein Produktions- oder Browsertest. Externe Dienste, laufende Container, Datenbanken und Deployment-Pfade wurden im Umbau nicht verändert.

Die Vision wird ausschließlich beim erfolgreichen migrate finish ohne Nutzerbestätigung mit Quelle „Umbau“ auf tragfähig gesetzt. Das ist keine neue Produktabnahme. Korrekturen erfolgen danach regulär über /vision.
