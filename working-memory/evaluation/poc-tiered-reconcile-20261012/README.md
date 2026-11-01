# PoC: gestufter Bestandsabgleich (12.10.2026)

Status (13.10.): Produktions-Suchränge lokal validiert; abschaltbare Hot-Set-Kopie (`pipeline-v12/`, A=30,k=5) mit 69/69 PoC-Tests; gefilterter Sol-Replay ausgewertet. Kein beobachteter Filterverlust, aber Qualität und Verlustfreiheit nicht nachgewiesen; Pflichtfall offen, keine Produktivfreigabe. Luna verworfen. Keine Produktionsänderung.

## Frage
Der Bestandsabgleich verursacht ~74 % der Kosten. Kann man ihn ohne Qualitätsverlust deutlich verbilligen, und wie bleibt das bei wachsendem Bestand tragfähig?

## Datenbasis (kostenlos, lokal)
Vollsicherung `dashboard-20261012T155114Z.tar.gz`, Datei `canonical/queue.jsonl`: 4.821 gespeicherte Aufrufe mit Prompt, Antwort, Usage und Embeddings, 23.918 Suchdokumente. Ausgewertet: 40 Abgleich-Aufrufe (Meetings 5.–12.10.2026), 12.223 Kandidaten-Aufgaben. Skripte: `replay/`. Rohdaten mit Meetinginhalt liegen nicht im Repo.

## Befunde
1. **Der Katalog ist fast der gesamte Bestand.** 706 Aufgaben im Bestand (12.10., +~8 pro Tag). Ein Meeting mit ~30 Beobachtungen schickt 450–520 davon (≈70 %). Kandidaten ≈ min(Bestand, 20 × Beobachtungen). Kosten wachsen damit linear mit dem Bestand.
2. **99,5 % der Prüfungen sind Ballast.** Von 12.223 Kandidaten wurden 64 genutzt (Urteil ≠ unchanged oder als update_target gewählt). Das Modell gibt 10.992-mal "unchanged" aus.
3. **Erledigte Aufgaben:** 1.590 Kandidaten mit Status `done`, 0 genutzt.
4. **Genutzte Aufgaben sind jung:** Median 4 Tage seit letzter Änderung, P90 16 Tage; Kandidaten insgesamt Median 53 Tage.
5. **Einfaches Ähnlichkeitsranking allein reicht nicht.** Selbst Embedding-Top-20 innerhalb der Kandidaten erfasst nur 78 % der gewählten update_targets (lexikalisch 49 %, beides 87 %). Lebenszyklus-Treffer ohne Beobachtung liegen teils auf Rang 60–90. Eine harte Top-K-Kürzung wäre unsicher.
6. **Aktualität + Ähnlichkeit zusammen:** behalte Aufgabe, wenn Alter ≤ A Tage ODER Rang < k (Embedding oder lexikalisch). A=21, k=5 → 64/64 genutzte behalten bei 54,3 % der Kandidaten; A=30, k=3 → 64/64 bei 52,3 %; A=7, k=3 → 93,8 % bei 35,1 %. Stichprobe klein (64 Positive): kein Beleg für 100 % im Betrieb.
7. **Folgerunden (Codex-Analyse, ganzes Archiv):** 12 Jobs hatten mehrere Abgleich-Aufrufe; die ersten Runden kosteten 3,57 von 48,32 USD (7,4 %). 58 nachgeforderte Archivtexte (50 Passagen, 7 Wissen, 1 Zusammenfassung). **Keine brauchbare Vorhersageregel:** "irgendeine gekürzte Karte" erkennt 4/4, aber 32/37 Fehlalarme. Vorab-Öffnen ist daher nicht belegt.
9. **Kosten je Stufe (42 Jobs, 23,15 USD):** Abgleich 73,5 %, Extraktion 20,0 %, Prüfung 6,5 %, Embeddings 0,07 %. Das Original-JSON (≈14.000 Token/Job) wird in allen drei Stufen identisch gesendet; Stufenpräfixe unterscheiden sich, deshalb kein Cache-Treffer.
8. **Ausgabe:** 355.838 Ausgabetokens in 40 Aufrufen; ein großer Teil sind unverändert neu ausgegebene Beobachtungen und "unchanged"-Einträge.

