# Modellwahl: korrigierte Bewertung und Nachweise, 7. September 2026

Die frühere Sonnet-Empfehlung war fachlich nicht hinreichend belegt. Auch die pauschale Formulierung „Es wurden keine bezahlten Vergleichsläufe ausgeführt“ war falsch: Es gab frühere Entwicklungsvergleiche. Bei dieser erneuten Prüfung wurden ausschließlich gespeicherte Antworten gelesen und öffentliche Quellen recherchiert; keine neuen Modellaufrufe.

**Ergebnis:** Terra ist ein ernstzunehmender wirtschaftlicher Kandidat. Opus ist die bisher ausführlicher geprüfte Referenz der vorhandenen Verarbeitung, aber kein nachgewiesener Qualitätssieger. Für einen Vorrang von Sonnet vor Terra gibt es keinen hinreichenden appbezogenen Nachweis. Ein unabhängiger Vergleich der endgültigen v9-Verarbeitung liegt nicht vor.

## Gemeinsamer Ausgangsvergleich

Quelle: [gespeicherte Messwerte](../evaluation/results-v1.json). Finance vom 15. Juli, ein Lauf je Modell, gleicher fachlicher Prompt v1 und Zitatstruktur, vollständiges Original ohne Archivkontext. Keine gemeldeten Thinking-/Reasoning-Tokens. API-Format und Tokenisierung unterscheiden sich.

| Modell | Erzeugte Aussagen | Beanstandete Quellen-/Zeitbelege | Vollständige Ausgabe | Kosten aus Usage |
|---|---:|---:|---|---:|
| Sonnet 5 | 11 | 0 | ja | 0,062620 USD |
| GPT-5.6 Terra | 11 | 2 | ja | 0,050262 USD |
| Opus 5 | nicht auswertbar | nicht auswertbar | nein: 12.000 Ausgabetokens erreicht | 0,354250 USD |

Sonnet bestand die damalige formale Belegprüfung. Das beweist weder korrekte Zusageinterpretation noch vollständige Erkennung. Terra hatte ein nicht originalgetreues Zitat mit falscher Sprecherzuordnung und eine nicht durch Zitat belegte Zeitangabe. Seit v2 setzt der Code Zitate aus referenzierten Originalpassagen ein; der alte Fehlervergleich ist deshalb nicht unverändert auf die aktuelle Verarbeitung übertragbar. Opus scheiterte am damaligen Ausgabelimit: Konfigurations-/Zuverlässigkeitsbefund, keine messbare semantische Niederlage.

Terra war hier **19,7 % günstiger als Sonnet**. Gemeldete Eingabe-/Ausgabetokens: Terra 5.283/3.088, Sonnet 10.850/4.092. API-Format, Ausgabeumfang und Tokenisierung wirken zusammen; keine generell halbierte Tokenisierung nachgewiesen. Kosten sind Usage-basierte Listenpreisrechnungen einschließlich berücksichtigter Cache-Schreibpreise, keine Rechnungsbeträge. Eine Rechnung mit hypothetisch identischen Tokenzahlen reicht nicht zur wirtschaftlichen Modellwahl.

## Erneut geprüfte fachliche Ergebnisse

Der [Belegauszug](../evaluation/model-evidence-reinspection-2026-09-07.json) enthält Lauf-IDs, relevante Arbeitseinträge mit Quellen, Usage und Antwort-Hashes. SQLite wurde schreibgeschützt geöffnet. Die Versionen unterscheiden sich; diese Befunde sind keine faire Rangliste.

| Fall | Rohresultat | Bedeutung |
|---|---|---|
| Terra v4, Umrechnungskurse | dependency, kein Owner, work_state not_applicable | Stimmt mit Glebs Kalibrierung „Voraussetzung; keine neue Zusage“ überein. |
| Terra v4, VO | Keine VO-Aufgabe unter elf Beobachtungen | Keine falsche Zusage in diesem Lauf; kein Vollständigkeitsbeweis. |
| Terra v4, Einladung | Eine Einladung, due_text Montag Mittag | Keine doppelte Einladung; Terminzeitpunkt aber als Fälligkeitsangabe eingesetzt. |
| Sonnet v5, VO | Explizite Zusage, required_review false; unklarer VO-Name zu Sebastian aufgelöst | Widerspricht Nutzerkalibrierung; zusätzliche Handlungsprüfung bestätigte den Fehler. |
| Sonnet v5, Einladung | Termin ansetzen und Einladung verschicken als zwei neue Verpflichtungen ohne Updateziel | Dieselbe Einladung doppelt; beide Einträge vom Handlungsprüfer unterstützt. |
| Sonnet v5, Folgemeeting 20. Juli | Elf Beobachtungen, null gezielte Updates | Der stattgefundene Termin wurde nicht abgeschlossen. Coverage behauptet zudem, die bestehenden Finance-Vorgänge seien nicht erneut thematisiert worden. |
| Opus v4, VO | commitment, explicit, open, required_review false | Ebenfalls falsche Zusage; kein automatischer Schutz durch Opus. |

Lauf-IDs: Sonnet 15. Juli `203d8e438ee74dc2a46f0118d369dc60`; Sonnet 20. Juli `90b78f319f504e76937f3032f08ff011`; Opus 15. Juli `955d5a2a8d6e4964bf8ba37623f5775a`; Terra v4 `resp_05f781be4ff9884a016a9d62ca009487d294a5a14b880590eb`.

