# Dashboard Job – belegter Stand am 6. September 2026

## Ergebnis

Der Rückstau entsteht vor allem durch das fachliche Extraktionsmodell: Ein isolierter Aufruf pro Meeting erzeugt Aufgaben, Blocker und offene Punkte ohne Abgleich mit laufender Arbeit. Informationen werden zu prüfpflichtigen Einträgen. Fehlende Quellenbindung und voneinander unabhängige Folgeprozesse erschweren Korrekturen.

Die Bestandsaufnahme kombiniert live gelesene Supabase-Tabellen, Trigger und Edge Functions, das tatsächliche Make-Szenario 5388913, Serverprüfung per SSH sowie Originaltranskripte und ihre Inbox-Einträge. Rohbelege liegen ausschließlich im ignorierten Verzeichnis `.local/evidence/`. Zahlen sind eine Momentaufnahme; Tabellenstatistiken wurden durch tatsächliche COUNT-Abfragen ersetzt.

## Verifizierte Bestände

| Bestand | Anzahl |
|---|---:|
| Ausstehende Todos / Blocker / offene Punkte | 698 / 301 / 500 |
| Zusätzliche ausstehende Meetings | 19 |
| Aktive Todos / Blocker / offene Punkte | 64 / 21 / 179 |
| Projekte / Projekt-Meeting-Verknüpfungen | 0 / 0 |
| Meetings mit Originaltranskript | 175 |
| Zusätzliche Entscheidungen / Zusagen / offene Schleifen | 214 / 162 / 254 |

Alle 264 aktiven Einträge haben keine Projektzuordnung. Alle 1.499 ausstehenden fachlichen Inbox-Einträge haben weder Projekt noch Originalzitat/Chunk-Beleg. In den drei zusätzlichen Wissensbeständen fehlt `evidence_chunk_id` ebenfalls durchgängig. Elf Meetings besitzen keine eigentlichen Transkript-Chunks; fünf Quelldateinamen kommen mehrfach vor. Gleicher Dateiname beweist keine identische Version.

## Tatsächliche Verarbeitungskette

1. Make beobachtet einen Drive-Ordner alle 15 Minuten, höchstens zwei Dateien je Abholung; Export als Text.
2. Ein Anthropic-Aufruf mit `claude-sonnet-4-6`, 8.192 maximalen Ausgabetokens und dem Auftrag „vollständig und textnah extrahieren“ erhält ausschließlich das aktuelle Transkript. Kein Abruf bestehender Projekte oder Verpflichtungen.
3. Make schreibt ein Meeting sowie getrennte Todos, Blocker und offene Punkte in die Inbox. Ein berechneter MD5-Inhaltshash wird im eigentlichen Schreibpfad nicht als Idempotenzschlüssel verwendet. Die Verzweigungen bilden keine gemeinsame Transaktion.
4. Bei Übernahme in den Meetingbestand starten Datenbanktrigger `ingest-transcript` und `extract-structured-data` unabhängig voneinander. Eine Reihenfolge „erst vollständige Chunks, dann strukturierte Extraktion“ ist nicht garantiert.
5. `ingest-transcript` erzeugt OpenAI-Embeddings mit `text-embedding-3-small`. Der vorhandene `OPENAI_API_KEY` liegt in der Supabase-Funktionsumgebung. Make selbst erzeugt diese Embeddings nicht.
6. `extract-structured-data` schreibt zusätzliche Entscheidungen, Zusagen und offene Schleifen, nicht die sichtbaren Make-Todos. Die Live-Version verwendet `claude-sonnet-4-20250514`, maximal 2.000 Ausgabetokens, AI-Zusammenfassungen und nur die ersten 12.000 Zeichen des Originals.
7. `detect-resolutions` versucht anschließend, bestehende Einträge anhand begrenzter Kandidaten und Passagen aufzulösen. Zusammenfassungen werden teilweise als Beleg akzeptiert.
8. `ask-memory` verwendet Sonnet 4.6, umfangreiche gecachte Meeting-Zusammenfassungen, strukturierte Daten und begrenztes Chunk-Retrieval. Damit ist die Suche nicht identisch mit der sichtbaren Aufgabenverwaltung.