## Gegenprüfung (Codex, unabhängig neu gerechnet)
- Kernzahlen bestätigt: 40 Aufrufe/36 Jobs, 12.290 Kandidaten (12.223 mit Beobachtungen), 64 genutzt; A=21,k=5 → 64/64 bei 54,26 %. Nach Entfernen der Zwischenrunden (nur letzte Runde je Job): 11.022 Kandidaten, 64 Positive, 100 % Recall bei 54,67 %.
- Keine Aliasfehler gefunden; Titel-Zuordnung der Embeddings bleibt strukturell fragil.
- **Grenzen:** 95-%-Konfidenzintervall für 64/64 = 94,4–100 % (nur unter Unabhängigkeit); Positive stammen aus 23 Aufrufen und nur aus 5.–12.10.; Parameter wurden auf derselben Stichprobe gewählt und bewertet (in-sample); "genutzt" = Entscheidung des Modells, keine fachliche Wahrheit; 1.268 Kandidaten (Zwischenrunden) ohne Urteil wurden als negativ gezählt.
- Konsequenz: Die Aussage lautet "Katalog ca. −45 % bei 0 Verlusten in der Stichprobe", nicht "verlustfrei". Fehlend für Verlustfreiheit: fixierte Parameter auf späteren unabhängigen Meetings (Schattenbetrieb, Tor 3) und fachliche Prüfung der Abweichungen.
- **Flex:** `flex_unavailable` ist lokal nicht belegt (keine Rohfehlerdaten, Provider verwirft Fehlerkörper `openai_provider.py:213`, `:121`). Die Aussage "Flex geht nicht" ist unbewiesen; klärbar mit einem einzelnen synthetischen Request mit gesicherter Fehlerantwort.
- **Batch:** kein Tarifschalter, sondern Umbau zu persistenter Fortsetzung (Lease 600 s, Ledger, Budget-Preisweg, antwortabhängige `open_ids`-Schleife `compact_reconcile.py:176`).

## Verworfen
- Cache-Grenze im Abgleich (negativ), verlustfreie Packung (+0,52 %), Decisions API als Ersatz (nur Klassifikation, Limits undokumentiert, gleicher Preis wie Luna).
- Reines Embedding-Top-K ohne weitere Absicherung (Befund 5).

## Zielarchitektur (Vorschlag)
1. **Bestand in Schichten:** Hot-Set mit A=30 Tagen, k=5; Status `done` wird gleich behandelt. Alte Aufgaben außerhalb des Hot-Sets bleiben im Bestand; ein vorgeschlagener wöchentlicher Vollabgleich im Batch (50 % Tarifnachlass; Umsetzung offen) soll sie als Sicherheitsnetz prüfen.
2. **Kandidatenreduktion per Hot-Set-Filter:** auf Basis der separaten Work-Suchliste der Produktion behalten, wenn Aktualität ≤ 30 Tage ODER nullbasierter Suchrang < 5 ODER Aufgaben-ID exakt im Transkript genannt; Sol entscheidet über die reduzierten Kandidaten. Abschaltbar per `DASHBOARD_HOTSET_FILTER`; Sicherheitsnetz und Evidenzsammlung auf neuen Meetings vor Produktivfreigabe.
3. **Ausgabe als Delta:** nur Änderungen und update_targets, keine "unchanged"-Listen, keine Wiederholung unveränderter Beobachtungen. Vollständige Endform und stabile Lebenszyklusurteile bleiben Pflicht; die beobachtete Sol-Instabilität bei `progress` ist für R2 Verfolgung relevant.
4. **Folgerunden verbilligen statt vermeiden:** Nachforderung ist nicht vorhersagbar. Prompt so ordnen, dass der große unveränderte Block vorne steht und die "geöffnet"-Liste hinten, damit die Folgerunde aus dem Cache liest (Hypothese, ≤ 5 % der Abgleichkosten, ungemessen).