Die [frühere Evaluation](EVALUATION.md) dokumentiert weitere Opus-Fälle: erteilten Zugang richtig abgeschlossen, Teams-Erreichbarkeit zunächst fälschlich als Aufgabe und erst vom Handlungsprüfer entfernt. Der Fünferpilot kostete 5,055840 USD für 13 Aufrufe; 16 Verpflichtungsbeobachtungen mit anonymen Sprecherlabels mussten in der anschließenden Projektion als ungeklärt behandelt werden. Menschliche Korrekturen und bestandene Softwaretests sind keine Modelltreffer.

## Externe Evidenz und ihre Grenzen

[Artificial Analysis, 24. Juli](https://artificialanalysis.ai/articles/opus-5) meldet für Opus 5 mit maximalem Reasoning 1.861 Elo bei GDPval-AA v2 und 1.720 Elo bei AA-Briefcase. Das sind professionelle Arbeitsprodukte in einem Agentensystem. Durchschnittlicher Intelligence-Index-Aufwand: Opus 2,03 USD pro Aufgabe, Sonnet 5 mit maximalem Reasoning 1,53 USD. Je nach Reasoning-Stufe ändert sich das Verhältnis. AA unterstützte Anthropic bei der Vorabprüfung; die Indexläufe verwendeten Opus-4.8-Fallback.

Das begründet Opus als leistungsfähige Referenz, beweist jedoch keine höhere Präzision bei deutschen Zusagen oder Statusänderungen. Unsere v1-Läufe hatten keine Reasoning-Tokens. Aktuelle Index-v4.2-Werte dürfen nicht mit Juli-v4.1-Werten vermischt werden.

[GTMBench](https://gtmbench.org/) meldet für Gesprächsauswertung (386 Aufgaben) Opus 85,2, Sonnet 79,3 und Terra 79,6; für CRM-Extraktion (460 Datensätze) 84,4 / 83,1 / 81,5. Die Aufgaben sind relativ nah an Transkriptanalyse und Dublettenprüfung. Sonnet/Terra unterscheiden sich bei Gesprächen nur um 0,3 Punkte, während die Seite ±1,8 Punkte Unsicherheit nennt.

**Nicht als belastbaren Entscheidungsbeweis verwendet:** Trotz Reproduzierbarkeitsbehauptung fand ich auf der geöffneten Seite keinen zugänglichen Aufgaben-/Rohresultatdatensatz oder Gradercode. Veröffentlichung laut Seite 18. Juli, AA-Opus-Bericht 24. Juli; ein etwaiger Vorabzugang ist nicht belegt. Diese Zahlen bleiben unzureichend überprüfte Betreiberangaben.

[ExtractBench](https://github.com/run-llama/ExtractBench/blob/main/README.md) bietet öffentliche Extraktionsmetriken und Datensätze. Eine Kaggle-Suchausgabe zeigte Terra 90,0 und Opus 88,8. Die eigentliche Kaggle-Seite lieferte keinen auslesbaren Inhalt; die geprüfte [Roh-CSV](https://raw.githubusercontent.com/run-llama/ExtractBench/refs/heads/main/leaderboard.csv) enthielt diesen konkreten Modellvergleich nicht. Diese Zahlen werden deshalb ausdrücklich nicht als bestätigter Terra-Sieg verwendet. Unterschiedliche Teststände oder Systeme dürfen nicht gleichgesetzt werden.

## Konsequenz

- **Terra:** Tatsächlich geringere Kosten im gemeinsamen Ausgangslauf und ein gespeicherter Treffer bei der nutzerkalibrierten Voraussetzung. Ausschließen wäre unbegründet. Ein vollständiger gleich konfigurierter Folgemeeting-/Lebenszyklusvergleich fehlt.
- **Opus:** Mehr Entwicklungserfahrung mit der gesamten Verarbeitung und externe Hinweise auf starke anspruchsvolle Wissensarbeit. Das spricht für eine vorläufige Referenz bei hoher Priorität der Fehlervermeidung. Der Aufpreis ist in dieser App bislang nicht durch eine gemessene Senkung falscher oder übersehener Aufgaben gerechtfertigt.
- **Sonnet:** Gute formale v1-Ausgabe und vorhandene Einbindung, aber belegte semantische Fehler, Dubletten und versäumte Fortschreibung. Die Einbindung spart Implementierungsaufwand; sie ist kein Qualitätsbeweis.

Eine behauptete Sonnet-Überlegenheit wird zurückgenommen. Terra bleibt wirtschaftlicher Vergleichskandidat, Opus die bisher weiter geprüfte Referenz. Keine Modellumschaltung, keine neuen kostenpflichtigen Tests.

Für einen abschließenden Nachweis braucht es einen vorher festgelegten identischen Vergleich der finalen Verarbeitung an unabhängig bewerteten neuen Meetingfolgen: berechtigte neue Aufgaben, übersehene Zusagen, falsche Abschlüsse, Dubletten, Personen-/Datumsfehler und Gesamtkosten einschließlich Prüfer/Reparaturen. Die beiden bekannten Nutzerkorrekturen allein sind keine ausreichende Testmenge. Der Altbestand wird dafür nicht erneut durch APIs geschickt.


## Aktualisierung: Terra aktiviert ohne Kostenobergrenze

Nach ausdrücklicher Nutzerfreigabe am 07.09.2026 läuft die produktive Automatik mit GPT-5.6 Terra für neue Meetings ab 08.09.2026, ohne Kostenobergrenze und mit fortlaufender Kostenprotokollierung. Frühere Hinweise auf ausstehende Budgetfreigabe oder 10 USD sind dadurch überholt. Einzelheiten und Prüfungen: [Terra-Implementierung](TERRA-IMPLEMENTATION-2026-09-07.md).
