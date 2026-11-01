# Meeting-Verarbeitung: Umsetzung und Abnahme vom 8. September 2026

## Produktiver Stand

Backend und Dashboard sind auf die geprüfte v10-Verarbeitung umgestellt. Das zuvor fehlgeschlagene Meeting **VS Code + Python + PBI** wurde mit dem bereits bezahlten, geprüften Terra-Ergebnis veröffentlicht (Revision 111). Es entstanden zwei Aufgaben: Glebs eigener Verbindungsversuch und Kimias XMLA-Test. Alle 381 vorherigen Aufgaben behielten Status, Zuständigkeit, Frist und Bedingung. Die 27 früher bezahlten API-Antworten wurden unverändert erhalten und nicht erneut versendet.

Revision 112 ergänzt ausschließlich die Schreibweisen `Kimia Safaei` und `Safaei, Kimia` beim vorhandenen Teamprofil `Kimia Safei`. Das Original bleibt unverändert. Im produktiven Dashboard ist ihre neue Aufgabe damit im aktiven Team sichtbar.

Die bisherigen unbegonnenen Inbox-Jobs wurden nachvollziehbar von beiden alten v9-Versionen auf v10 umgestellt. Der automatische Worker ist wieder aktiviert. Sein Wiederanlauf ist zusätzlich begrenzt; siehe Kosten. Aktueller abschließender Warteschlangenstand wird unten ergänzt.

Produktiv: https://team-dashboard-rho.vercel.app

## Tatsächlich implementierte Verarbeitung

1. Das vollständige neue Transkript wird eigenständig ausgewertet. Die bestehenden Wissensarten bleiben erhalten; es werden keine neuen Projekte hergeleitet. Neben Fakten, Entscheidungen und Ideen existieren weiterhin beispielsweise Risiken, Fragen, Voraussetzungen und Statusaussagen.
2. Beobachtungen bekommen einen konkreten Gegenstand, höchstens acht Suchbegriffe und überprüfbare Originalstellen. Eine Übersichtszusammenfassung entsteht im selben Extraktionsaufruf.
3. Die Suche kombiniert Volltext und semantische Vektoren. Je Anfrage werden die jeweiligen Treffer vereinigt. Aufgaben haben eine separate Suchquote, damit viele Archivpassagen sie nicht verdrängen.
4. Je Beobachtungsgruppe werden nur die zugehörigen Suchtreffer abgeglichen. Archivpassagen bleiben hier verfügbar. Transportmetadaten und mehrfach identische Texte werden nicht unnötig wiederholt.
5. Gefundene alte Aufgaben werden zunächst mit ihren Beschreibungen auf mögliche Änderungen geprüft. Für vorgeschlagene Änderungen öffnet die abschließende Prüfung die historischen Originalbelege. Sie erhält außerdem immer das vollständige neue Transkript.
6. Unklare belegte Altbezüge können eine einmalige gezielte Sucherweiterung auslösen. Unklarheit erzeugt keine erfundene neue Verpflichtung und keinen pauschalen zweiten Gesamtlauf.
7. Die Speicherung und Veröffentlichung erfolgt erst nach Belegprüfung und dauerhafter Indizierung. Antworten, Suchsnapshot und Suchtreffer bleiben nachvollziehbar; unbekannte API-Ausgänge werden nicht blind wiederholt.

**Embeddings sind enthalten:** `text-embedding-3-small`, 1536 Dimensionen, für Originalabschnitte, Wissenseinträge, Aufgaben, vorhandene/neu erzeugte Zusammenfassungen und geeignete Interpretationskorrekturen. Inhaltsgleiche Vektoren werden wiederverwendet. Die neue Originalquelle wird vollständig in Abschnitte zerlegt; keine stille Abschneidung. Bestehende Themenzusammenfassungen werden ebenfalls indiziert; eine zusätzliche eigene Erzeugungsstufe für neue Themenzusammenfassungen wurde nicht erfunden.

Es gibt keinen starren Alters- oder Projektfilter. Alte relevante Zusagen können weiterhin gefunden werden. Im realen Beispiel wurden 240 von 381 Aufgaben ausgewählt, nicht der gesamte Aufgabenbestand. Das ist noch eine breite Vorauswahl. Die semantische Suche und begrenzte Trefferzahl garantieren keine mathematische Vollständigkeit.

