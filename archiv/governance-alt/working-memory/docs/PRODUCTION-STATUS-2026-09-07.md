# Produktive Übernahme – 07.09.2026

Die neue App ist unter https://team-dashboard-rho.vercel.app produktiv. Die ausdrückliche Nutzerfreigabe vom 07.09.2026 wurde ausgeführt. Frühere Freigabesperren und offene technische Prüfpunkte in historischen Protokollen sind damit überholt.

## Übernommen

- Neues ausschließlich helles Design, gegliederte Navigation, Bereichssuche, Filter, Dialoge und Rücknavigation.
- Persönliche Todos, getrennte Fälligkeit und Wochenplanung, Aufwandsschätzung, Teamansicht und Einstellungen.
- Aktives Team: Jan Gieselberg, Nikolaos Ginnas und Kimia Safei. Mathias Hummel bleibt als ausgeschiedene Person historisch erhalten.
- Finale Generation 614621ff-d766-4f20-8f6e-ad9bd0998fdc angenommen, kanonische Revision 107. 106 Quellen und 1.306 vorhandene Items manuell geprüft; 42 abschließende Korrekturen übernommen.
- 69 persönliche Aufgaben, 10 eigene bedingte Aufgaben, 252 Aufgaben bei anderen Verantwortlichen und 50 fachlich belegte Abschlüsse. Hinzu kommt ein ausdrücklich gekennzeichnetes, erledigtes technisches Abnahmetodo; Revision nach dessen drei Browser-Schreibvorgängen: 110.
- 194 archivierte Originale und 298 erhaltene Notizen. Bis einschließlich 31.05.2026 wurden die vorhandenen Zusammenfassungen und Originale erhalten, keine neuen Aufgaben extrahiert. Ab 01.06.2026 wurde der vorhandene Itembestand manuell in die neue Logik eingeordnet.
- Ausführliche Themenzusammenfassungen sind im Meetingdialog unter „Nach Themen“ erreichbar. 123 Originale enthalten insgesamt 560 ausführliche Themenabschnitte.

## Echte Prüfungen

- 217 Backendtests bestanden; vorheriger TypeScript-, ESLint- und Frontendbuild erfolgreich.
- Isolierter echter Supabase-Test: Anlage, Planung, Aktualisierung, Teamkonfiguration, Wiederholung derselben Entscheidungs-ID und Zurückweisung unberechtigter Akteure geprüft. Rekonstruktion aus dem Journal identisch; PostgreSQL-Wiederherstellung geprüft.
- Produktive bestehende Supabase-Anmeldung blieb erhalten. Browser → App → API → Supabase: manuelles Abnahmetodo angelegt, nach Serverneustart vorhanden, Plantag 07.09. und Frist 08.09. getrennt gespeichert, im Wochenkalender geprüft, anschließend erledigt. Alle drei Vorgänge im Verlauf vorhanden. Filter blieb beim Rücksprung erhalten.
- Beim ersten produktiven Wiederaufbau überschritt der Dienst sein 512-MiB-Containerlimit und wurde beendet. Die Änderung war bereits in Supabase gespeichert. Limit auf dem vorhandenen Server auf 1 GiB erhöht; weitere Speicherung und Abschluss ohne Neustart/Fehler geprüft. Kein zusätzlicher Server gebucht.
- Alle sieben ausgelieferten Frontenddateien stimmen bytegenau mit dem geprüften Build überein. Anonyme Aufrufe von Arbeitsstand, Archiv und Betrieb liefern 401.
- Archiv mit echtem Konto geöffnet, Gesamt- und ausführliche Themenzusammenfassungen gelesen. Service meldet production und healthy.

## Altlogik stillgelegt

- Make-Szenario 5388913 „Google Drive ->Dashboard Job“ ist inaktiv.
- 41 alte Trigger deaktiviert, Schreibrechte auf 21 alten Tabellen und Ausführungsrechte für 30 alte Anwendungs-RPCs entzogen. Der bestehende Leseberechtigungsprüfer behält seine ursprünglichen Rechte.
- Alte Cronjobs 8 und 9 deaktiviert.
- Alle neun alten KI-Edge-Endpunkte durch netzwerk- und datenbankfreie HTTP-410-Antworten ersetzt; jeder Endpunkt tatsächlich aufgerufen und geprüft. working-memory-journal bleibt aktiv.
- Produktive Nginx-Route zeigt auf den neuen Dienst. Beide früheren Dashboard-Dienste gestoppt. Andere n8n-/Picnic-Workflows unverändert; die fünf Dashboard-n8n-Workflows sind inaktiv.
- Bestehende Daten bleiben in Supabase. 3.197 alte Chunks und 71 Embeddings unverändert, keine Neuerstellung oder Löschung.

