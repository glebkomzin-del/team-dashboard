# Ergebnis und gesicherter Stand – 09.09.2026

## Entscheidung

v11 ist nach ausdrücklicher Nutzerfreigabe der zwei zusätzlichen Prüfhinweise **produktiv aktiviert**. Die Teilkorrektur im Dashboard ist ebenfalls veröffentlicht. Der echte Drive-Push und die abgesicherte Veröffentlichungsabfrage sind bereits aktiv. Der Processed-Move ist nach ausdrücklicher Freigabe des erweiterten Google-Zugriffs ebenfalls aktiv. Fünf bereits veröffentlichte Originale wurden erfolgreich verschoben; Inhaltsprüfsummen und Zielordner wurden anschließend unabhängig nachgelesen.

Die strengen Abnahmekriterien aus `KOSTENOPTIMIERUNG-PLAN-2026-09-08.md` sind nicht vollständig erfüllt: Die gemessene Modellkostensenkung beträgt 69,804 % statt mindestens 70 %, und zwei bestehende Wissensaussagen erhalten zusätzliche Prüfhinweise. Das wird nicht durch eine nachträgliche Änderung der Abnahmekriterien als bestanden ausgegeben.

## Gemessener langer Vergleich

Original: „VS Code + Python + PBI“, 08.09.2026, 35.960 Zeichen. Historischer Bestand auf Journalrevision 110 fixiert. Unveränderte, bereits bezahlte Terra-Extraktion wiederverwendet; ihre regulären Kosten und Providerzeit im Vergleich dennoch vollständig mitgezählt. Testläufe veröffentlichen keine neuen Dashboard-Ergebnisse.

| Kennzahl | bisher v10 | geprüfte v11 |
|---|---:|---:|
| Modellaufrufe | 12 | 3 |
| Eingabetokens | 589.011 | 145.991 |
| Modellkosten | 1,614567 USD | 0,487530 USD |
| Zusagen als neue Aufgaben | 2 | 2 |
| ursprüngliche Beobachtungen erhalten | 15 | 15 |
| zusätzliche alte Fortschrittsvorschläge ohne ausreichenden Beleg | 3 | 0 |
| Prüfhinweise insgesamt | 5 | 4 |
| Aufgaben im Suchergebnis / Bestand | 240 / 381 | 240 / 381 |
| Suchsnapshot | identisch | identisch |
| Providerzeit aller Modellstufen | 141,6 s | 98,095 s |

- v11-Stufen: Extraktion 0,105526 USD; kombinierter Abgleich 0,333840 USD; unabhängige Abschlussprüfung 0,048164 USD.
- Preisziel 0,4843701 USD: um 0,0031599 USD überschritten. Rund 70 % günstiger ist korrekt; „mindestens 70 % bestanden“ wäre falsch.
- Die 25 Suchanfragen benötigen Embeddings im Gegenwert von 0,000028 USD. Bereits vorhandene Inhalts-Embeddings wurden verwendet. Kosten eines komplett frischen Inhaltsindex wurden in diesem warmen Vergleich nicht erneut gemessen; die Modellkosten sind kein pauschaler All-inclusive-Meetingpreis.
- Beim EZB-Kurs 1,1614 USD/EUR vom 08.09.2026 entsprechen Modellkosten und Suchanfragen etwa 0,42 EUR netto beziehungsweise 0,50 EUR mit vorsorglichem 19-%-Aufschlag. Kein Durchschnitt über viele Meetings.
- Wandzeit des letzten isolierten Laufs ungefähr 86 Sekunden, dabei war die Extraktion bereits bezahlt und wurde wiederverwendet. Ein reiner Replay benötigte ungefähr 30 Sekunden. Daraus folgt kein belegter neuer Ende-zu-Ende-Wert für ein frisches Meeting; allein reguläre Modellstufen entsprechen hier rund 98 Sekunden. Die frühere Aussage 20–30 Sekunden ist damit nicht bestätigt.

## Fachliche Gegenprüfung

Beide Zusagen bleiben richtig zugeordnet: Kimias begrenzter XMLA-Test und Glebs gemeinsame Erprobung mit Kimia. Keine Erfolgszusage aus einer Bemühenszusage. Entscheidungen, Ideen, Status, Voraussetzungen und Risiken der 15 ursprünglichen Beobachtungen bleiben erhalten; das Meeting-Summary stammt aus derselben vollständigen Extraktion.

Die drei entfallenen Fortschrittsmeldungen waren bereits von der alten Abschlussprüfung als unzureichend belegt verworfen worden: Workflow-Übersicht, GitOps-Besprechung und GCP-Zugang. Die Erörterung verwandter Technik erfüllt diese konkreten Verpflichtungen nicht. Ihr Wegfall ist kein Verlust belegter Erledigungen.