Make meldete gleichzeitig `isActive=true` und `isPaused=true`. Die letzten ausgelesenen Ausführungen reichen bis 31. August. Die nachfolgende Live-Prüfung bestätigt die Ursache: Organisation 7361129 ist pausiert, alle 1.000 Free-Operationen verbraucht, Restkontingent null. Nächster Reset: 27. September 2026, 21:41 UTC. Ein getrenntes reines Drive-Leseszenario wurde wegen dieses Kontingents abgewiesen.

## Weitere belegte Fehlerpfade

- Für Meetings, Todos, Blocker, offene Punkte und Projekte existieren jeweils zwei Embedding-Trigger auf dieselbe Triggerfunktion. Die konkrete zusätzliche API-Last hängt vom Ereignis und den Triggerbedingungen ab; die Zahl aller historisch doppelt abgerechneten Aufrufe ist nicht belegt.
- Die strukturierte Extraktion prüft weder HTTP-Fehler noch alle Insert-Ergebnisse ausreichend. Ein API-Fehler kann wegen `content?.[0]?.text ?? "{}"` zu einem leeren scheinbar erfolgreichen Ergebnis werden. Der verwendete alte Sonnet-Modellname fehlt in der aktuell mit dem Konto abgerufenen Modellliste; ein expliziter Inferenztest dieses alten Namens steht aus.
- Die Extraktion läuft ohne zuverlässige Quellenversions-Idempotenz. Der Ingest bewertet vorhandene Chunks nach Anzahl/Länge statt anhand des Quellhashes.
- Erzwungenes Re-Ingest löscht Chunks vor erfolgreichem Ersatz. Das Originalfeld wird außerdem durch den Parser aktualisiert, statt eine unveränderliche Eingangsquelle zu erhalten.
- Der Make-Prompt verlangt Datumsableitung aus dem Dateinamen, übergibt in seinem Text aber nur den Dateiinhaltswert. Relative Zeitangaben werden teils künstlich zu einzelnen Tagen präzisiert.
- `created_at` eines Meetings wird per Trigger auf `meeting_date` gesetzt. Es ist damit kein zuverlässiger Zeitpunkt der tatsächlichen Kenntnisnahme/des Imports.
- Die Frontend-Inbox-Abfrage hat keine sichtbare Pagination. Ob der konkrete REST-Servergrenzwert Einträge abschneidet, muss noch durch eine echte Abfrage geprüft werden; 1.518 wartende Inbox-Zeilen machen das relevant.

## Reale Beispiele

**15. Juli, Finance 2.0:** Aus fehlenden Umrechnungskursen und Konsolidierungsbuchungen wurde eine persönliche Aufgabe für Gleb. Gleb bestätigt ausdrücklich: Voraussetzung, keine neue Zusage. Diese Abhängigkeit gehört an den Vorgang „Vorjahresreporting / Monatsscheiben“, während Olivers ausdrückliche Terminzusage erhalten bleibt. Ein diskutierter Verzicht auf Migration ist noch keine getroffene Entscheidung.

**20. Juli, derselbe Themenbereich:** Die Entscheidung bleibt offen, weil der Bilanz-/Board-Bedarf noch geklärt werden muss. Caroline übernimmt Rücksprache mit Marc am Mittwoch; Oliver sagt eine schriftliche Zusammenfassung zu. Das aktualisiert den Entscheidungsstand desselben Vorgangs. Die bloße Möglichkeit einer KPS-Beauftragung erzeugt keine Aufgabe.

