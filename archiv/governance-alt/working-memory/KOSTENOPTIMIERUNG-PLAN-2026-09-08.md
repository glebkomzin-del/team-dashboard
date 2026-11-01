# Kostenoptimierung: technischer Plan und Abnahme

Stand: 08.09.2026. Plan, noch keine produktive Änderung. Keine neuen bezahlten Läufe für die Erstellung dieses Plans. Ziel: deutlich weniger Kosten bei unveränderten fachlichen Anforderungen; keine behauptete Garantie für unbekannte zukünftige Fälle.

## 1. Geprüfter Iststand

- `hybrid_schema.py`: Neue Beobachtungen haben `subject`, bis zu acht `search_keywords`, zwei Belegstufen und eine Begründung. Die Extraktion erhält das vollständige aktuelle Meeting; Suchanfragen bekommen Originalbelege.
- `memory.py:apply`: Der vollständige Beobachtungsinhalt wird in `observations.data_json` gespeichert; wirksame Aufgabenereignisse behalten ihn ebenfalls. Keine erneute KI-Klassifikation des gesamten Altbestands beim nächsten Meeting.
- `memory.py:overview`: Aufgaben übernehmen gespeicherte Suchmerkmale. Eine spätere wirksame Aktualisierung kann diese ersetzen. Sie sind daher wiederverwendbar, aber nicht unveränderlich.
- `hybrid_index.py:documents`: Gespeicherte Titel, Aussagen, Gegenstände, Keywords und weitere Felder werden zu Suchtexten zusammengesetzt. Ältere Einträge ohne neue Merkmale bleiben über vorhandenen Text und Vektoren suchbar. Es gibt keinen global einheitlichen Dimensionskatalog und keine neue Projektdimension.
- `SearchIndex.prepare`: Die Suchdokumentliste wird pro Meeting aus dem zulässigen historischen Stand neu konstruiert. `persist` prüft vorhandene Dokumente und verwendet Inhalts-Embeddings wieder. Das ist technischer Bestandsaufwand, keine wiederholte KI-Auswertung alter Meetings.
- Pro Suchanfrage werden allgemeine Treffer sowie separat Aufgaben gesucht. Mehrere Trefferarten und Anfragen erzeugen gemeinsam einen großen Kandidatenbestand. Beim langen realen Fall waren es 240 von 381 Aufgaben.
- `hybrid_pipeline.py`: Jeder Zuordnungsblock erhält erneut das vollständige aktuelle Original. Danach folgen separate Aufgabenänderungsprüfungen und eine Abschlussprüfung. Die Blockgrenze begrenzt einzelne Aufrufe, nicht die Summe aller Aufrufe.
- Gespeicherte erfolgreiche Terra-Stufen des langen Falls: 12 Aufrufe, 589.011 Eingabetokens, 1,614567 USD Modellkosten; davon 1,215297 USD für acht Zuordnungsaufrufe. Providerzeiten zusammen 141,6 Sekunden; kein vollständiger End-to-End-Zeitwert.

## 2. Abnahme vor Umsetzung festschreiben

Referenz sind Originale und ausdrücklich begründete Erwartungen, nicht automatisch sämtliche bisherigen Terra-Ausgaben. Fachliche Fehler des bisherigen Ergebnisses werden dokumentiert und dürfen nicht zur neuen Sollregel werden.

- Preisziel: höchstens 30 % der bisherigen Modellkosten beim identischen langen Meeting, also höchstens 0,484370 USD. Embeddings, Reparaturen und etwaige zusätzliche Sortiermodelle separat ausweisen und in den Gesamtvergleich einschließen. Kein garantierter Preis für jedes beliebige Meeting.
- Qualität: keine zusätzliche fehlende Verpflichtung, falsche Zustandsänderung, falsche Zusammenlegung oder falsche Zuständigkeit in der Abnahmestichprobe. Alle vorab markierten relevanten Alteinträge müssen in der Kandidatenauswahl enthalten sein.
- Wissen: Fakten, Entscheidungen, Ideen sowie vorhandene weitere Wissensarten und Zusammenfassungen mitprüfen. Gleiche Anzahl neuer Aufgaben beweist keine gleiche Qualität.
- Nacharbeit: Zahl und Gründe der Prüfpflichten pro vergleichbarem Sachverhalt dürfen nicht steigen, um scheinbare Genauigkeit durch mehr manuelle Arbeit zu erzielen.
- Laufzeit: Erkennung, Warteschlange, Suche, einzelne Modellaufrufe und Veröffentlichung getrennt messen. Vergleichbare alte Laufzeiten von 20–30 Sekunden erst nach belegbarem Messvergleich bewerten. Kein Versprechen aus Tokenzahlen ableiten.
- Erst bei bestandenem Qualitäts- UND Kostenvergleich ausrollen. Andernfalls verbleibende Ursache offen berichten.

