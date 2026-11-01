# Fachliches Ziel und Freigaberegeln

Das Dashboard beantwortet zuerst: Was hat sich geändert, was muss Gleb tun, und worauf wartet er? Meetings sind Quellen, keine Container voller neu angelegter Arbeit.

## Datenmodell

- **Quelle und Version:** stabile Drive-ID, unveränderlicher Inhalt, Hash, Ereigniszeit, getrennte Kenntnisnahmezeit. Korrigierte Quellen ersetzen die Historie nicht.
- **Beobachtung:** belegte Aussage mit Originalpassagen, Sprecher, Zeitpunkt und Einordnung. Voraussetzung, Idee, Risiko und Entscheidungsbedarf bleiben Wissen.
- **Vorgang:** bestimmtes Vorhaben/Ergebnis in einem Projekt oder Arbeitsbereich; zum Beispiel „Bedarf und Weg für Vorjahresreporting klären“. Ein Projekt kann viele Vorgänge enthalten. Ähnliche Namen allein reichen nicht zur Zusammenführung.
- **Verpflichtung:** konkret übernommene Handlung oder zugesagtes Ergebnis, Verantwortlicher, gegebenenfalls belegte Frist. Eigene Arbeit, fremde Zusagen und Kalenderabsprachen getrennt darstellen.
- **Änderungsereignis:** neue Erkenntnis, Fortschritt, geänderte Zuständigkeit/Frist, Abschluss oder Wiederaufnahme. Änderungen referenzieren bestehende IDs und erhalten vorherige Zustände.

## Automatik

Neue Arbeit nur bei ausdrücklicher Zusage oder angenommener Bitte, identifizierbarem Verantwortlichen und tragfähigem Originalbeleg. Keine Aufgabe aus „ich brauche“, „sobald“, „wir könnten“ oder einer fremden Erwartung allein. Keine starre Aufgabenobergrenze. Wiederholungen aktualisieren die vorhandene Verpflichtung.

Automatische Statusänderung nur mit sicherem Bezug auf die bestehende Verpflichtung. Eine nächste Besprechung beweist nicht automatisch, dass alle Vorbereitungsaufgaben erledigt wurden. Unklare Verantwortliche werden nicht aus Fachgebiet oder Meetingteilnahme geraten. Eine mögliche Frist bleibt eine mögliche Frist; „nächste Woche“ wird nicht zu Sonntag.

Nur handlungsrelevante Unsicherheit mit Konsequenz für eine aktuelle Verpflichtung erfordert eine knappe Entscheidung. Sonstige Unsicherheit bleibt direkt am Vorgang mit Originalpassage sichtbar. Technische Verarbeitungsfehler erscheinen im Betriebsstatus, nicht als persönliche Inbox-Aufgaben. Abgelehnte Vorschläge und verworfene Alternativen bleiben nachvollziehbar.

## Kontext

1. Vollständige Originalquelle in referenzierbaren Sprecherpassagen erfassen. Keine unmarkierte Abschneidung.
2. Zum Ereigniszeitpunkt vorhandene Vorgangstitel/IDs, offene Verpflichtungen und relevante belegte Änderungen bereitstellen. Spätere Quellen sind ausgeschlossen. Historische Wissensstand-Replays benötigen zusätzlich eine Kenntnisnahme-Grenze.
3. Neue Aussagen erst gegen diesen Stand abgleichen. Zusammenfassungen dienen der Navigation; die Beweiskette endet im Original.
4. Validierung prüft IDs, Originalbelege, Datumsbezug und zulässige Änderungen unabhängig vom Modell. Strukturierte Ausgabe allein beweist keine fachliche Richtigkeit.

Der Prototyp verarbeitet die ausgewählten Quellen vollständig und setzt einen expliziten Gesamtgrenzwert von 140.000 Zeichen für Prompt inklusive Kontext. Das ist eine technische Schutzgrenze, kein bereits qualitätsoptimiertes Tokenbudget. Überschreitung stoppt nachvollziehbar statt Inhalte zu verlieren. Für größere Archive benötigt die Produktionsfassung einen vollständigen Vorgangskatalog, gezieltes Retrieval und kontrolliertes Nachladen. Relevanz-Recall, tatsächliche Tokens und Zusatzkosten müssen vor einer Reduktion gemessen werden.

## Abnahme vor produktiver Umschaltung

Die aktuelle Entwicklungsstichprobe ist kein unabhängiger Testsatz. Vor Freigabe: separate vollständig fachlich geprüfte Meetingfolgen; keine kritische Zusage übersehen, keine unbelegte Zuständigkeit/Frist, keine falsche Zusammenführung und kein falscher Abschluss. Ziel für neue Aufgaben: mindestens 95 % fachlich berechtigt, mit ausgewiesener Fallzahl und Unsicherheit. Dieser Prozentwert ist bei wenigen Beispielen nicht belastbar nachweisbar.

Zusätzlich: lückenlose Quellenzuordnung, vollständige Eingangsabdeckung, nachvollziehbare Kosten einschließlich Fehlversuchen, wiederholte Imports ohne zusätzliche Arbeit, Parallel- und Absturztests, erfolgreich geprobter Restore. Migration des Rückstaus zunächst als Vorschau mit erhaltenen IDs; keine Massenlöschung oder pauschaler Abschluss.
