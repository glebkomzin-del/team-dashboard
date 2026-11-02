## Aktueller Stand 7. September 2026 — manuelle Migration und technische Abnahme

Der unten historisch beschriebene kostenpflichtige Gesamtimport wurde vom Nutzer ausdrücklich verworfen. Er wird nicht ausgeführt. Stattdessen wurden **alle 1.306 vorhandenen Altitems aus 106 Quellen vollständig am Original manuell geprüft**, einschließlich der beiden Nutzerkalibrierungen. Ein frischer vollständiger Zeilenhash-Abgleich mit Supabase bestätigt unveränderte Ausgangsdaten. Die abschließenden 42 Arbeitskorrekturen sind als separater Vorschlag auf Revision106 gespeichert; keine automatische produktive Übernahme. Nachweis: `evaluation/legacy-final-review-result.json` und privates unveränderliches Reviewledger.

**210 automatisierte Prüfungen bestanden** (10,890 Sekunden). Dies sind Regel-, Integritäts-, Betriebs- und Zugriffstests. Sie belegen keine allgemeine Modellgenauigkeit. Hinzu kommen durchgeführte Browserfälle für Anmeldung, Ablauf einer Sitzung, Fehlerrückmeldung, Warteschlangen-Wiederaufnahme, Quellenkorrektur, Bedingungen, persönliche Entscheidungen, Themenzuordnung und explizite Chronologiekorrektur. Der letzte Fall prüft eine verlorene Bestätigung nach bereits gespeichertem Vorgang: erneuter Versuch ergibt exakt eine Entscheidung und eine neue Revision, null Modellaufrufe.

Die aktuellen fachlichen Regeln sind v9. Ein vollständiges neues Original bleibt vollständig im Extraktionsinput. Historische Originalpassagen und Wissensaussagen werden begrenzt ausgewählt; alle vorhandenen Arbeitsidentitäten bleiben im Kontext. Zu große Kataloge führen zu einem sichtbaren Halt, nicht zu stiller Kürzung. Jeder bestehende noch nicht aktualisierte Arbeitsauftrag wird in der gesonderten Lebenszyklusprüfung berücksichtigt. Nicht-Erwähnung ist kein Abschluss. Gleichnamige Themen werden nicht automatisch gleichgesetzt, ungeordnete Gespräche desselben Tages liefern keine erfundene Vorgeschichte.

Die manuell überprüften Realfolgen belegen unter anderem ausdrücklich angenommene Aufträge, bloße Möglichkeiten, Voraussetzungen, mehrere UND-Bedingungen, belegtes Ende einer Wartebedingung, Terminänderungen, getrennte Empfänger in Sammelitems und tatsächlich ausgeführte Teilaufträge. Diese Korrekturen sind Aussagen des direkten Reviews; sie dürfen nicht als Modelltreffer oder unabhängige Präzisions-/Recallquote gezählt werden. Der Originalbestand wurde dabei nicht durch Modell-APIs geschickt.

Für zukünftige automatische Meetings bleibt Opus mit Handlungs- und Lebenszyklusprüfung die aus den bisherigen Entwicklungsproben gewählte Referenz. Die Budgetgrenze und Startdatumssperre sind dauerhaft gespeichert; alte oder geänderte Originale werden nicht automatisch kostenpflichtig erneut verarbeitet. Unbekannte Kosten bleiben reserviert; gespeicherte Antworten werden bei Neustart ohne Wiederholung des Modellaufrufs genutzt. Ein ungeklärter bereits bezahlter Aufruf wird nicht blind erneut ausgeführt.

**Grenzen:** Die verfügbare Modellstichprobe ist klein und wurde zur Entwicklung benutzt. Eine unabhängige 95-Prozent-Quote oder null Auslassungen in beliebigen künftigen Meetings sind nicht nachgewiesen. Unter dem ausdrücklichen Verbot weiterer Modellaufrufe für Altbestand wird dieser Nachweis nicht durch einen weiteren historischen API-Durchlauf erzwungen. Die automatische Verarbeitung ist bis zur finalen Freigabe pausiert. Die folgenden älteren Zwischenstände sind historische Entwicklungsnotizen, keine aktuellen offenen Importaufträge.

---

# Fachliche Evaluation und Modellauswahl – 6. September 2026

## Empfehlung und Grenze des Nachweises

Der größte zuverlässige Gewinn kommt aus Quellen-IDs, unveränderlichen Originalen, getrenntem Wissen/Arbeit, chronologischem Kontext und verbindlichen Nutzerkorrekturen. Ein stärkeres Modell allein löst das Problem nicht. Für die nächste isolierte Evaluationsrunde bleibt Opus 5 mit zusätzlicher Handlungsprüfung die Referenz; Sonnet 5 ist der günstigere Vergleichskandidat. Eine produktive Modellentscheidung ist noch nicht abgesichert. Mehrere zusätzliche Anbieter oder ein automatischer Modellrouter sind durch diese Stichprobe nicht gerechtfertigt.