## 3. Kostenloser Engpassnachweis

Gespeicherte Requests des langen und kürzeren echten Meetings lokal auswerten. Pro Stufe Umfang von Regeln, Schema, aktuellem Original, Kandidaten, wiederholten historischen Passagen und Ausgabe messen. Exakte Tokenzählung nur mit passendem vorhandenem Tokenizer, sonst Zeichenmengen ausdrücklich als Näherung kennzeichnen.

Je Suchanfrage protokollieren: Trefferarten, eindeutige Ziel-IDs, mehrere Abschnitte desselben Ziels, gleichartige Suchanfragen, Rang des tatsächlich benötigten Ziels. Vorab begründete Gold-Ziele anhand der Originale markieren. Daraus Kandidatenverdichtung und Promptänderung getrennt ableiten. Keine kostenpflichtige Modellausführung für diese Diagnose.

## 4. Suchmerkmale einmal erzeugen und weiterverwenden

Bestehende `subject`, `search_keywords`, Thema, Art, Zuständigkeit, Bedingungen und Originalverweise weiterverwenden. Zusätzliche strukturierte Merkmale nur bei nachweislichem Nutzen: konkretes Objekt/Ergebnis und Handlung; aus derselben ersten Extraktion, mit Originalbezug, nullable statt geraten. Keine Projektableitung.

Suchprofil versionieren: Item-ID, Inhaltsversion, Profilversion, Originalverweise und normalisierte Merkmale. Groß-/Kleinschreibung, Schreibvarianten und bestätigte Namensaliasse deterministisch normalisieren. Synonyme helfen der Suche, ändern keine Fakten.

Aktualisierung nur für neue/geänderte Items. Bei einer Statusmeldung ursprünglichen Gegenstand und bestehende hilfreiche Suchbegriffe nicht blind durch die Formulierung der Statusmeldung ersetzen. Neue bestätigte Begriffe nachvollziehbar ergänzen; veraltete oder korrigierte Angaben mit Historie ersetzen. Menschliche Korrektur schlägt die frühere KI-Interpretation.

Altbestand ohne neue Felder bleibt über bestehenden Text erreichbar. Kein pauschaler kostenpflichtiger Backfill. Falls ein fehlendes Profil einen nachgewiesenen Suchfehler verursacht, gezielt nur betroffene Items ergänzen und Budget dafür zählen.

## 5. Breite Suche, kompakte Übergabe

1. Aktuelles Meeting vollständig extrahieren. Suchhinweise auch für Statusaussagen ohne neue Aufgabe erzeugen.
2. Exakt gleiche normalisierte Suchanfragen wiederverwenden. Ähnliche, aber unterschiedliche Handlungen nicht allein wegen Wortähnlichkeit zusammenlegen.
3. Bestehende lexikalische und semantische Suche beibehalten. Keywords sind ein zusätzlicher Suchweg, kein zwingendes gemeinsames Wort. Alter, Thema und Person sind keine harten Ausschlussfilter.
4. Treffer derselben Item-/Quellenversion zusammenführen. Rangsignale und Belegverweise behalten; verschiedene Versionen und widersprechende Aussagen nicht verwechseln. Zusammenfassung, Wissenseintrag und Original können dasselbe Ziel mehrfach repräsentieren.
5. Ohne zusätzlichen LLM-Aufruf nach konkretem Gegenstand, Handlungsbezug, exakten Verweisen und bestehenden Suchrängen sortieren. Gemeinsame Person oder allgemeines Thema allein reichen nicht. Gewichte und Schwellen anhand separater Kalibrierfälle bestimmen, danach für Abnahme einfrieren.
6. Zuerst kompakte Kandidatenkarten übergeben: ID, ursprüngliche Aufgabe/Aussage, Gegenstand, relevante Merkmale, Status, Bedingungen und Originalverweise. Historische Volltexte nur bei benötigter Beweisprüfung öffnen. Keine neue KI-Zusammenfassung jedes Altitems für jedes Meeting.
7. Keine ungeprüfte feste Top-5-Kappung. Bei knappem Rangabstand, explizitem Altbezug ohne Treffer, fehlendem Handlungsbezug oder widersprüchlichen Kandidaten gezielt erweitern. Ein breiteres Fallback darf Ausnahme bleiben; Häufigkeit und Kosten messen.
8. Retrieval-Score nicht als Confidence ausgeben. Er sortiert Suchergebnisse; erst Originalbelege rechtfertigen Änderungen.

Wenn die vorhandenen Ränge keine sichere Verdichtung erlauben, nicht unbemerkt abschneiden. Ein zusätzliches Reranking-Modell wäre dann eine separat zu bewertende Alternative mit eigenen Kosten und Tests, keine vorab unterstellte Lösung.