Zwei zusätzliche Prüfhinweise bleiben eine echte Abweichung:

1. **Modellrechte/Tenant-Funktion:** Die genannten Voraussetzungen sind belegt; die erfolgreiche spätere Verbindung ist noch offen. v11 senkt deswegen die Aussage-Sicherheit auf Stufe 1. Die neue Anweisung zur Unterscheidung von Aussage und Erfolg hat diese unnötige Unsicherheit im realen Fall nicht zuverlässig beseitigt.
2. **Claude-Abschaltung:** Der Bericht Glebs ist enthalten; ASR-Produktnamen und Hintergründe bleiben offen. v11 setzt Stufe 1, während v10 den eingeschränkten Bericht mit Stufe 2 behandelte.

In Summe weniger Prüfhinweise beweist nicht, dass pro vergleichbarem Sachverhalt keine zusätzliche Nacharbeit entsteht. Deshalb keine automatische Freigabe gegen das festgeschriebene Kriterium.

## Implementierte Logik

- Extraktion am vollständigen neuen Meeting erzeugt die vorhandenen Gegenstände, Keywords, Beobachtungen und Zusammenfassungen. Keine neue Projektdimension.
- Bestehende lexikalische und semantische Suche bleibt erhalten. Keine KI-Neuklassifikation des gesamten Altbestands; vorhandene Inhalts-Embeddings werden wiederverwendet.
- Alle gefundenen Aufgaben bleiben im Abgleich. Keine neue Altersgrenze, kein gemeinsames Keyword als zwingender Filter, keine zusätzliche Top-K-Kappung.
- Aufgaben stehen im letzten Entwurf als vollständige, normale Einträge mit lokalem W-Alias und explizitem Ergebnisindex im Prompt. Nur Archiv-Suchkarten werden tabellarisch komprimiert und teilweise als Vorschau dargestellt. Originale bleiben verfügbar; eine Vorschau allein darf keine historische Themenzuordnung freigeben.
- Zuordnung und Aufgabenänderungsprüfung erfolgen zusammen. Die unabhängige Abschlussprüfung erhält das vollständige aktuelle Original und Originalbelege betroffener Aufgaben.
- Neue v11-Aufrufe zählen ihren identischen Input samt Schema vorab über den offiziellen Tokenzählendpunkt. Vollständige maximale Ausgabe, 4096 Sicherheitstokens und Preisaufschläge bleiben reserviert. Unklare frühere Nutzung bleibt angerechnet. Replays erzeugen keine zweite Modellrechnung.
- Der Index rekonstruiert weiterhin technisch den zulässigen Bestand und prüft auf vorhandene Einträge. Inkrementelle Rekonstruktion und dauerhafte Zusammenführung alter/neuer Suchbegriffe bei Statusänderungen sind **nicht** zusätzlich umgesetzt; sie sind getrennte verbleibende Punkte des Plans. Bestehende Beobachtungen behalten ihre gespeicherten Merkmale, aber die aktuelle Aufgabenansicht kann durch neue Ereignisse Suchmerkmale ersetzen.

## Tests und Grenzen

- **284 Python-Tests bestanden** (einschließlich Teilkorrektur, wiederholter Wissenskorrektur ohne Aufgabenentstehung, korrigierter Zuständigkeit, erneuter Korrektur nach Verwerfen und Suchfeedback), abschließend mit Produktionsumgebung v11; der alte v4-Testaufbau wurde explizit auf seine eigene Fixture-Version festgelegt.
- **6 Node-Testgruppen bestanden:** zehn Move-Pläne, doppelte Ausführung, geänderte Datei/Version, fehlendes ETag, v2-Metadaten und bestätigter Move-Inhalt.
- Terra bestand zunächst die acht Fachfälle. Nach der Regelkorrektur bestanden erneut alle acht, einschließlich einer erlaubten Vertragsreparatur beim alten Termin.
- Mit dem endgültigen Format der Aufgaben wurden die vier betroffenen schwierigen Fälle erneut bezahlt geprüft: Paraphrase, alte Terminzusage, gleicher Bericht/andere Handlung, nur eine von zwei Freigaben. Alle bestanden; der alte Termin brauchte eine Vertragsreparatur. Die übrigen vier kleinen Fälle wurden nach dieser letzten Formatänderung nicht nochmals bezahlt wiederholt.
- Vier zusätzliche positive/negative Modelltests zur gemeinsamen Zusage bestanden. Ein „wir übernehmen“ mit klarer Gruppe ist von „wir könnten“, einer Bitte an andere und unklarem Gruppenbezug getrennt.
- Luna: zwei einfache Fälle bestanden, danach doppelte Zustandsänderung beim Paraphrase-Fall, auch nach einer Reparatur. Die Serie wurde gestoppt. Keine Gleichwertigkeit zu Terra festgestellt; kein Luna-Rollout.
- Der vollständige letzte reale Lauf bestand alle Struktur-/Belegprüfungen ohne Reparatur und ohne Nachladen. Ein anschließender Replay verwendete ausschließlich bezahlte Antworten und änderte das Kostenledger um **0 USD**.
- Ein vorheriger langer Entwurf verlangte fast alle Archivtexte und stoppte am Kontextlimit. Das ist dokumentiert, keine verlorene Datei und kein veröffentlichtes Teilergebnis. Die letzte Aufgabenrepräsentation beseitigte dieses Verhalten im geprüften Fall; keine Garantie für alle künftigen Fälle.
- Keine zehn echten gleichzeitigen Meetings getestet. Echter OAuth-berechtigter Move-Ende-zu-Ende-Lauf mit fünf bereits veröffentlichten Originalen erfolgreich; Wiederholung ohne weiteren PATCH und automatischer Minutenlauf ebenfalls erfolgreich.