**18. Juni, Mathias/Gleb:** Gleb übernimmt die Prüfung der Entwürfe und Rückmeldung. Die vorhandene Aufgabe „2-Wochen-Termin einstellen“ stammt aus einer stark beschädigten ASR-Passage. Die fachliche Nutzerkalibrierung zu diesem zweiten Beispiel ist noch offen; sie wird nicht als bestätigtes Goldlabel ausgegeben.

## Server und Betrieb

SSH-Zugang zu 178.105.167.26 funktioniert. n8n 2.20.9, PostgreSQL 16 und Picnic laufen; etwa 26 GB freier Plattenplatz. Das n8n-Image nutzt einen beweglichen `latest`-Tag. Sechs Workflow-Metadaten wurden gelesen, davon drei aktive Picnic-Workflows. Der anfängliche n8n-Bestand hatte einen Kitchen-PostgreSQL-Zugang und keinen Drive-OAuth-Zugang. In Make bestehen dagegen drei gültig konfigurierte Google-Verbindungen; der Ordnerabruf über die vorhandene Verbindung funktioniert. Siehe unten. Die geprüfte Crontab enthält Picnic-Wartung. PostgreSQL-Dump und Wiederherstellung in einem getrennten Wegwerfcontainer sowie Online-Backup/Integritätsprüfung des Testdienstes wurden inzwischen erfolgreich geprüft. Eine regelmäßige externe Sicherung ist noch einzurichten.

Produktive Importfunktionen, Make-Aktivierung, Altbestand, Picnic und Frontend-Veröffentlichung wurden nicht umgeschaltet. Hinzugefügt wurde ausschließlich `dashboard-memory-eval`: intern authentifizierter, zeitlich bis 8. September 00:00 UTC begrenzter API-Testzugang ohne Datenbankzugriffe. Der OpenAI-Schlüssel verlässt seine bisherige Umgebung nicht. Unberechtigter Live-Aufruf: HTTP 401; interner Modellabruf und drei strukturierte Inferenztests: HTTP 200.

## Nachträge aus Implementierung und Zugangstest

Auf Hetzner läuft jetzt zusätzlich der isolierte Container `dashboard-memory-preview-memory-preview-1`, ohne öffentlichen Port, mit eigener SQLite-Datenablage. n8n hat jetzt sieben Workflows und zwei Credentials. Der neue Workflow „Dashboard Job – isolierter Importtest“ (ID `cwY12LjLd4UnJoEC`) bleibt ohne Zeitplan. Ein echtes Juni-Meeting wurde erfolgreich verarbeitet; erneuter Import und Neustart erzeugten keine zusätzliche Arbeit. Die aktuelle Dienstversion v4 enthält Streaming, Quellenkorrekturen und zusätzliche Handlungsprüfung. Das bereits importierte Juni-Meeting wird bei einem Versionswechsel absichtlich nicht nochmals bezahlt verarbeitet.

Make-Verbindungen im tatsächlichen Szenario: `7501532` beobachtet den Eingangsordner, `7501500` liest Dateien (beide `drive.readonly`), `7501561` verschiebt Dateien (`drive`). Alle gehören demselben Google-Konto; Ablaufmetadatum 1. März 2027. Der RPC-Ordnerabruf über `7501500` lieferte „Inbox“ und „Processed“. Es fehlt folglich kein genereller Google-Zugang. Die Make-Verbindungs-API liefert Metadaten und Scopes, keine OAuth-Tokens. Ein unterstützter direkter Export in n8n wurde mit den verfügbaren Werkzeugen nicht gefunden.

Der ausschließlich lesende Make-Test `7266049` („Dashboard Job – Drive-Lesetest 15.07.“) wurde angelegt. Seine Ausführung ist wegen des erschöpften Make-Kontingents blockiert, nicht wegen eines Google-Authentifizierungsfehlers. Kein Upgrade, Kauf zusätzlicher Operationen oder Eingriff in das bestehende Szenario vorgenommen.