## 6. Weniger doppelte Modellarbeit

Erste sichere Optimierung: kompakte Kandidatenkarten und wiederholte Belege entfernen, während bisherige Prüfverträge zunächst erhalten bleiben. Deren Token-/Kostenpotenzial vor riskanteren Eingriffen bestimmen.

Danach Zuordnung und Änderungserkennung auf denselben passenden Kandidaten in einem strukturierten Antwortvertrag zusammenführen. Jede extrahierte Beobachtung sowie jeder belegte Statushinweis bekommt ein überprüfbares Ergebnis; keine separate Vollprüfung sämtlicher grob ähnlicher Aufgaben auf `unchanged`.

Für Zuordnungsgruppen aktuelle Originalstellen samt Sprecherwechseln, notwendigen Nachbarstellen und verknüpften Voraussetzungen bereitstellen. Pronomen, Negationen, zeitliche Einschränkungen und spätere Korrekturen im Meeting erhalten. Wenn die Auflösung unsicher ist, gezielt Kontext erweitern bis hin zum vollständigen aktuellen Original. Eine generierte Zusammenfassung ersetzt nie den Beleg.

Zunächst die unabhängige Abschlussprüfung für Verpflichtungen und Änderungen mit vollständigem aktuellem Original erhalten. Historische Originalbelege der betroffenen Aufgaben werden zusätzlich geöffnet. Erst reduzieren, wenn ein getrennter Vergleich die Qualität belegt; kein gleichzeitiger Umbau sämtlicher Schutzstufen.

IDs, gültige Zustandsübergänge, Belegpositionen, Dublettenfreiheit und Aufgabenidentität deterministisch validieren. Eine erfüllte Voraussetzung schließt keine Gesamtaufgabe. Keine neue Verpflichtung aus einer unklaren alten Referenz raten.

Terra bleibt im ersten Vergleich konstant. Luna später nur für klar abgegrenzte Stufen prüfen; dieselben Qualitäts- und Nacharbeitskriterien anwenden. Modellwechsel und Kontextkürzung nicht gleichzeitig testen, weil sonst die Fehlerursache unklar bleibt.

## 7. Indexarbeit nur bei Änderungen

Nach der Prompt-/Trefferoptimierung gesondert prüfen, welchen Laufzeitanteil die technische Bestandsrekonstruktion hat. Falls relevant: persistente Suchprofile und revisionsgebundene Mitgliedschaften inkrementell aktualisieren statt immer sämtliche Dokumente zu konstruieren und auf Existenz zu prüfen.

Historische Ansichten müssen Ereigniszeit, Beobachtungszeit, Korrekturen und Quellversionen unverändert berücksichtigen. Gleicher Inhalt verwendet vorhandene Embeddings; geänderte Suchtexte benötigen passende neue Vektoren. Modell-/Profilversionen dürfen nicht unbemerkt gemischt werden. Historische Rekonstruktion bleibt prüfbarer Referenzweg.

## 8. Kleine, gezielte Testmatrix

Die acht bestehenden fachlichen Fälle weiterverwenden; Zusatzfälle überwiegend ohne Modellkosten als Such-/Speicher-/Vertragstests. Gold-Erwartungen vor Ausführung fixieren. Wenige zusätzliche, bisher nicht zum Einstellen verwendete Formulierungen als zurückgehaltene Abnahmefälle nutzen.

| Fall | Erwartung / zu verhindernder Fehler |
|---|---|
| Klare neue Zusage; reine Tatsache | Richtige Aufgabe bzw. keine erfundene Aufgabe; Wissen erhalten |
| Idee mit Voraussetzung; Termin ohne Versandzusage | Keine erfundene Verpflichtung oder Deadline |
| Erledigung als Paraphrase ohne gemeinsame Keywords | Richtige frühere Aufgabe semantisch gefunden und korrekt geändert |
| Sehr alte relevante Zusage | Trotz Alter und vieler neuer Ablenkungstreffer enthalten |
| Gleiches Thema, andere Handlung/anderer Bericht | Keine Zusammenlegung oder falsche Erledigung |
| Nur eine von zwei Freigaben | Gesamtaufgabe bleibt offen/bedingt |
| „Das ist fertig“, Bezug einige Sprecherwechsel vorher | Notwendiger Kontext geöffnet; keine geratene Zuordnung |
| Negation oder spätere Korrektur im selben Meeting | Widerspruch berücksichtigt; kein voreiliger Abschluss |
| Neue/geänderte Person, Datum, Status oder Bedingung | Nur belegtes Attribut ändern; ursprünglicher Suchgegenstand erhalten |
| Unbekanntes Altprofil und Nutzerkorrektur | Altbestand bleibt auffindbar; Korrektur wird wiederverwendet, keine globale Regel erfunden |
| Mehrfachtreffer aus Original/Summary/Item | Ein Kandidat pro Zielversion; widersprüchliche Versionen bleiben erkennbar |
| Leere Suche mit ausdrücklichem Altbezug | Gezielte Erweiterung oder begründete Prüfung, keine neue Dublettenaufgabe |