## Confidence und Lernen

Zuordnung und Aussage/Änderung erhalten Belegstufen **0/1/2**, keine Prozentwahrscheinlichkeiten. Ein Wert unter 2 erfordert Prüfung. Ein zweifelhaftes oder abgelehntes abschließendes Urteil senkt die sichtbare Belegstufe ebenfalls. Weder ein hoher Score noch eine erledigte Teilvoraussetzung darf unbelegt die ganze Aufgabe schließen.

Bestätigung oder Korrektur von Wissen erzeugt keine zusätzliche Aufgabe. Die Oberfläche unterscheidet eine falsche KI-Interpretation von einer später geänderten Sachlage. Geeignete Interpretationskorrekturen werden als Beispiele für spätere ähnliche Fälle gesucht. Es gibt bewusst keine selbständig allgemein gültig werdende Regel nach zwei oder drei Bestätigungen und kein automatisches Nachtrainieren des Modells.

## Begrenzte Qualitätsprüfung

- **261 Python-Tests bestanden**, inklusive historischer Wiederherstellung, Quellenpositionen, Kostenreservierung, Wiederaufnahme und Schutz gegen falsche Aufgabenabschlüsse.
- **20 Gateway-Tests bestanden**; neue Suchzugriffe sind an den Space/Snapshot gebunden, RLS bleibt aktiv.
- Frontend-Build bestanden. Produktiver Browser: neuer Task, Originalverlauf, Confidence mit Begründung und Teamzuordnung geprüft; keine dabei erfassten Browserfehler.
- Drei repräsentative Suchanfragen gegen exakte Vektorergebnisse geprüft: jeweilige 20 ANN-Treffer lagen in der exakten Spitzengruppe einschließlich Gleichständen. Das ist eine Stichprobe, kein globaler Recall-Beweis.
- n8n: echtes DOCX herunterladen, Version prüfen, Original archivieren und denselben Job einreihen geprüft; Wiederholung erzeugte keine Duplikate. Der bestehende Transportworkflow musste nicht fachlich umgebaut werden.

Vorab definierte kleine Fälle, jeweils Terra und Luna:

| Schwierigkeit | Fall | Erwartetes Ergebnis |
|---|---|---|
| leicht | Klare Zusage | Eine Aufgabe, richtiger Verantwortlicher und Fristausdruck |
| leicht | Reine Tatsache | Keine Aufgabe |
| mittel | Anders formulierte Erledigung | Richtige frühere Aufgabe schließen |
| mittel | Idee mit Voraussetzung | Keine erfundene Zusage |
| mittel | Termin ist keine Versandfrist | Keine erfundene Deadline |
| schwer | Sehr alte relevante Zusage | Trotz Alters auffindbar und korrekt erledigt |
| schwer | Gleiches Thema, andere Handlung | Nur die tatsächlich erledigte Aufgabe schließen |
| schwer | Nur eine von zwei Freigaben | Gesamtaufgabe bleibt offen und bedingt |

Beide Modelle bestanden zuletzt **8/8**. Zusätzlich wurde ausschließlich das freigegebene lange Meeting für den vollständigen Modellvergleich verwendet. Danach erfolgte der reguläre, budgetbegrenzte Wiederanlauf der Inbox; keine weiteren vollen Vergleichsmeetings.

## Entscheidung zu Luna und gemessene Kosten

| Gleiches langes Meeting, finale Logik | Terra | Luna |
|---|---:|---:|
| Neue Aufgaben | 2 | 2 |
| Wissens-/Statusbeobachtungen insgesamt | 18 | 26 |
| Prüfpflichtige Einträge | 5 | 18 |
| Technische Reparaturversuche im finalen Lauf | 0 | 1 |
| Modellkosten aller benötigten Stufen | 1,614567 USD | 0,174169 USD |

**Terra bleibt Standard.** Luna ist erheblich billiger, erzeugte in dieser Stichprobe aber deutlich mehr schwach begründete Bestandsbezüge und damit mehr Nacharbeit. Frühere Luna-Versuche scheiterten zudem an ungültigen IDs bzw. einer unzulässigen Dublettenzuordnung; die verschärften Verträge verhinderten deren Veröffentlichung. Die finale Luna-Version wurde erfolgreich beendet, aber daraus lässt sich keine allgemeine Qualitätsgleichheit ableiten.

