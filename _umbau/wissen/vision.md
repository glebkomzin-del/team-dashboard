# Vision · Dashboard Job

## Zweck und Zielgruppe
Das Dashboard soll Gleb Änderungen, eigene nächste Aufgaben und ausstehende Zusagen aus Meetings als Quellen sichtbar machen. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:3
Das Zielbild beschreibt die vorbereitete Übergabe relevanter Arbeit samt Kontext an Glebs Arbeits-KI als zusätzliche Ausbaurichtung. Quelle: archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:4

## Produktgrenzen
Nur ausdrückliche Zusagen oder angenommene Bitten mit identifizierbaren Verantwortlichen und tragfähigem Originalbeleg begründen neue Arbeit; Wiederholungen aktualisieren vorhandene Verpflichtungen. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:15
Statusänderungen brauchen einen sicheren Bezug; Personen und Fristen dürfen weder aus bloßer Teilnahme noch aus ungenauen Formulierungen geraten werden. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:17
Originalquellen und Versionen, belegte Beobachtungen, Vorgänge, Verpflichtungen und Änderungsereignisse bleiben unterscheidbar; ähnliche Namen allein begründen keine Zusammenführung. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:7
Nur handlungsrelevante Unsicherheit mit Folgen für eine aktuelle Verpflichtung soll eine knappe Nutzerentscheidung verlangen; technische Fehler gehören zum Betriebsstatus. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:19
Originale vollständig erfassen; spätere Quellen im Ereigniszeitpunkt-Kontext ausschließen und bei historischen Wissensstand-Replays zusätzlich die Kenntnisnahme begrenzen. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:23
IDs, Originalbelege, Datumsbezug und zulässige Änderungen sind unabhängig vom Modell zu validieren; strukturierte Ausgabe allein beweist keine fachliche Richtigkeit. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:26
Daten-, Original-, Hash-, Schema-, Berechtigungs-, Humanentscheidungs- und Kostenintegrität bleiben verpflichtend; fehlerhafte Quellen müssen mit Grund und Wiederaufnahmeweg sichtbar bleiben. Quelle: archiv/governance-alt/working-memory/docs/NEXT-OPERATIONS.md:345
Fachliche Dashboardprüfungen bleiben vom technischen Betrieb getrennt. Quelle: archiv/governance-alt/working-memory/docs/NEXT-OPERATIONS.md:345
Nur die passende Eigentümerkennung darf eine persönliche Arbeitsgedächtnisprojektion öffnen; die HTTP-Annahme von Originalen ist der Dienstrolle vorbehalten. Quelle: working-memory/journal_service.py:108; working-memory/server.py:372
Historische, gespeicherte und noch nicht bestätigte Ansichtsstände sind schreibgeschützt; bei fehlgeschlagener Aktualisierung bleibt Bearbeiten gesperrt. Quelle: src/pages/ProductivityPage.tsx:212; src/features/working-memory/useReviewSnapshot.ts:34
Bei Zugangssperre mit HTTP 401 oder 403 wird der gespeicherte Ansichtsstand gelöscht; ein neues Passwort muss in der Oberfläche mindestens acht Zeichen lang sein. Quelle: src/features/working-memory/useReviewSnapshot.ts:24; src/features/auth/AuthForms.tsx:49
Planung einer aus Meetings stammenden Arbeit ändert nicht die ursprüngliche Meetingzusage; persönliche Entscheidungskennungen dürfen mit verändertem Inhalt oder veralteter Revision nicht wiederverwendet werden. Quelle: src/features/working-memory/PlannerEditor.tsx:31; working-memory/journal_service.py:202
Nutzerbestätigte Quellenkorrekturen überstimmen Modellurteile; die Vorbereitung einer Originalkorrektur verändert den Arbeitsstand erst nach ausdrücklicher Übernahme und sendet keine KI-Anfrage. Quelle: archiv/governance-alt/working-memory/README.md:23; src/features/working-memory/SourceEditor.tsx:114
Unvollständige oder übergroße Drive-Originale werden abgelehnt und nicht gekürzt; unerwartete Quellidentität oder konkurrierende abweichende Archivdaten führen zu einem Konflikt. Quelle: working-memory/drive_intake.py:12; working-memory/drive_intake.py:52
Ungeklärte Transport- oder Providerergebnisse dürfen keinen automatischen erneuten Versand und keine automatische Doppelbezahlung auslösen. Quelle: working-memory/durable_calls.py:71; archiv/governance-alt/working-memory/docs/NEXT-OPERATIONS.md:345
Bei unklaren Kosten bleibt die volle Reservierung angerechnet; die Kostenübersicht ist keine Anbieterrechnung. Quelle: src/features/working-memory/ProcessingPanel.tsx:72
Frühere Gesprächsbeiträge sind Referenzkontext und keine Antwortbelege; belegte Antworten benötigen bekannte Quellenverweise. Quelle: working-memory/memory_chat.py:61; working-memory/qa_service.py:98
Ein Restore beginnt auf einem isolierten leeren Ziel und attestiert die aktuelle externe Löschbarriere; ohne nachweislich aktuellen externen Ledger erfolgt kein Datenrestore. Quelle: archiv/governance-alt/working-memory/docs/RESTORE-RUNBOOK.md:201
Beim Dashboard-Restore dürfen andere Anwendungen und die gemeinsame produktive n8n-Datenbank nicht pauschal überschrieben oder neu gestartet werden. Quelle: archiv/governance-alt/working-memory/docs/RESTORE-RUNBOOK.md:324
Die zusätzliche Arbeits-KI-Ausrichtung fordert keine eigene neue Dashboard-UI und nennt VS Code, E-Mail und Power BI als mögliche Kanäle; der dokumentierte Phase-1-Rahmen ist als historische Entscheidung erfasst. Quelle: archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:27
Qualität darf bei Kostensenkung nicht sinken; jede Aussage in einem künftigen Auftragspaket muss belegt oder als unbekannt markiert sein, und Ergebnisse einschließlich Reviews, E-Mail-Entwürfen und Erinnerungen verlangen Nutzerabnahme. Quelle: archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:32; archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:20

## Recherche und Nachweisgrenzen
Die Bestandsbeschreibung der Funktionen stützt sich auf die gezielten Frontend- und Backend-Inventare und ihre Codequellen. Quelle: src/pages/MemoryApp.tsx:57; working-memory/server.py:190
Annahme: Ein belegter Codepfad und lokale Tests allein belegen weder eine aktuelle externe Bereitstellung noch eine angemeldete reale Browserabnahme.
Die vorgefundenen Archiv-HTTP- und kompakten Pipeline-Integrationstests sind teilweise rot; ihre Ursachen und Folgen bleiben gesondert zu prüfen. Quelle: working-memory/test_canonical_archive_http.py:30; working-memory/test_compact_reconcile.py:193
Die dokumentierte 140.000-Zeichen-Grenze betrifft einen historischen Prototyp und belegt keine aktuelle Produktionsgrenze. Quelle: archiv/governance-alt/working-memory/docs/TARGET.md:28
Die im Zielbild beschriebenen Bausteine Relevanz-Gate, Memory-MCP, Erinnerungen und Auftragspakete sind wegen offener Kalibrierung, Zustellung oder fachlicher Abnahme keine zusätzlich bestätigten Bestandsfeatures. Quelle: archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:41; archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:43; archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:44; archiv/governance-alt/working-memory/docs/ZIELBILD-PHASE1.md:47