## Kostenmodell (Rechnung auf den 40 Aufrufen, Listenpreise, ohne Cache-Aufschlag)
| Variante | USD (40 Aufrufe) | Bemerkung |
|---|---:|---|
| heute (Sol Standard) | ≈ 12,2 | Basis |
| Hot-Set-Filter (A=30, k=5) | nicht auf 40 Aufrufe hochgerechnet | ≈ −20 bis −27 % zusätzlich zum Cache-Fix (kontrollnormierte Näherung, nicht isoliert gemessen); gesamt gemessen ≈ −33 bis −38 % gegenüber Ausgangslage |
| Sol Batch | ≈ 6,1 | −50 %, Latenz/Umbau |
| Triage Luna + Sol auf 20 % | ≈ 6,2 | gemessen: verworfen; Triage selbst ungetestet, wegen geringer Unterscheidungsleistung im Replay nicht empfohlen |
| Alles auf Luna | ≈ 0,6 | gemessen: verworfen; 0,55 USD im Replay, Qualitätsmaßstab nicht erfüllt |

Kostenvarianten außer Hot-Set auf 40 Aufrufen gerechnet, nicht gemessen; Hot-Set-Messung auf kleiner Teilmenge siehe „Ergebnis Hot-Set-Replay (13.10.)“, Modell-Replay siehe unten. Annahmen: Katalog ≈ 75 % der Eingabe, Ausgabe zu 65 % Beobachtungen.

## Ergebnis Hot-Set-Replay (13.10.)
- **A · Produktionsränge und Kopie:** 36/36 Aufrufe und 716/716 Beobachtungsanfragen rekonstruiert. Rang ist nullbasiert; die separate Work-Liste zählt. `pipeline-v12/` ist eine abschaltbare Kopie (`DASHBOARD_HOTSET_FILTER`, Standard A=30,k=5), 69/69 PoC-Tests bestanden. Review laut Sitzungsbefund: „Freigabe mit Auflagen“, nur isolierter Offline-Vergleich; `DEPLOY-NOTES.md` dokumentiert keine globale Abnahme, zehn unveränderte Vollsuite-Fehler und historische offene Schreibgrenzen-Nachweise. Der Worker veröffentlicht regulär; die Versionskennung ändert Job-/Request-Identität und schafft keinen Schattenmodus.

| Vergleich / Parameter | Recall / Kandidaten / Ziele | Kosten aus Usage |
|---|---|---|
| Produktionsränge A=30,k=5 | 64/64 genutzt behalten; 6.002/12.223 Kandidaten = 49,1 % | keine Kostenmessung im Rangvergleich |
| Produktionsränge A=21,k=5 | 63/64; verpasst: Alter 25 Tage, Rang 12 | keine Kostenmessung im Rangvergleich |
| Sol gefiltert, 6 Aufrufe | Lebenszyklus-Endantworten 2/5; Ziele 50/53 = 94,3 % | 1,472672 → 0,910437 USD; −38,18 % |
| Sol ungefiltert, 3 Kontrollen | Lebenszyklus 2/4; Ziele 20/22 = 90,9 % | 0,570328 → 0,480524 USD; −15,75 % |
| Gefiltert, nur gültige Endantworten | 5/6 Endantworten | 1,168348 → 0,779743 USD; −33,26 % |