Die Modellkosten wurden aus den gespeicherten Providerantworten den tatsächlich im erfolgreichen Lauf benötigten Stufen zugeordnet. Sie enthalten wiederverwendete Extraktion, nicht sämtliche verworfenen Entwicklungsversuche. Embeddingkosten kommen geringfügig hinzu. **Mit Terra ist damit noch kein großer Preisrückgang gegenüber den genannten etwa 1,50 EUR pro normalem Meeting nachgewiesen.** Die neue Architektur vermeidet den vollständigen Bestandsabgleich und wiederholte Embeddings; der größte verbleibende Kostentreiber sind die zahlreichen historischen Treffer im Zuordnungsmodell.

Gesamte neue Test-/Embeddingrechnung einschließlich Entwicklung und Modellvergleich:

- Bekannte Nutzung: **8,089775 USD**.
- Eine unvollständige Providerantwort ohne endgültige Nutzung: **1,652205 USD vorsorgliche Reservierung**. Antwort vorhanden, kein laufender/unbeantworteter Netzaufruf; nicht erneut senden und nicht als kostenlos behandeln.
- Konservativ zusammen: **9,741980 USD**, innerhalb des harten Testdeckels von 10 USD.
- Historische v9-Fehlversuche von 6,620629 USD gehören zum bereits vorher entstandenen Aufwand; keine erneute Abrechnung durch Wiederholung.
- Separater kontrollierter Wiederanlauf: höchstens **2,258020 USD** zusätzlich. Neue Tests und Wiederanlauf zusammen maximal **12 USD** nach hinterlegten Modellpreisen einschließlich ungeklärter Reservierung; ausreichender Abstand zur Nutzerobergrenze 15 EUR. Dies ist ein technischer Kostenzähler, keine Anbieterrechnung.

Keine automatische Aufstockung, kein unbeschränkter Wechsel zu einem teuren Ersatzmodell. Wenn die Reserve für einen nächsten Aufruf nicht reicht, bleibt die Quelle mit nachvollziehbarem Grund erhalten.

## Sicherung und Betrieb

- Vollständige Sicherung vor Umstellung: Revision 110, Archiv 504; 206 Originale, 298 vorhandene Zusammenfassungen, 1280 Wissenseinträge sowie Suchvektoren, Snapshots, gespeicherte Treffer und Kostenbelege.
- Offline-Rekonstruktion bestand inklusive Vektorlänge, Inhaltshashes, Snapshot-Mitgliedschaft und Suchtreffernachweisen. Vollständiges SQL zur pausierten Wiederherstellung wurde erzeugt. Ein kompletter Import dieses SQL in eine zweite Postgres-Instanz wurde nicht ausgeführt.
- Produktiver Pipeline-Identifier: `v10:hybrid1:gate1:gpt-5.6-terra:ac77cd367e6e4e8e:canonical1:bb59e5f58c5e11f8`.
- Vercel-Deployment: `dpl_BDrbCXPHqFSbyvb1yfHj8tZ6SK7R`, READY und produktiv zugeordnet.
- Server: `/opt/dashboard-memory-canonical-draft`; private Artefakte unter `.local/cache/hybrid-validation-20260908/`.
- Testledger: `budget.sqlite`. Niemals löschen oder unbekannte Nutzung auf null setzen.
- Wiederherstellbarer Stand vor Rollout: `.local/hybrid-checkpoint-20260908/pre-rollout-code.tgz` und private `pre-rollout-service.env`.
- Veröffentlichung: `reviewed-recovery/payload.json`, `receipt.json`, `publication.json`; Quellen-/Ergebnishashes und Auditentscheidungen verknüpfen den geprüften Test mit dem veröffentlichten Ergebnis. Keine künstlichen Providerbelege angelegt.
- Kostenvergleich: `final-cost-report.json`; Modellantworten bleiben vollständig im privaten Ledger.

## Prompt für spätere gezielte KI-Arbeit