## Bereits produktiv

- Intake `nzyaKxs5Om9wuPEc`: authentifizierter Google-Drive-Push zusätzlich zur Zehn-Minuten-Nachholung.
- Erneuerung `dashboardDriveWatch`: täglich, sechs Tage Kanallaufzeit, Erneuerung spätestens zwei Tage vor Ablauf.
- Echter Google-Sync-Callback in n8n-Ausführung 20426 beobachtet. Ohne Header 403, authentifiziert 200. Der kurzlebige Testkanal verfällt; der Hauptkanal bleibt gespeichert.
- `/drive-completion/{document_id}` prüft Originalidentität, aktuelle Dateiversion, Prüfsumme und dauerhaft veröffentlichten Job. Nur Service-Zugriff; Owner-Zugriff 403. Zwölf vorhandene veröffentlichte Dokumente ergeben gültige Belege.
- Vorheriger Modellkern war v10: `v10:hybrid1:gate1:gpt-5.6-terra:ac77cd367e6e4e8e:canonical1:bb59e5f58c5e11f8`. Zwölf Jobs veröffentlicht, keine wartenden Jobs beim Schlusscheck.

## Processed-Move produktiv und live geprüft

Flow `dashboardDriveMove` ist veröffentlicht und aktiv; er prüft jede Minute. Er liest ausschließlich die konfigurierte Inbox, verlangt einen gültigen Veröffentlichungsbeleg, liest aktuelle Drive-v2-Metadaten mit ETag und verschiebt bedingt mit `If-Match`. Nach dem PATCH werden Zielordner und unveränderte Inhaltsprüfsumme geprüft. Fehler einer Datei erzeugen keinen zweiten Modellaufruf.

Der erste Schreibversuch mit `drive.metadata` hatte HTTP 403 `fileAccess` ergeben; ein bewusst veraltetes ETag wurde zuvor mit HTTP 412 abgelehnt. Nach ausdrücklicher Nutzerfreigabe („ja, du darfst“) wurde ausschließlich die separate Verbindung „Dashboard Job – Google Drive verschieben“ auf `https://www.googleapis.com/auth/drive` erweitert. Der tatsächlich gewährte Scope wurde bei Google geprüft, ebenso dieselbe Google-Konto-ID. Die Leseverbindung hat weiterhin ausschließlich `drive.readonly`. Technisch umfasst die Schreibberechtigung das gesamte Drive; der konfigurierte Flow arbeitet ausschließlich zwischen Inbox und Processed.

Live-Nachweise am 09.09.2026:
- Ausführung **20509**: fünf bereits veröffentlichte Inbox-Dateien erfolgreich nach Processed verschoben, darunter die beiden zuvor geprüften Beispiele. Alle fünf Ergebnisse anschließend direkt bei Google nachgelesen: Zielordner vorhanden, Inbox entfernt, Inhalt unverändert, nicht im Papierkorb.
- Ausführung **20517**: Wiederholung erfolgreich; kein PATCH und keine erneute Verschiebung. Inbox leer.
- Ausführung **20518**: erster automatischer Minutenlauf erfolgreich. Aktivierung über n8n-Oberfläche, kein Neustart nötig.
- Intake, Kanal-Erneuerung und Move-Flow aktiv. Gespeicherter Hauptkanal läuft bis 14.09.2026; tägliche Erneuerungsprüfung bleibt aktiv. Authentifizierter Hook-Test HTTP 200, ohne Berechtigung HTTP 403. Backend-Health bestätigt Produktionsbetrieb.
- Für diese Google-/n8n-Prüfung wurden keine KI-Testaufrufe gestartet.
- Schlusscheck: Journalrevision 126, keine wartenden Jobs, Produktionsnutzung 7,601221 USD bei unverändertem Deckel 8,878649 USD. Seit dem vorherigen Stand kamen drei Quellveröffentlichungen hinzu (08:52, 09:02, 09:18 UTC), alle vor dem Move-Test um 09:27 UTC. Die zusätzliche reguläre Nutzung von 0,412752 USD ist daher getrennt von den kostenfreien Move-Tests zu betrachten; der frühere Produktionswert 7,188469 USD unten dokumentiert den vorherigen Stand.