- **B · Qualität:** Modell und 0 Transportfehler sind Sitzungsbefunde (gpt-6.1-sol); die Auswertung bestätigt 6 gefilterte und 3 ungefilterte Ergebnisse. Filterverlust 0: keine Referenz-Lebenszyklusänderung oder Zielbeobachtung verworfen, bei 6 Lebenszyklus-Positiven und 4 Zielbeobachtungen. Endantwort-Recall 2/5; ein gefilterter Aufruf liefert `open_ids` statt Endform. Sol reproduziert ungefiltert nur 2/4 Lebenszyklusurteile; die beiden `progress`-Urteile werden auch gefiltert verpasst. Das belegt Modellrauschen, trennt Filterwirkung aber nicht kausal. Die Zielübereinstimmung gültiger Endantworten (94,3 % gegenüber 90,9 %) ist explorativ: breite 95-%-Intervalle, nur 4 nichtleere Referenzziele im gefilterten Lauf. Gesamtqualität nicht bestanden. Pflichtfall Alter 25 Tage/Rang 12 budgetbedingt nicht im Modelllauf; bleibt offen.
- **C · Kosten:** Nachgerechnet mit 2,00/0,10/2,50/10,00 USD je Million Tokens (Standardinput/Cache-Lesen/Cache-Schreiben/Output). Gefiltert rund 1,47 → 0,91 USD (−38,2 %), Eingabetokens −26,36 %, Ausgabetokens −34,97 %. Wegfall des Cache-Aufschlags im explicit-Modus laut Sitzung; die Quelle belegt weniger Cache-Schreiben und −15,75 % auch in Kontrollen, einschließlich Antwortabweichungen. Das sind keine isoliert belegten 15,8 Prozentpunkte Cachewirkung. Nach Normierung mit der Kontrollersparnis ergeben sich ca. −20 bis −27 % zusätzlich zum Cache-Fix; keine kausale Filtermessung, zumal eine Nachforderung die Kosten senkt. Filter-Replays einschließlich Kontrollen: 1,390961 USD (≈ 1,39 USD); alle bezahlten Sitzungstests laut Sitzungsbefund ca. 1,95 USD, in diesen drei Quellen nicht vollständig belegt.
- **D · Aussagekraft:** Kleine, positiv vorselektierte und korrelierte Stichprobe. 0 Filterverluste bei 6 Lebenszyklus-Positiven entsprechen unter hypothetischer Unabhängigkeit einer einseitigen 95-%-Obergrenze von 39,30 %; kein Nachweis der Verlustfreiheit. Verrauschte Modellreferenzen sind kein fachlicher Wahrheitsmaßstab.
- **E · Folgerung:** Hot-Set weder widerlegt noch bewiesen; nicht ohne weiteres produktiv. Empfehlung: Sicherheitsnetz durch wöchentlichen Vollabgleich im Batch (50 % Tarifnachlass) plus Evidenzsammlung auf neuen Meetings. Hohes Restrisiko: Eine relevante Aufgabe mit Alter 31 Tage, Rang ≥ 5 und ohne exakte ID-Nennung wird still nicht geprüft. Sol-Instabilität bei `progress` bleibt ein Produktqualitätsbefund für R2.

Belege: [RESULT.md](filtered-replay/RESULT.md), [RANK-VALIDATION.md](selector/RANK-VALIDATION.md), [DEPLOY-NOTES.md](pipeline-v12/DEPLOY-NOTES.md). Sitzungsbefunde und vorgeschlagenes Sicherheitsnetz sind ausdrücklich von den lokalen Nachweisen getrennt.

