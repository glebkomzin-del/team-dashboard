# Roadmap
Der aktuelle Feature-Status wird ausschließlich von gov geschrieben.

| Kennung | Name | Status | Vision-Bezug |
| --- | --- | --- | --- |
| F-001 | Anmeldung und Navigation | fertig | Die Oberfläche bietet Anmeldung, Passwortwiederherstellung und Navigation durch die Arbeits- und Wissensbereiche. Quelle: src/pages/MemoryApp.tsx:57 |
| F-002 | Arbeitsübersicht und Aufgabenplanung | fertig | Die Oberfläche zeigt den Arbeitsstand und bietet Wochenplanung, Aufgabenbearbeitung und Statuswechsel. Quelle: src/pages/ProductivityPage.tsx:53 |
| F-003 | Teamansicht und Teamverwaltung | fertig | Die Oberfläche zeigt Aufgaben nach Teamumfang und bietet eine Verwaltung des direkten Teams. Quelle: src/pages/ProductivityPage.tsx:215 |
| F-004 | Wissen prüfen und korrigieren | fertig | Die Oberfläche zeigt Aussagen und erlaubt bei bearbeitbarem aktuellem Stand, Vorschläge zu übernehmen, zu verwerfen oder zu korrigieren. Quelle: src/pages/ProductivityPage.tsx:186 |
| F-005 | Originale aufnehmen und einsehen | fertig | Der Dienst kann Drive-Originale mit Version archivieren; die Oberfläche bietet Originale und gespeicherte Zusammenfassungen. Quelle: working-memory/drive_intake.py:52; src/pages/ArchivePage.tsx:29 |
| F-006 | Notizen fragen | fertig | Die Oberfläche bietet Gespräche über Notizen und ordnet Antworten ihrer Anfrage und ihrem Gespräch zu. Quelle: src/features/working-memory/NotesChat.tsx:121 |
| F-007 | Verarbeitung und Kostenbelege | fertig | Hinterlegte Quellaufträge werden verarbeitet; Providerabrufe werden mit Reservierung und Beleg geführt. Quelle: working-memory/canonical_worker.py:58 |
| F-008 | Originalquelltext löschen | fertig | Ein angemeldeter Eigentümer kann bei aktivierter Funktion die Löschung eines Originalquelltexts beantragen und den Status abfragen. Quelle: working-memory/server.py:219 |
| F-009 | Sicherung exportieren und prüfen | fertig | Der Sicherungslauf kann Journal, Archiv und zugehörige Aufträge an einer festen Grenze exportieren und prüfen. Quelle: working-memory/canonical_backup.py:232 |
| F-010 | Geräteeinstellungen und Betriebsübersicht | fertig | Die Oberfläche bietet Geräteeinstellungen und zeigt Informationen über Verarbeitung, Budget und Sicherungen. Quelle: src/pages/SettingsPage.tsx:68 |
| F-011 | Offener Punkt | Idee | Der Betriebsroutentest tests/planning-route.test.mjs:9 ist rot: Erwartung einer eigenen Betriebsroute widerspricht der Weiterleitung nach Einstellungen. Quelle: tests/planning-route.test.mjs:7; src/features/working-memory/planning.ts:28. |
| F-012 | Offener Punkt | Idee | Die vollständige Python-Suite ist vor dem Umbau rot: erster Lauf 521 Tests mit sieben Fehlern, Wiederholung 521 Tests mit sechs Fehlern; Archiv-HTTP und kompakte Pipeline-Integration sind betroffen. Ursache und Stabilität sind gesondert zu prüfen. Quelle: archiv/governance-alt/umbau-20261101/python-basis.txt. |
| F-013 | Offener Punkt | Idee | Eine aktuelle angemeldete Browserprüfung einschließlich Passwortwiederherstellung und Produktionsabnahme ist im Umbau nicht belegt. Quelle: archiv/governance-alt/umbau-20261101/vorpruefung.md. |