Die API-Verfügbarkeit wurde mit den bestehenden Konten geprüft. Anthropic-Modellliste und tatsächliche Inferenzaufrufe enthielten die unten genannten Modelle. OpenAI wurde über den bereits in Supabase vorhandenen API-Schlüssel getestet; dieser wurde nicht exportiert. ChatGPT-Abonnements decken diese API-Aufrufe nicht ab. Quellen: [OpenAI-Modelle](https://developers.openai.com/api/docs/models), [OpenAI-Preise](https://developers.openai.com/api/docs/pricing), [Claude-Modelle](https://platform.claude.com/docs/en/models/overview), [Claude-Preise](https://platform.claude.com/docs/en/about-claude/pricing). Preise/Verfügbarkeit sind eine Momentaufnahme vom 6. September.

## Gemeinsamer Ausgangsvergleich

Ein vollständiges Originalmeeting vom 15. Juli, derselbe fachliche Prompt v1 und dieselbe Zitatstruktur, ohne Archivkontext, ein Lauf je Modell. Unterschiedliche Tokenzahlen ergeben sich auch aus Tokenisierung und API-Format. Dies ist ein technischer und qualitativer Einzelvergleich, keine Modellrangliste. Die alten Make-Einträge dienen als beobachtete Ausgangslage; der alte Workflow wurde nicht erneut produktiv ausgeführt.

| Modell | Ungültige Belege/Aussagen | Vollständiges JSON | Kosten aus Usage, USD | Laufzeit |
|---|---:|---|---:|---:|
| Haiku 4.5 | 8/20 | ja | 0,034682 | 76,7 s |
| Sonnet 4.6 | 16/16 | ja | 0,110304 | 113,0 s |
| Sonnet 5 | 0/11 | ja | 0,062620 | 42,0 s |
| Opus 5 | nicht auswertbar | nein, Ausgabelimit | 0,354250 | 131,0 s |
| GPT-5.6 Luna | 6/12 | ja | 0,004072 | nicht instrumentiert |
| GPT-5.6 Terra | 2/11 | ja | 0,050262 | nicht instrumentiert |
| GPT-6 Astra | 2/26 | ja | 0,462880 | nicht instrumentiert |

„Ungültig“ umfasst nicht buchstabengetreue Zitate, vertauschte Sprecher/Zeitmarken und nicht belegte Zeitangaben. Bei Sonnet 4.6 scheiterten bereits die umformatierten Sprecher-/Zeitpräfixe. Das bedeutet **nicht**, dass alle Aussagen fachlich falsch waren. Umgekehrt beweist ein wörtliches Zitat keine richtige Interpretation. Die vollständigen Messwerte stehen in `evaluation/results-v1.json`.

## Verbesserte Verarbeitung und echte Folgen

Ab v2 referenziert das Modell Originalpassagen über IDs; der Code setzt die Zitate ein. V3 trennt Unsicherheit über die Existenz einer Verpflichtung von Unsicherheit über deren Rahmenbedingungen. V4 unterscheidet offene, wartende und bereits im Meeting erledigte Arbeit. Streaming verhindert lange stille HTTP-Wartezeiten; unvollständige Antworten werden niemals als leeres erfolgreiches Ergebnis übernommen. Ein technischer Reparaturversuch ist begrenzt und wird mitgerechnet.

- **Finance 15./20. Juli:** Opus v4 erkannte die Einladung, Caroline/Marc und Olivers schriftliche Ergänzung. Es akzeptierte aber auch das VO-Gespräch als neue Zusage. Selbst die zusätzliche, eng auf Handlungen fokussierte Modellprüfung bestätigte diesen Fehler. Gleb korrigierte ihn ausdrücklich zur bloßen Möglichkeit. Diese Nutzerentscheidung steht nun über jedem Modellurteil, gebunden an den Hash und die genaue Originalaussage.
- **Umrechnungskurse:** Gleb bestätigte die Voraussetzung ohne neue eigene Zusage. Sie bleibt als Wissen erhalten. Eine pauschale Regel „sobald = keine Aufgabe“ wäre falsch: Im Juni sagt Jan ausdrücklich eine Aktualisierung und einen Wertevergleich zu, sobald Daniela fertig ist.
- **Finance am 20. Juli:** Die korrigierte Testprojektion zeigt zwei offene fremde Zusagen und einen erledigten Abstimmungstermin, keine neue persönliche Aufgabe. Die eigentliche Migrationsentscheidung ist weiterhin offen. Die Terminerfüllung ist eine quellengeprüfte Schlussfolgerung aus der tatsächlich abgehaltenen thematisch passenden Besprechung, keine zusätzliche Nutzerbestätigung.
- **75-Minuten-Meeting vom 16. Juni:** Alle 69.700 Zeichen wurden verarbeitet, einschließlich später Zusagen jenseits des alten 12.000-Zeichen-Ausschnitts. Sonnet v2 erzeugte unter anderem eine Aufgabe aus einer Lizenzmöglichkeit und hielt den bereits erteilten Workspace-Zugang offen. Opus v4 erkannte den erteilten Zugang als erledigt, machte aber Glebs bloße Teams-Erreichbarkeit noch zur Aufgabe. Die zusätzliche Prüfung verwarf diese Aufgabe. Die korrigierte Projektion enthält drei offene fremde Zusagen, einen erledigten Zugang und keine persönliche Aufgabe. Vollständiger Input ist noch kein Nachweis vollständiger Erkennung aller Zusagen.
- **Kurzes Meeting am 16. Juli:** Sonnet v2 erzeugte keine neue Arbeit. Eine einzelne solche Probe belegt noch keine allgemeine Zuverlässigkeit bei Meetings ohne Aufgaben.
- **23. Juni:** Der erste Opus-Versuch lief ohne Usage-Rückmeldung in einen Timeout. Streaming plus einmalige technische Reparatur ergab eine auswertbare Projektion; die echte bedingte Jan-Zusage blieb erhalten. Dieser Fall wurde zur Entwicklung benutzt und ist kein unabhängiger Test.

Die beiden Nutzerkorrekturen sind rückblickende Quelleninterpretationen vom 6. September. Sie ergänzen keine Fakten aus späteren Meetings. Andere fachliche Labels sind als `assistant_original_review` markiert. Der beschädigte Mathias-/Sieglinde-Grenzfall bleibt unbestätigt.

## Kosten der tatsächlichen Verarbeitung

Standardpreise je Million Eingabe-/Ausgabetokens: Opus 5: 5/25 USD; Sonnet 5: 2/10; Sonnet 4.6: 3/15; Haiku 4.5: 1/5. OpenAI Astra: 10/50; Terra: 2/12; Luna: 0,2/1,2. Für die gemeldeten OpenAI-Cache-Schreibvorgänge ist der separate Schreibpreis eingerechnet. Es handelt sich um berechnete Listenpreise aus tatsächlicher Usage, nicht um Rechnungsbeträge.

| Durchlauf | Extraktion + zusätzliche Prüfung | Gemessene API-Zeit beider Schritte |
|---|---:|---:|
| Finance 15. Juli, v4 | 0,368315 USD | 92,398 s |
| Finance 20. Juli, v4, mit vorherigem Stand | 0,561230 USD | 107,460 s |
| Jan/Gleb 16. Juni, v4, vollständiges langes Original | 0,929135 USD | 178,353 s |
| Jan/Gleb 23. Juni, v3, zwei bekannte Versuche | 0,710835 USD **plus unbekannter Timeout-Aufwand** | 283,028 s plus 180,083 s Timeout |
| n8n-Test 18. Juni, alle drei Versuche | 0,316295 USD | 242,950 s |

Die Zusatzprüfung kostet hier etwa 7–15 Sekunden und 0,09–0,30 USD. Sie verbessert einzelne Fehler, ist aber kein unabhängiges Wahrheitsmodell und kann ausgelassene Verpflichtungen nicht nachträglich finden. Ihre Kosten müssen immer mit der ursprünglichen Extraktion addiert werden; die getrennten Replay-Datenbanken enthalten nicht nochmals deren API-Kosten.

Der lokale Versuchsnachweis umfasst 30 API-Aufrufe: **6,809312 USD bekannte Kosten und zwei Aufrufe mit unbekannten Kosten**. Hinzu kommen 0,316295 USD für den Server-Test, zusammen **7,125607 USD bekannte Kosten plus zwei nicht bezifferbare Fehlversuche**. Deterministisches Wiederaufbauen und Importwiederholungen verursachten keine neuen KI-Kosten. Reproduzierbar mit `python evaluation/measure_saved.py`; Details in `evaluation/results-saved.json`. Make-Operationen, Infrastruktur und menschliche Prüfzeit sind darin nicht bepreist.

## Was wirklich gemessen ist

35 automatisierte Python-Tests prüfen u.a. atomare Übernahme, Parallelzugriffe, abgelaufene Leases, doppelte Imports auch nach Codewechsel, Reparaturgrenze, Kostenprotokoll, Quellenbelege, bedingte/wartende Arbeit, bereits erledigte Arbeit und Vorrang der Nutzerkorrekturen. Hinzu kommen fünf zuvor bestandene Deno-Tests des isolierten OpenAI-Testzugangs. Sie sind Infrastrukturtests, keine 40 fachlichen Goldfälle.

Sieben gespeicherte Regressionen bestehen: zwei nutzerbestätigte negative Grenzfälle, vier fachlich am Original bewertete Status-/Aufgabenfälle und ein zeitlicher Quellenfilter. Diese Prüfungen wurden nach Entwicklung am selben Material erstellt. Es wäre falsch, daraus 100 % Präzision oder Recall abzuleiten.

| Geforderte Qualitätsdimension | Nachweisstand |
|---|---|
| Berechtigung neuer Aufgaben | Zwei Nutzerkorrekturen und ausgewiesene positive/negative Entwicklungsfälle; keine belastbare Gesamtquote |
| Übersehene relevante/kritische Zusagen | Volltext statt Ausschnitt getestet; vollständiger Recall noch nicht fachlich gelabelt |
| Updates/Abschlüsse | Finance-Terminerfüllung und im Meeting erteilter Zugang geprüft; Wiederaufnahme/Frist-/Ownerwechsel nur technische Verträge, noch keine unabhängigen Realfolgen |
| Projekt-/Vorgangszuordnung | Finance-Folge über bestehende IDs verbunden; ähnliche Projekte nicht ausreichend getestet |
| Belege/Fristen | Exakte Quellen- und Zeittextprüfung; semantisch falsches, aber wörtlich belegtes Datum weiterhin möglich |
| Dubletten/falsche Zusammenführung | Identischer Import technisch verhindert; paraphrasierte Zusagen über große Archive noch nicht ausreichend evaluiert |
| Persönlicher Prüfaufwand | Zwei geklärte fachliche Rückfragen, eine offene; keine gemessenen Minuten je Woche |
| Fehler/Parallelität/Neustart | Automatisierte Tests plus echter n8n-Wiederholungs- und Container-Neustarttest |

Vor Produktion fehlen getrennte, vollständig geprüfte Realfolgen für geänderte Fristen und Zuständigkeiten, Wiederaufnahme, konkurrierende ähnliche Projekte sowie eine unabhängige Wiederholung aller kritischen Fälle. Die angestrebten ≥95 % berechtigten neuen Aufgaben und null kritischen Auslassungen sind **Abnahmekriterien, noch kein Ergebnis**.


## Fortschreibung und React-Anschluss, 6. September

Der lokale Teststand umfasst jetzt 42 Python-Tests. Die zusätzlichen synthetischen Verträge prüfen explizite Friständerung und ihren Datumsbezug, Übergabe an eine andere Person, Abschluss, anschließende Statusmeldung ohne Wiederöffnung und ausdrückliche Wiederaufnahme unter derselben Arbeits-ID. Sie prüfen außerdem die atomare Ablehnung eines Updates im falschen Vorgang, exakte persönliche Namenszuordnung und die zeitbezogene, schreibgeschützte HTTP-Schnittstelle. Diese Tests sind Infrastrukturprüfungen, keine neuen menschlichen Labels und keine Aussage über die Extraktionsqualität.

Eine spätere Statusmeldung überschreibt Frist und Eigentümer nicht mehr durch leere Schemafelder. Jede Arbeitsposition enthält ihren vollständigen belegten Ereignisverlauf; relative Fristtexte behalten das Datum ihrer ursprünglichen Nennung bzw. ausdrücklich belegten Änderung. Die sieben gespeicherten realen Vergleichsfälle bestehen mit dieser Fortschreibung weiterhin. Keine neuen Modellaufrufe.

Die React-Testansicht wurde über Browser → lokalen Proxy → schreibgeschützte SQLite-Projektion → vollständiges Original geprüft. Details und Grenzen stehen in [UI-PREVIEW.md](UI-PREVIEW.md). Das ist kein Nachweis eines vollständigen Google-Drive-Produktionsimports.

## Archivkontext und Lebenszyklus – weitere Entwicklungsbefunde

V5 erweitert den Kontext kontrolliert: vollständige aktuelle Originale, vollständiger Katalog bestehender Arbeits-IDs, begrenzte historische Originalpassagen mit ausgewiesener Auswahl. Das größte Archivoriginal (218.642 Transkriptzeichen) wurde mit Opus vollständig verarbeitet; Extraktion und Handlungsprüfung kosteten zusammen 1,788180 USD. Daraus folgt kein Nachweis vollständigen Recalls.

Die zusätzlichen Sonnet-Läufe zeigten eine doppelte Einladung und einen ausgelassenen Abschluss. V6 prüft Wiederholungen und Rollen von Zeitangaben, löste aber nicht alle Probleme: Eine explizite Zusage wurde widersprüchlich als decision klassifiziert. V7 weist diesen Feldwiderspruch vor der Übernahme zurück und lässt eine belegte Handlungsprüfung frühere Unsicherheit ausdrücklich auflösen. Beide Versionen sind Entwicklungsstände, keine bewiesene Produktionsqualität.

V8 prüft zusätzlich jede vorhandene, noch nicht wirksam aktualisierte Arbeits-ID am gesamten aktuellen Original. Jede ID benötigt ein Ergebnis, einschließlich unchanged. Nicht-Erwähnung schließt nichts ab; unbekannte IDs, fehlende Belege und heimliche Frist-/Owneränderungen werden abgewiesen. Im Finance-Test wird die Einladung am tatsächlich abgehaltenen Termin abgeschlossen. Auch die ausdrücklich begrenzte Bemühenszusage zur Vorbereitung wird anhand der bereits gezogenen und im Termin präsentierten 2,6 Millionen Datensätze als erfüllt beurteilt. Zwei neue Zusagen bleiben offen. Dies sind ausgewiesene Quelleninterpretationen, keine zusätzlichen Nutzerlabels.

Zeitangaben bleiben erhalten, auch wenn sie keine Ausführungsfrist sind: Carolines „am Mittwoch“ wird als genannter Gesprächszeitpunkt gespeichert. Die Oberfläche zeigt solche Angaben gesondert. Der Termin „Montag Mittag“ darf nicht als Versandfrist der Einladung erscheinen.

Der aktuelle Python-Stand umfasst 72 bestandene Infrastrukturtests. Der vorbereitete v8-Gesamtimport registriert alle 194 Quellen (7.531.952 Transkriptzeichen), bevor er Modellaufrufe erlaubt. Version, Modell und Inventar sind eingefroren; ein veränderter Stand braucht eine neue Generation. Der erste zusätzliche Pilot ist auf fünf Meetings und 10 USD begrenzt. Persistente Kostenreservierungen umfassen Ausgabelimit, Reparaturen und weitere Prüfschritte; bei unbekannter Usage bleibt die Reservierung belastet. Keine Veröffentlichung dieses Imports.

Vor weiterer Skalierung zu beachten: vier Quellen haben anonyme Sprecher, drei davon ausschließlich; Sprecherlabels dürfen keine globalen Personenidentitäten werden. Die Exporte enthalten keine verlässlichen absoluten Startzeiten. Eine Sortierung nach Drive-ID innerhalb desselben Tages belegt keine kausale Reihenfolge und darf in einer abschließenden Generation keinen Kontext aus möglicherweise späteren Meetings erzeugen. Nachweis: `evaluation/source-identity-quality.json`. Diese Grenzen werden vor dem endgültigen Import behandelt.

Die aktualisierte Kostenübersicht `evaluation/results-saved.json` enthält vor dem neuen Fünferpilot 51 lokal erfasste API-Aufrufe, 12,651264 USD bekannte Kosten und zwei unbekannte Fehlversuche; dazu 0,316295 USD aus dem zuvor separat gesicherten n8n-Test. Die bisherigen sieben Regressionen bleiben bestanden; sie sind weiterhin Entwicklungsfälle und keine unabhängige 95-Prozent-Abnahme.

## Abschluss des Fünferpiloten und deterministische Absicherung

Der Pilot umfasst fünf Quellen, 135 Beobachtungen und 13 echte Modellaufrufe. Sämtliche Usage liegt vor: 5,055840 USD, ohne Reparaturaufruf. Die technisch gültigen v8-Ausgaben enthielten trotzdem 16 Verpflichtungsbeobachtungen mit anonymen Sprecherlabels. In der neuen getrennten v9-Projektion bleiben alle 135 Aussagen erhalten; diese 16 Zuordnungen werden ausdrücklich als ungeklärt markiert und erzeugen keine identifizierte Arbeit. Danach bestehen fünf Arbeitsidentitäten (eine eigene, vier fremde). Die erneute Projektion nutzte gespeicherte Ergebnisse und verursachte keine Modellkosten.

V9 verwendet Aussagen früherer Tage als Vorgeschichte. Bereits eingelesene Arbeits-IDs desselben Tages stehen ausschließlich als ungeordneter Identitätskatalog bereit. Zustandsänderungen an einer am selben Tag veränderten Identität werden ohne belegte Reihenfolge zur Prüfung zurückgestellt. Die separate Lebenszyklusprüfung verwendet solche IDs nicht als angenommenen vorherigen Stand. Das ist konservativ und kann eine manuelle Prüfung erfordern; es erfindet keine Uhrzeit aus Drive-Änderungsdaten.

Der Replay-Versuch deckte außerdem auf, dass bereits gespeicherte Handlungsurteile nicht ein zweites Mal über später angehängte Lebenszyklusbeobachtungen gelegt werden dürfen. Der Wiederaufbau erhält die bereits aufgelösten Urteile und Belegreihenfolgen. Ein zusätzlicher Regressionstest prüft den Abschluss unter derselben Arbeits-ID. Der erste abgewiesene Replay blieb separat erhalten; nur ein vollständiger, regelgeprüfter Replay darf die nächste Generation starten.

Der Importplan v9 enthält fünf wiederaufgebaute Quellen und 189 noch ausstehende Quellen. Die weiteren kostenpflichtigen Aufrufe warten auf die ausdrücklich angefragte zusätzliche Obergrenze von 250 USD. Der lineare Pilotvergleich ergibt 191,11 USD für den Rest; wachsender Kontext kann darüber liegen. Kein angeblicher Rechnungsbetrag, keine 95-Prozent-Qualitätsquote. Nachweis: `evaluation/backfill-pilot-result.json`.


## GPT-6-Modellvergleich vom 24.09.2026

Ziel ist ein günstigerer Ersatz für GPT-5.6 Terra bei unveränderter fachlicher Qualität. Die Produktionsvorgabe bleibt Terra. Implementiert sind explizite Modellwahl für GPT-6 Sol/Luna, eine getrennte Extraktionsmodellwahl für den Versuch Luna → Sol sowie Preis-, Token- und Kontextprüfungen. Es erfolgte kein Deployment.

Die 272.000 Input-Tokens sind die Schwelle für den Langkontext-Tarif, nicht das Eingabelimit. Laut Modellvertrag haben beide GPT-6-Kandidaten 922.000 maximale Input-Tokens und 1.050.000 Tokens Gesamtkontext bei maximal 128.000 Output-Tokens. Input umfasst den gesamten Request einschließlich Anweisungen und Kontext. Ein historischer Request mit 407.135 Prompt-Zeichen hatte laut gespeicherter Provider-Usage 108.754 Input-Tokens; Zeichen- und Byte-Obergrenzen dürfen nicht als gemessene Tokens dargestellt werden. Diese Metadaten wurden read-only gelesen, die historischen Inhalte nicht erneut versendet.

Standardpreise in USD pro Million Input-/Output-Tokens: Terra 2/12, Sol 2/10, Luna 0,10/0,50. Sol ist beim Input gleich teuer und beim Output günstiger als Terra. Mehr Ausgaben oder Reparaturen können diesen Vorteil je Auftrag verändern. Oberhalb 272.000 Input-Tokens gelten die dokumentierten Aufschläge für den ganzen Request. Quellen: [Preise](https://developers.openai.com/api/docs/pricing), [Sol](https://developers.openai.com/api/docs/models/gpt-6-sol), [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna).

Die isolierte Auswertung nutzt die tatsächliche kompakte Pipeline mit lokalen Testdatenbanken sowie den QA-Service mit dem vorhandenen Test-Store. Nur der Provider wird real aufgerufen; Produktionsdatenbanken und Journal werden nicht eingebunden. Exakte gespeicherte Requests werden wiederverwendet, unbekannte Provider-Ausgänge blockieren einen erneuten Versand. Zwei zusätzliche unabhängige Durchläufe je schwieriger Fall haben eine eigene Trial-ID; bloße Wiederholung desselben Trials erzeugt keine neuen Modellaufrufe. Die gemeinsame Kostengrenze beträgt 10 USD. Alle Kandidaten verwenden reasoning=none.

Der Umfang ist ein Entwicklungsscreening: zwölf kurze synthetische Pipeline-Fälle und zwanzig QA-Fälle, davon acht deterministische Listen/Zählungen ohne Modellnachweis und zwölf einfache Fragen zu vier manuell angelegten Aufgaben. Die zwölf Antworten wurden pro Modell zusätzlich gegen die Quellen gelesen. Echte lange Transkripte, produktives Retrieval-Ranking, längere Chatverläufe, Schreibaktionen und projektübergreifende Widersprüche sind damit nicht abgenommen. Die ursprünglich vorgeschlagene Abnahme an rund zehn echten Meetings steht aus.

Lokale Validierung: 94 fokussierte Laufzeit-/Integrations-Unit-Tests bestanden; anschließend 17 Tests des Vergleichs und der Tokenzählung bestanden. Diese technischen Tests belegen keine semantische Produktionsqualität.


Bei den zwölf einfachen Modellfragen bestanden Terra, Sol und Luna die automatischen Prüfungen und die manuelle Prüfung der finalen Antworten gegen die vier Testaufgaben. Die acht deterministischen Kontrollen bestanden ebenfalls. Requestkosten einschließlich verbrauchter gespeicherter Antworten und Embeddings: Terra 0,050137 USD (19 Textaufrufe), Sol 0,043579 USD (17 Textaufrufe), Luna 0,002320 USD (19 Textaufrufe). Reparaturen sind enthalten. In diesem konkreten Test war Sol etwa 13 % günstiger als Terra; daraus folgt keine allgemeine Einsparquote. Replay-Wandzeiten sind kein Geschwindigkeitsnachweis.


Erster Pipeline-Durchlauf: Sol bestand 12/12 Fälle. Terra bestand sieben Fälle und stoppte am achten wegen „Condition lacks quoted evidence“; die restlichen vier wurden nicht durchgeführt. Luna-Extraktion plus Sol bestand sechs Fälle und stoppte am siebten wegen „Work update belongs to a different matter“; die restlichen fünf wurden nicht durchgeführt. Die automatische Übernahme wurde jeweils verhindert. Im Mischlauf hatte Luna die beiden Aussagen korrekt extrahiert; die falsche Themen-ID entstand im anschließenden Sol-Schritt. Das ist kein Beleg für einen isolierten Luna-Extraktionsfehler.

Zwei zusätzliche Versuche pro ausgewähltem Problemfall: Sol bestand bei „same_topic_different_action“ einen und scheiterte einmal an derselben Themen-Zuordnung; beide „partial_condition“-Versuche bestanden. Der Mischlauf bestand beide zusätzlichen Versuche für beide Fälle. Terra bestand beide zusätzlichen „partial_condition“-Versuche. Einschließlich des Erstlaufs zeigen diese kleinen Fallzahlen Schwankungen und keinen hinreichenden Qualitätsnachweis für eine Umstellung. Identische Teilrequests können zwischen Modellrouten aus dem Ledger wiederverwendet werden; die Ergebnisse sind keine unabhängige statistische Schätzung einer Fehlerrate.

Bewertung: Luna ist für die geprüften einfachen, beleggebundenen QA-Fragen ein aussichtsreicher günstiger Kandidat. Für die gesamte Transkriptverarbeitung ist weder Sol noch Luna → Sol produktiv abgenommen. Die bestehenden Identitätsprüfungen bleiben bestehen; keine Lockerung, um Tests grün zu machen. Die Modellwahl wurde vorbereitet, der Produktionsstandard bleibt Terra. Vor einer Aktivierung folgen die Abnahme mit echten repräsentativen Transkripten und die noch fehlenden komplexen Chatfälle. Die größeren Realtests wurden nach den instabilen Screening-Fällen nicht begonnen.

Abschluss des isolierten Versuchs: 1,185200 USD nach gespeicherter Usage und hinterlegten Listenpreisen, einschließlich aller Trials, Reparaturen und Embeddings; kein Rechnungsbetrag. 297 gespeicherte Provider-Calls, davon 139 Embeddings; keine unbekannten Ausgänge und keine offenen Evaluation-Outbox-Einträge. Die abschließende Wiederprüfung der ursprünglichen Terra-/Mischläufe nutzte ausschließlich gespeicherte Antworten und verursachte keine zusätzlichen Kosten. Aggregierte Belege: `evaluation/model-comparison-20260924-summary.json`; Rohantworten verbleiben unter `.local/model-comparison-20260924/`.


## Direkter Vergleich an fünf echten Transkripten – 24.09.2026

Nach expliziter Freigabe wurden dieselben fünf vollständigen Originale mit Terra und Sol bei unveränderten Prompts und `reasoning=none` ausgewertet. Auswahl: Jan/Gleb 16.06. (rund 70.000 Zeichen, längstes Original der vorhandenen Testsammlung), Finance 15.07., Mathias/Gleb 18.06. und 16.07., Jan/Gleb 09.06. Die Modellreihenfolge wechselt pro Fall. Jeder Durchlauf nutzt eine isolierte Datenbank; beim 16.06. gibt es dieselbe manuell belegte offene IT-Klärungsaufgabe vom 09.06. als Seed. Dessen vollständiges Vororiginal ist für Retrieval verfügbar. Die Testsuche verwendet weiterhin den vorhandenen Test-Store, keinen produktiven Gesamtbestand.

Vor dem ersten Aufruf eingefroren: Manifest SHA-256 `251fcda93bd005ee260f9d8501636f01188064de63f246b9233c57cf71e95cc7`, Quellenreview SHA-256 `be30f17f60381c344238df83d580c0426707580207f20fa7fa2de9c7e0177630`. Alle fünf Originale wurden vollständig durchgesehen. 21 feste Belegstellen plus 32 zusätzliche Kandidaten-/Ausschlussstellen bilden die manuelle Prüfbasis; Mehrdeutigkeiten und Überlappungen bleiben dokumentiert. Es wird keine exakte Recallquote behauptet. Die Ergebnisse werden zusätzlich anhand sämtlicher gespeicherter Beobachtungen und Arbeitszustände geprüft, nicht nur über Schema oder Aufgabenanzahl.

Der Runner speichert echte Titel, unveränderte Originaldateien, Vorher-/Nachherzustände und Beobachtungen mit Zitaten. Echte Fälle bleiben technisch als manuell prüfpflichtig gekennzeichnet. Die semantische Abnahme ist separat dokumentiert; ein grüner technischer Durchlauf ist kein Qualitätsnachweis. Nach jedem Fall werden unbekannte Provider-Ausgänge und die Outbox kontrolliert. Kein automatischer Neuversand unbekannter Ergebnisse, kein Produktionsschreibzugriff. Lokale Validierung der erweiterten Auswertung und Tokenzählung: 18 Tests bestanden.

Bewertungspräzisierung ohne Änderung der eingefrorenen Quellen: Beim Finance-Versuch bedeutet die Unsicherheit der Aufbereitung einen offenen Erfolg. Nach der bereits vorher geltenden Produktregel (`evaluation/prompt-v9.txt`, Zeilen 13 und 38) darf eine klar übernommene Bemühung als Aufgabe gelten, sofern kein fertiges Ergebnis zugesagt wird. Sol formuliert genau diese begrenzte Bemühung. Eine anfängliche Reviewer-Beanstandung wurde anhand dieser bestehenden Regel zurückgenommen; die Prompts wurden nicht angepasst.


Ergebnis: Alle zehn technischen Durchläufe wurden übernommen (`applied`), ohne Reparaturaufrufe, unbekannte Provider-Ausgänge oder offene Outbox. Alle zehn Ausgaben wurden danach semantisch gegen Originale und Vorabregister geprüft. Die eingefrorenen sieben Fixture-Dateien blieben unverändert.

| Original | Terra USD | Sol USD | Fachliche Bewertung dieses Paars |
| --- | ---: | ---: | --- |
| Jan/Gleb 16.06., lang | 0,300752 | 0,331355 | Sol erfasst zugesagte Gleb-Sichtung; Terra lässt sie aus und trennt überlappende Jan-Arbeit zu stark. Seed bei beiden korrekt offen. |
| Finance 15.07. | 0,142062 | 0,180936 | Sol bewahrt Ende April 2026; Terra schreibt Ende 2026. Beide vermeiden unbelegte Migrations-/VO-Pflichten. |
| Mathias/Gleb 18.06. | 0,072244 | 0,071732 | Beide erfassen Sichtung und Rückmeldung passend; keine aus ASR erfundene Frist. |
| Mathias/Gleb 16.07. | 0,070224 | 0,054742 | Beide erfassen eine Terminverschiebung; keine neue Maryam-Zusage, keine Versandfrist aus der Uhrzeit. |
| Jan/Gleb 09.06. | 0,208624 | 0,234799 | Sol trennt Wochenziel von fester Zusage und bewahrt die Upload-Bemühung; Terra setzt eine zusätzliche sichere Fertigstellungsaufgabe und hält den Upload im Review. |
| **Gesamt** | **0,793906** | **0,873564** | **Sol kostet in diesem Vergleich 10,03 % mehr.** |

Je Modell gab es 15 Textaufrufe. Terra verbrauchte insgesamt 191.022 Input- und 26.292 Output-Tokens; Sol 201.978 Input- und 36.771 Output-Tokens. Das sind Summen über alle Aufrufe, keine einzelnen Kontextgrößen. Rund 40 % mehr Output-Tokens sowie etwas mehr Input verbrauchten Sols niedrigeren Output-Tarif. Reasoning-Tokens: bei beiden null. Kosten enthalten die protokollierten Cache-Schreibpreise, Embeddings und gegebenenfalls verbrauchte gespeicherte Antworten; keine Rechnung oder Prognose für andere Meetings. Die zehn neuen Durchläufe kosteten inkrementell 1,667467 USD. Die Vergleichssumme liegt durch ein wiederverwendetes Embedding um 0,000003 USD darüber.

Fachliches Urteil: Sol war in den drei längeren Gesprächen stärker; die zwei kurzen Gespräche waren bei beiden passend. Neben den klaren Auslassungs-/Datumsfehlern werden mehrdeutige Granularität und übervorsichtige Review-Zuordnungen separat bewertet. Die eigenständige Hierarchie-Selbstprüfung bleibt bei beiden eine nicht abschließend geklärte Aufgabenidentität. Daraus folgt weder eine exakte Recallquote noch eine allgemeine Fehlerfreiheit von Sol. Dieser Test umfasst einen Durchlauf pro Modell und Original sowie begrenzte identische Vorgeschichte, nicht den vollständigen Produktions-Memorybestand.

**Entscheidung:** Unter der ausdrücklichen Vorgabe „Sol nur, wenn Terra teurer ist“ wird nicht umgestellt. Terra bleibt Produktionsstandard. Sol ist nach diesen fünf Fällen ein möglicher Qualitätsgewinn mit ungefähr 10 % Aufpreis, kein belegter Sparwechsel. Die vereinbarte Testserie ist abgeschlossen; keine automatische Erweiterung, Promptoptimierung oder produktive Umstellung. Aggregierte Belege: `evaluation/model-comparison-20260924-real-summary.json`; Originale, eingefrorene Voraberwartungen und Antworten liegen privat unter `.local/model-comparison-20260924/`.
