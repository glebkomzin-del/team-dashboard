# Altbestand erhalten und geordnet überführen

> Historische Migrationsplanung. Die Übernahme erfolgte am 07.09.2026; der nachfolgende technische Verarbeitungsrückstand wurde laut Abschlussnachweis am 21.09.2026 bis Revision 212 geleert. Die Zahlen und offenen Schritte unten beziehen sich auf die damalige Planung. Aktuelle Betriebsnachweise: [Release](RELEASE-2026-09-19.md) und [Betriebsstand](NEXT-OPERATIONS.md). Fachliche Prüfungen und offene Nutzeraufgaben sind vom technischen Verarbeitungsrückstand getrennt.

Die Vorschau `evaluation/backlog-preview.json` und `.csv` enthält 19 tatsächliche Inbox-Einträge aus der Finance-Folge vom 15./20. Juli. Jeder behält seine ursprüngliche ID, Quelle, Einordnung, Begründung und den Status `none_preview_only`. Keine produktive Zeile wurde gelöscht, erledigt oder umgeschrieben.

| Bisher | Vorgeschlagene Überführung |
|---|---|
| „Umrechnungskurse in Dates/S4 verbinden“ als Gleb-Aufgabe plus eigener FX-Blocker | Eine Voraussetzung am Reportingvorgang mit beiden Herkunfts-IDs. Nutzer bestätigt: keine neue Zusage. |
| „Gespräch mit VO führen“ als Oliver-Aufgabe | Diskutierte Option am selben Entscheidungsvorgang. Nutzer bestätigt: keine übernommene Abstimmung. |
| „Finale Entscheidung: Verzicht auf Monatsscheiben-Migration“ | Offener Entscheidungsbedarf; die Quelle enthält noch keine endgültige Entscheidung. |
| „Migration Monatsscheiben ja/nein“ aus dem Folgemeeting | Fortschreibung dieses Entscheidungsbedarfs; keine zweite unabhängige Aufgabe. |
| Caroline/Marc und Olivers Zweizeiler | Zwei getrennte fremde Verpflichtungen mit eigener Herkunft; nicht pauschal zusammenführen. |
| Montagstermin | Am 15. Juli offen; nach dem tatsächlich abgehaltenen Termin am 20. Juli erfüllt. Die fachliche Migrationsentscheidung bleibt offen. |

Drei Zeilen der Vorschau entsprechen im jeweiligen Meeting übernommenen fremden Verpflichtungen. Diese Anzahl ist weder ein Zielwert noch eine starre Obergrenze. Sämtliche übrigen Inhalte bleiben als Wissen, Voraussetzungen, Risiken, Optionen oder berichtete bestehende Arbeit erhalten. Eine kleinere Liste allein belegt keine Qualität.

Für die 1.499 wartenden und 264 aktiven Einträge: zuerst vollständiger Export einschließlich IDs, Status, Owner, Quellen und manuell bearbeiteter Felder. Manuell bereits angenommene Arbeit hat höheren Erhaltungsbedarf als ein ungeprüfter Make-Vorschlag. Fehlende Originalbelege werden als solche ausgewiesen, nicht automatisch als Fehler behandelt.

Danach Quell- und Versionsidentitäten abgleichen, nach fachlichen Themen gruppieren und einen vollständigen Vorschlag pro Vorgang erstellen. Gleiche Quelldatei plus gleiche Aussage ist ein Dublettenkandidat; ähnliche Titel allein reichen nicht. Fremde Aufgaben, verschiedene Ergebnisse und wiederkehrende Perioden bleiben getrennt. Ein altes Fälligkeitsdatum beweist keinen Abschluss. Langfristige Vorhaben bleiben offen oder ausdrücklich ruhend, bis ein belegter Abschluss, Abbruch oder eine bestätigte Überholung vorliegt.

Die Überführung erzeugt eine separate, wiederholbar aufbaubare Generation mit einer Zuordnungstabelle `legacy_id → source_version → observation → matter/work`. Jede alte ID muss in einer Erhaltungskontrolle vorkommen, auch wenn sie keine neue Aufgabe erzeugt. Neue aktive Verpflichtungen und gezielt gebündelte handlungsrelevante Konflikte stehen zuerst. Unsicherheit ohne aktuelle Konsequenz bleibt am Vorgang, statt hunderte Einzelprüfungen auszulösen.

Vor Freigabe sind zu vergleichen: nicht zugeordnete Alt-IDs, aktive Verpflichtungen ohne Ziel, automatische Abschlüsse, Owner-/Datumsänderungen, vermischte unterschiedliche Ergebnisse und Zitate ohne Original. Diese Änderungen müssen als verständliche Vorgangspakete vorliegen. Vollständige automatische Überführung und fachliche Abnahme des gesamten Bestands stehen noch aus; die 19 Zeilen sind der konkrete überprüfbare Ausschnitt.


## Vollständige Bestandssicherung, 6. September

Erfasst und mit allen IDs unverändert in einer getrennten SQLite-Sicherung erhalten: 175 Meetings, 64 Todos, 21 Blocker, 179 offene Punkte und 1.622 Inbox-Einträge (einschließlich 123 Meeting-Einträgen). Die 175 separat exportierten Originaltexte stimmen sämtlich mit den beim Snapshot erfassten SHA-256-Prüfsummen überein. Snapshot-SHA-256: `a132dfd2e732be6ebaecd30c90ab91e9e2b739e0eea8991615bef0d852d2e511`.

152 alte Meetingtexte stimmen vollständig mit Drive-Originalen überein; vier sind exakte Teiltexte; 19 sind abweichend und bleiben eigenständig erhalten. Bei drei alten Meeting-IDs existieren widersprüchliche Verknüpfungen zu mehreren Drive-Dateien. Gleicher Titel und gleiches Datum begründen keine automatische Zusammenführung, da tatsächlich mehrere verschiedene Gespräche denselben Titel und Tag tragen. Alle 1.622 Inbox-Datensätze haben eine vorhandene Drive-Quell-ID. Ein Quelllink bestätigt jedoch nicht die inhaltliche Richtigkeit des alten KI-Vorschlags.

`legacy_snapshot.py` erhält 2.061 Originaldatensätze, erstellt belastbare bzw. ausdrücklich ungeklärte Quellzuordnungen und erzeugt keine neuen Arbeitsereignisse. Die produktiven Supabase-Daten wurden weder gelöscht noch umgeschrieben. Maschinenlesbarer Nachweis: `evaluation/legacy-retention-result.json`.