## Abschlussinventur ohne Modell-API

Alle 19 weiterhin in der bisherigen Inbox als pending markierten Meetings entsprechen anhand ID und Transkript-SHA genau den bereits manuell geprüften Quellen. Sie sind im neuen Archiv und Arbeitsstand berücksichtigt; der alte Inbox-Status wurde nicht als neue Freigabe oder erneuter Import verwendet.

Die 1.306 Altitem-Entscheidungen enthalten 100 ausdrücklich als Dopplung behandelte Fälle und 66 Fortschreibungen vorhandener Aufgaben. Die produktive Abschlussinventur umfasst 382 eindeutige Arbeitsidentitäten einschließlich des technischen Abnahmetodos sowie 1.280 eindeutige Wissensbeobachtungen. Keine doppelten Arbeits-IDs oder identischen Titel beim selben Verantwortlichen. Sieben zusätzliche Ähnlichkeitspaare manuell bewertet: unterschiedlicher Empfänger, offene Frage versus Zusage oder bereits verknüpfter späterer Fortschritt. Keine weitere belegte Doppelaufgabe gefunden; Datums- und Quellenhistorie nicht gelöscht. Die thematischen Filter fassen gleiche Bezeichnungen bereits zusammen, ohne unterschiedliche Quellenidentitäten zu überschreiben.

## Sicherung und verbleibende Betriebsentscheidung

Vorherige vollständige Sicherung und Wiederherstellung erfolgreich. Nach der Übernahme erneut vollständiges Paket dashboard-20260907T123751Z.tar.gz, SHA-256 067c0df6d544a3e9d64ff21e33dccce4a6f6f56272236ccf96fee51c47cfdc93, 31.770.787 Bytes. Alle 88 Dateien verifiziert und unabhängig auf den Mac kopiert. Kanonisches Journal/Originale, Runtime, Konfiguration sowie n8n-Daten und entschlüsselbar wiederherstellbarer Google-Refresh-Zugang enthalten. Die n8n-Wiederherstellung erfolgt isoliert ohne externes Netz und ohne aktive/publizierte Workflows. Dies ist keine vollständige Sicherung sämtlicher Supabase-Auth-Nutzer oder sämtlicher alten Tabellen.

Die produktive App ist nutzbar. Kostenpflichtige automatische Verarbeitung bleibt bis zu einer ausdrücklichen Budgetentscheidung pausiert, ebenfalls der Drive-Workflow. Ein Gesamtbudget von höchstens 10 USD für ausschließlich künftige Meetings wurde separat zur Entscheidung gestellt. Kein Monatsbudget und keine automatische Erhöhung. Frühester zulässiger Meetingstichtag ist 08.09.2026; heutiger und historischer Bestand bleiben vom bezahlten Weg ausgeschlossen. Bisher 0 kanonische Modellaufrufe und 0 neue Verarbeitungsjobs.

Offene fachliche Prüfungen in der App sind beabsichtigte unklare Aussagen, keine technischen Freigabesperren. Sie werden nicht pauschal zu persönlichen Zusagen umgedeutet.

Modellbewertung: siehe MODEL-CHOICE-2026-09-07.md. Prüfquittungen stehen unter ../evaluation/production-*.json und retired-edges-result.json. Das private Rückfallpaket bleibt getrennt erhalten; keine automatische Reaktivierung alter KI-Automatik.


## Aktualisierung: Terra aktiviert ohne Kostenobergrenze

Nach ausdrücklicher Nutzerfreigabe am 07.09.2026 läuft die produktive Automatik mit GPT-5.6 Terra für neue Meetings ab 08.09.2026, ohne Kostenobergrenze und mit fortlaufender Kostenprotokollierung. Frühere Hinweise auf ausstehende Budgetfreigabe oder 10 USD sind dadurch überholt. Einzelheiten und Prüfungen: [Terra-Implementierung](TERRA-IMPLEMENTATION-2026-09-07.md).