Technische Tests: unveränderter Bestand löst keine neue Profilgenerierung/Embeddingrechnung aus; geändertes Item aktualisiert nur betroffene Suchtexte; Revision und historische Zeitgrenzen stimmen, einschließlich gleichdatierter Meetings; vollständige Originalabdeckung und stabile Belegpositionen; Retry verwendet bezahlte Antwort nur bei identischem Request/Kontext; Budgetabbruch veröffentlicht kein ungeprüftes Ergebnis.

Skalierung kostenlos testen: gespeicherte fachliche Fälle mit zunehmend vielen thematisch ähnlichen, aber falschen Kandidaten kombinieren. Gold-Ziele müssen erhalten bleiben. Übergabetokens, Trefferzahl und Fallbackrate messen; daraus keine bezahlte Modellqualität ableiten.

## 9. Kostenkontrolle der Validierung

Bestehende Gold-Originale, bezahlte Antworten und Suchsnapshots unverändert wiederverwenden. Replay mit alten Antworten prüft Speicher-/Vertragslogik, beweist aber NICHT die Qualität eines geänderten Prompts.

Vor neuen API-Aufrufen alle bisherigen Tests, Reservierungen und Wiederanlaufkosten konsolidieren. Die Nutzerobergrenze von 15 EUR bleibt für den bisherigen Gesamtauftrag bestehen; vorhandene strengere technische Deckel nicht still erhöhen. Ungeklärte Nutzung weiter reservieren. Weder eine neue Testserie noch Luna automatisch mit frischem Budget starten.

Bezahlte Reihenfolge, nur innerhalb nachgewiesener Reserve: wenige gebündelte fachliche Abnahmefälle; bei Erfolg ein langer realer Vergleich mit wiederverwendeter Extraktion, soweit unverändert. Kürzeren realen Fall zunächst für kostenlose Kandidaten-/Promptprüfung verwenden; ein zweiter voller Modelllauf nur bei ungelöster Abnahmefrage und verfügbarem Budget. Reicht die Reserve nicht, kostenfreien Befund fertigstellen und die konkret fehlende Validierung ausweisen, keine Scheinergebnisse melden.

## 10. Eingang und Veröffentlichung als eigener Umbau

Gewünschter Ablauf: Eingangssignal -> versionsgeprüft einreihen -> chronologisch verarbeiten -> dauerhaft veröffentlichen -> dieselbe unveränderte Quelldatei nach Processed verschieben. Nicht bereits nach dem Einreihen verschieben.

Vor der Umsetzung feststellen, ob der Erzeuger des Transkripts direkt einen Webhook senden kann; andernfalls echten Drive-Änderungskanal mit Erneuerung und Ordnerprüfung planen. Ein als Trigger benannter Poller ist kein sofortiger Hook. Authentifizierung, doppelte/verspätete Signale und eine sparsame Nachholung verpasster Ereignisse berücksichtigen.

Mit Fixtures prüfen: zehn gleichzeitige Eingänge, doppelte Meldung, noch unvollständiger Upload, geänderte Version während Verarbeitung, Ausfall nach Veröffentlichung/vor Verschieben und fehlgeschlagener Move. Keine zweite KI-Rechnung bei erneutem Move; Fehlerdateien bleiben in Inbox und Fehlerstatus bleibt sichtbar. Danach ein echter vollständiger Weg, nur soweit Budget vorhanden.

## 11. Umsetzung und Rollout

Reihenfolge: Diagnose und Goldfälle -> Suchprofile/Kandidatenverdichtung -> Tokenmessung -> passende lokale Tests -> begrenzter echter Qualitätsvergleich -> gegebenenfalls Zusammenführung der Modellstufen mit erneuter gezielter Abnahme -> separater Eingang/Move -> Rollout an ruhender Warteschlange.

Neue Pipeline versionieren; alte Antworten, Quellen, Rückmeldungen und Suchsnapshots erhalten. Kein stilles Replay bereits veröffentlichter Meetings. Pro Ergebnis Kosten, Suchumfang, Kontext-Erweiterung, Prüfpflichten und Laufzeiten speichern. Ergebnisbericht enthält Zielerreichung oder Abweichung sowie konkrete nicht geprüfte Risiken. Erst dieser Bericht begründet den Abschluss der Kostenoptimierung.