> Lies zuerst diesen Abnahmebericht und den aktuellen Produktionszustand. Verändere akzeptierte Ergebnisse nicht durch stilles Replay. Bewahre Originale, bezahlte Antworten, Suchsnapshots und die gesamte Historie. Keine Projektdimension und keine harten Altersfilter einführen. Für weitere Kostensenkung untersuche zuerst die sehr breite Treffermenge der Zuordnungsstufe und messe deren Tokenanteil kostenlos aus gespeicherten Requests. Verkleinere sie nur mit nachvollziehbarer Absicherung für alte Zusagen, Paraphrasen, unterschiedliche Aufgaben zum selben Thema und fehlende Treffer. Trenne Retrieval-Recall von Interpretationsqualität. Vergleiche neue Varianten zunächst mit gespeicherten Antworten und den acht benannten Minimalfällen; vollständige kostenpflichtige Vergleiche benötigen verbleibendes ausdrücklich autorisiertes Budget. Der bestehende Testdeckel ist fast ausgeschöpft und darf nicht automatisch erhöht werden. Luna darf Terra nicht allein aufgrund der Kosten oder gleicher Aufgabenanzahl ersetzen: prüfe auch fehlendes Wissen, falsche Altbezüge, falsche Zustandswechsel und Nutzer-Nacharbeit. Belege 0/1/2 sind keine Wahrscheinlichkeiten. Ändere die laufende Pipeline nicht während eines bezahlten Jobs. Verifiziere einmal den gesamten Weg über n8n, Originalarchiv, Verarbeitung, Datenbank und Dashboard. Führe passende lokale Tests aus, sichere Code und Daten, und berichte Kosten und Prüfungslücken ausdrücklich.

## Ergänzungen der Betriebsprüfung

Die vollständige Sicherung nach Veröffentlichung wurde zusätzlich erfolgreich exportiert und offline rekonstruiert: Revision 112, Archiv 505, 206 Originale, 299 Zusammenfassungen, 1298 Wissenseinträge, 13333 Suchdokumente, 27 Suchsnapshots und 269 gespeicherte Suchergebnisse. Ablage: `complete-backup-final/`, inklusive `restore-check.json`. Der Snapshot enthält den begonnenen Wiederanlauf zu seinem festen Aufnahmezeitpunkt; spätere automatische Verarbeitungen liegen im fortlaufenden Journal.

Ein regulärer Inbox-Job (`Schichten`) blieb nach vier vollständig gespeicherten Modell-/Embeddingantworten bei einem Transportzugriff stehen. Er wurde am unveränderten Kontext revisionsgebunden über die vorhandene Recovery-Funktion wieder freigegeben. Der Suchclient wiederholt jetzt ausschließlich idempotente Suchoperationen bei temporären Netzwerk-/Serverfehlern bis zu dreimal mit kurzer Wartezeit. Reservierung, Modellaufruf, Veröffentlichung und Benutzerentscheidungen bleiben von dieser Wiederholung ausgeschlossen; Validierungs- und Revisionsfehler ebenfalls. Drei gezielte zusätzliche Tests bestanden. Die genaue externe Ursache des einmaligen Transportfehlers konnte aus dem bisherigen generischen Fehlerprotokoll nicht bestimmt werden.

## Abschließender Betriebsstand

Beim letzten Live-Check: **Revision 116, fünf Inbox-Jobs angewandt, ein Job in Verarbeitung, sechs eingereiht, kein Job im Fehler-/Reviewzustand.** Der unterbrochene Job `Schichten` wurde nach Wiederaufnahme erfolgreich veröffentlicht; seine Zahl bezahlter Aufrufe blieb bei vier. Der Rest läuft auf dem Server selbständig weiter, auch wenn dieser Chat oder der lokale Rechner beendet wird.

Der laufende Produktionszähler lag beim Check bei 6,690179 USD einschließlich der schon vorher entstandenen 6,620629 USD: somit 0,069550 USD neuer Wiederanlaufaufwand einschließlich damals bestehender Reservierungen. Testaufwand plus Wiederanlauf konservativ 9,811530 USD zu diesem Zeitpunkt. Die harte gemeinsame Obergrenze bleibt 12 USD. Dies ist ein Zeitpunktwert, da die restliche Warteschlange weiterarbeitet.

Aktueller tatsächlich ausgerollter Quellstand einschließlich Transportkorrektur: `.local/hybrid-checkpoint-20260908/final-deployed-code.tgz` auf dem Server und gleichnamige lokale Kopie unter `.codex-deploy/hybrid-checkpoint-20260908/`. Keine weiteren kostenpflichtigen Vergleichstests gestartet.