## Ergebnis Tor 2 (Modell-Replay)
- **Lauf:** 41 gespeicherte Abgleich-Anfragen mit identischem Prompt/Schema auf gpt-6-luna Standard nachgespielt; 0 Transportfehler, alle Antworten `status=completed`, Schema 41/41. 40 Referenzantworten vorhanden; eine fehlt.
- **Kosten aus Usage:** 0,55163874 USD (≈ 0,55 USD) gegenüber 15,016926 USD (≈ 15,02 USD) Sol-Referenz, damit 27,22× (≈ 27×) günstiger. Keine Providerrechnung.
- **Qualität:** 24/41 Antworten ungültig: keine vollständige Endform (`work_results=null`, `open_ids=[]`), keine legitimen Nachforderungen. Schemaerfüllung und `completed` belegen keine vollständige Entscheidung.
- **Fairer Vergleich (15 Aufrufe, beide vollständige Endform):** Recall der Sol-Lebenszyklusänderungen 1/4 = 25 %, 4 zusätzliche Flags; `update_target`-Übereinstimmung 128/140 = 91,4 % (einschließlich null), bei von Sol gewählten Zielen 0/12.
- **Zählung und Tor:** 30 Referenz-Lebenszyklusänderungen in `work_results`; die früher genannten 64 „genutzten“ Kandidaten sind die Vereinigung aus Lebenszyklusänderungen und `update_targets` der Beobachtungen. Der vorab gesetzte Erfolgsmaßstab (≥ 62/64 bzw. ≥ 97 % Recall, ≥ 95 % gleiche Ziele) ist **nicht erfüllt**. Referenzübereinstimmung ist keine fachliche Wahrheitsprüfung.
- **Schlussfolgerung:** „Alles auf Luna“ ist mit diesem Prompt widerlegt. Luna-Triage (Luna sortiert vor, Sol entscheidet) ist nicht getestet und wegen der geringen Unterscheidungsleistung nicht empfohlen. Tragfähiger Weg: Sol mit reduziertem Kandidatenkreis (Hot-Set-Filter), Delta-Ausgabe, später Batch; Produktionsnachweis bleibt Tor 3.
- **Bezahlte Tests dieser Sitzung:** ca. 0,56 USD (Smoke 0,013 USD + Vollauf 0,55 USD); freigegebener Rahmen 2–5 EUR. Smoke-Verbrauch laut Sitzungsbefund, Vollauf aus Usage.
- **Flex:** `flex_unavailable` bleibt unbelegt: keine Rohfehlerdaten, Provider verwirft Fehlerkörper.

Belege: [RESULT.md](model-replay/RESULT.md) (Usage, Schema, Gesamtvergleich) und [RESULT-DETAIL.md](model-replay/RESULT-DETAIL.md) (Endform und faire Vergleichsmenge).

## Stand der Prototypen (12.10., abends)
- `selector/`: deterministischer Selektor + Replay, 29/29 Tests grün (selbst nachgeprüft), reproduziert 64/64 bei 54,26 % (A=21, k=5).
- `model-replay/`: Harness für den Modell-Replay (extract → dry-run → execute → compare), 49/49 Tests grün, Dry-Run über 41 gespeicherte Abgleich-Anfragen: Kostenobergrenze (inkl. reservierter Ausgabe) **0,94 USD** für gpt-6-luna Standard.
- **Erledigt:** Der Replay lief am 12.10. auf dem Server (Smoke-Test, dann 41 Aufrufe, 0 Fehler); Ergebnis siehe „Ergebnis Tor 2 (Modell-Replay)“ und `model-replay/RESULT.md`, `RESULT-DETAIL.md`.

## Entscheidungstore
- **Tor 1 (kostenlos):** Selektor-Prototyp + Replay reproduzieren Befund 6; unabhängige Gegenprüfung ohne Abweichung.
- **Tor 2 (bezahlt): durchgeführt, nicht bestanden.** Replay der 41 gespeicherten Abgleich-Anfragen auf gpt-6-luna Standard; gemessen 0,55 USD. Vergleich gegen gespeicherte Sol-Antworten: fairer Recall 1/4, `update_target` 128/140 = 91,4 %; Erfolgsmaßstab vorab (≥ 62/64 bzw. ≥ 97 % Recall und ≥ 95 % Übereinstimmung) nicht erfüllt. Zählung und Grenzen siehe „Ergebnis Tor 2 (Modell-Replay)“.
- **Tor 3: offen.** Echter Parallelbetrieb braucht getrennten Ledger/Outbox und Publikationssperre; der reguläre Worker veröffentlicht, eine neue Pipeline-Version allein genügt nicht. Alternative: Evidenzsammlung per isoliertem Offline-Replay je neues Meeting über mindestens 20 neue Meetings, mit fachlicher Prüfung der Abweichungen und dem offenen Pflichtfall Alter 25 Tage/Rang 12. Wöchentlichen Vollabgleich als Sicherheitsnetz nachweisen; erst nach erfüllten Qualitäts-/Kostenkriterien eine separat freizugebende, zurückdrehbare Umschaltung.