## Budget und Fortsetzung

Gemeinsames Testledger nach den letzten Fachfällen: **11,459170 USD**, davon 1,652205 USD ungeklärte Nutzung weiterhin reserviert. Zusätzlich anrechenbarer Wiederanlauf: 0,567840 USD. Oberer aufgezeichneter Auftragsstand somit **12,027010 USD**, beim angegebenen Kurs mit 19-%-Puffer etwa **12,32 EUR**. Noch 0,040830 USD im ausdrücklich zugeteilten Testdeckel; kein weiteres großes Experiment gestartet. Nutzerobergrenze bleibt 15 EUR, kein automatisches Nachfüllen.

Gebauter, noch nicht gestarteter Kandidat: `dashboard-memory-v11:cd121312d5be3c22`. Netzwerkfreier Container-Smoke-Test bestätigt:
`v11:compact1:gate1:gpt-5.6-terra:cd121312d5be3c22:canonical1:4b4bf0c190a6a2c3`.

Aktuelle Produktionspipeline: `v11:compact1:gate1:gpt-5.6-terra:25495068bcd57832:canonical1:4b4bf0c190a6a2c3`.
Image: `dashboard-memory-v11:correction-final-20260909`. Rückweg und vorherige Dateien/Umgebung unter `.local/correction-release-20260909/rollback`; altes Image `dashboard-memory:before-correction-20260909` erhalten. Produktionsbudget 8.878649 USD und bisherige Nutzung 7.188469 USD unverändert. 12 veröffentlichte Jobs, keine neu eingereihten Bestandsmeetings.

Dashboard-Deployment `dpl_DqnhjW7pfLGRC9k33LDjeAZ6nP5H` READY, Alias `https://team-dashboard-rho.vercel.app`. Sieben veröffentlichte Asset-Prüfsummen stimmen mit dem Build überein, anonyme API-Anfragen bleiben 401. Browserprüfung am echten Wissenseintrag: Korrigieren und bestätigen sichtbar, Dialog mit Titel/Aussage/Begründung öffnet sich. Keine erfundene Nutzerkorrektur in Produktion gespeichert.

Teilkorrektur: Originaltext und Belegzitate unverändert; datierte Nutzerfassung und Begründung als eigenes Journalereignis. Wissenskorrekturen erzeugen keine Aufgabe, auch nach mehrmaliger Bearbeitung. Vorgeschlagene Aufgaben können mit korrigierter Person/Text/Status/Frist bestätigt werden. Interpretationsfeedback gelangt in die vorhandene hybride Suche; nur neue/geänderte Inhalte benötigen neue Embeddings. Keine behauptete Modellnachschulung oder garantierte Übertragung jeder Ablehnung.

Browser-Fixtures geprüft: ausschließlich falschen Satzteil korrigieren; Originalbeleg behalten; Abbruch mit ungespeicherten Änderungen; Teilfortschritt statt falschem Aufgabenabschluss; nach verlorener Speicherantwort gleiche command_id und identische Daten beim Wiederholen. Finaler TypeScript/Vite-Produktionsbuild und ESLint der geänderten Dateien bestanden in einer lokalen Kopie außerhalb von iCloud. Die eigentliche Workspace-Installation hatte temporär nicht lesbare Abhängigkeiten; Quellabgleich ergab keine weiteren Frontend-Differenzen. Bestehende PostCSS-/Tailwind-Konfiguration beim Build vollständig übernommen.

Die zuvor ausstehende Google-Freigabe, der Schreibtest und die Aktivierung samt Inbox-/Processed-, Duplikat- und Hook-Prüfung sind abgeschlossen. Quellen bleiben bei Fehlern unverändert in der Inbox. Metadatenbedingte Versionsanstiege bei identischer Inhaltsprüfsumme sind erlaubt; frisches ETag schützt vor Änderungen zwischen Lesen und Verschieben. Modellverarbeitung ist davon unabhängig bereits produktiv.

Server-Staging und Nachweise: `/opt/dashboard-memory-canonical-draft/.local/cache/cost-optimization-20260908/`; Deployment-Backups/Logs: `/opt/dashboard-memory-canonical-draft/.local/cost-optimization-20260908/`. Lokale private Rohbelege: `.codex-deploy/cost-optimization-20260908/`. Private Prompts, Ledger und Kanal-Token nicht veröffentlichen.
