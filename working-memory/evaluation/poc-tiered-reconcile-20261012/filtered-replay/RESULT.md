# Lokale Filter-Auswertung · 2026-10-13
Nur lokale gespeicherte Daten; keine neuen Modellaufrufe. F=gefiltert, K=ungefilterte Kontrolle; n/b=nicht bestimmbar. Referenzvergleich, keine fachliche Wahrheitsprüfung.
Quellen: comparison_requests-run2.jsonl, beide results-filtered-run*.jsonl, selected_requests*.jsonl, ../model-replay/requests.jsonl; README und server-run*.log lokal gelesen. 9 eindeutige Ergebnisse, 6 F + 3 K; kein Retry/Best-of-N.
Unverändertes README-Kommando: `python3 -I -B compare_filtered.py --requests comparison_requests-run2.jsonl --results results-filtered-run1.jsonl results-filtered-run2.jsonl`; Exitcode 1, passed=0, quality_pass=0, cost_complete=1, evidence_known=0. Eigene Stdlib-Berechnung bestätigt alle bestimmbaren CLI-Zahlen; Paketdateien unverändert.

| Kriterium | Status | Nachweis |
| --- | --- | --- |
| Schema / Endform | nicht bestanden | Schema 9/9 (Referenz 9/9); Endform 8/9. Nr. 5: work_results=null, 2 open_ids, 0/12 Beobachtungen. |
| Kein Filterverlust | bestanden | 0 Lebenszyklusänderungen und 0 Zielbeobachtungen verworfen; 6 bzw. 4 Positive in F. |
| Lebenszyklus-Recall 100 % | nicht bestanden | 2/5 = 40.00 % bei Endantworten; 3 verpasst, 1 weitere Änderung ohne Endantwort; geliefert 2/6. |
| Zielübereinstimmung F ≥ K − 2 pp | nicht bestimmbar | Keine vollständige F-Endantwortbasis. K=90.91 %, Schwelle=88.91 %. |
| Beobachtungsabdeckung | nicht bestanden | 75/87 source_index; 12 fehlen, 0 zusätzliche, 0 Duplikate. |
| Gesamtqualität | nicht bestanden | Recall und Endform scheitern; kein Freigabenachweis. |

Je Aufruf, nur Zahlen: K=0 F / 1 Kontrolle; S=Schema, E=Endform; R=Recall Treffer/Positive (n/b bei fehlender Endform); Z/U/Ki=Ziel/update/kind-Treffer; B=Abdeckung; Δ=zusätzliche Lebenszyklusflags; V=Filterverlust L/O. Nr. 5: CLI-Vergleiche unbekannt.

| Nr | K | S | E | R | Z | U | Ki | B | fehlend | extra | Δ | V |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 0 | 1 | 1 | 0/1 | 6 | 6 | 6 | 6/6 | 0 | 0 | 0 | 0/0 |
| 2 | 0 | 1 | 1 | 0/1 | 8 | 8 | 9 | 9/9 | 0 | 0 | 0 | 0/0 |
| 3 | 0 | 1 | 1 | 2/2 | 7 | 7 | 7 | 7/7 | 0 | 0 | 0 | 0/0 |
| 4 | 0 | 1 | 1 | 0/1 | 13 | 13 | 13 | 13/13 | 0 | 0 | 0 | 0/0 |
| 5 | 0 | 1 | 0 | n/b | n/b | n/b | n/b | 0/12 | 12 | 0 | n/b | 0/0 |
| 6 | 0 | 1 | 1 | 0/0 | 16 | 17 | 18 | 18/18 | 0 | 0 | 0 | 0/0 |
| 7 | 1 | 1 | 1 | 0/1 | 5 | 6 | 6 | 6/6 | 0 | 0 | 1 | 0/0 |
| 8 | 1 | 1 | 1 | 0/1 | 8 | 8 | 9 | 9/9 | 0 | 0 | 0 | 0/0 |
| 9 | 1 | 1 | 1 | 2/2 | 7 | 7 | 7 | 7/7 | 0 | 0 | 0 | 0/0 |
Zielvergleich: gültige F-Endantworten 50/53=94.34 % (explorativ); alle F geliefert 50/65=76.92 % bei fehlend=Fehler, damit unter Schwelle. Beides ersetzt keine vollständige Endantwortbasis.
Gepaarte 3 Jobs: F 21/22=95.45 %, K 20/22=90.91 %; F/K Lifecycle je 2/4, zusätzliche Flags 0/1. K-Zielrauschen 2/22=9.09 %; 2/4 Lifecycle-Positive abweichend.

Aggregiert, geliefert: fehlende Antworten zählen hier als Nichttreffer; dies ist keine Aussage über unbekannte Entscheidungen.

| Gruppe | Schema/Endform | L geliefert/Referenz | zusätzliche L | Filterverlust L/O | Z/U/Ki geliefert | Beobachtungen | fehlend/extra |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F | 6/6; 5/6 | 2/6 | 0 + n/b | 0/0 | 50/65; 51/65; 53/65 | 53/65 | 12/0 |
| K | 3/3; 3/3 | 2/4 | 1 | 0/0 | 20/22; 21/22; 22/22 | 22/22 | 0/0 |
| Alle | 9/9; 8/9 | 4/10 | 1 + n/b | 0/0 | 70/87; 72/87; 75/87 | 75/87 | 12/0 |

Kosten je Aufruf: I/O=Input-/Outputtokens, ref→neu; tatsächlich aus Usage, Preise 2,00 / 0,10 / 2,50 / 10,00 USD/Mio. Standardinput=I−Cached−Cache-Schreiben; Reasoning in O enthalten; je Aufruf Mikro-USD aufgerundet.

| Nr | I ref→neu | O ref→neu | I/O Tokenersparnis % | Cached/Write neu | USD ref | USD tatsächlich | Ersparnis % | Sekunden |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 49499→36808 | 4167→3152 | 25.64/24.36 | 0/36805 | 0.165416 | 0.123539 | 25.32 | 52.081 |
| 2 | 56273→41055 | 5664→4503 | 27.04/20.50 | 0/0 | 0.197321 | 0.127140 | 35.57 | 94.130 |
| 3 | 61529→43012 | 5377→4505 | 30.09/16.22 | 0/0 | 0.207591 | 0.131074 | 36.86 | 75.466 |
| 4 | 69010→55438 | 7073→5984 | 19.67/15.40 | 0/0 | 0.243254 | 0.170716 | 29.82 | 87.662 |
| 5 | 89358→63467 | 8093→376 | 28.97/95.35 | 0/0 | 0.304324 | 0.130694 | 57.05 | 15.204 |
| 6 | 103263→76072 | 9661→7513 | 26.33/22.23 | 0/0 | 0.354766 | 0.227274 | 35.94 | 105.582 |
| 7 | 49499→49511 | 4167→4127 | -0.02/0.96 | 0/0 | 0.165416 | 0.140292 | 15.19 | 62.341 |
| 8 | 56273→56285 | 5664→5275 | -0.02/6.87 | 0/0 | 0.197321 | 0.165320 | 16.22 | 80.788 |
| 9 | 61529→61541 | 5377→5183 | -0.02/3.61 | 0/0 | 0.207591 | 0.174912 | 15.74 | 76.566 |

| Gruppe | USD ref→neu | Ersparnis USD / % | I-Tokens ref→neu / % | O-Tokens ref→neu / % | I-/O-Kostenersparnis USD | I/O Anteil an Ersparnis % | Σ Sekunden |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F | 1.472672→0.910437 | 0.562235 / 38.18 | 428932→315852 / 26.36 | 40035→26033 / 34.97 | 0.422214 / 0.140020 | 75.10 / 24.90 | 430.125 |
| K | 0.570328→0.480524 | 0.089804 / 15.75 | 167301→167337 / -0.02 | 15208→14585 / 4.10 | 0.083574 / 0.006230 | 93.06 / 6.94 | 219.695 |
| Alle | 2.043000→1.390961 | 0.652039 / 31.92 | 596233→483189 / 18.96 | 55243→40618 / 26.47 | 0.505788 / 0.146250 | 77.57 / 22.43 | 649.820 |
Kostenkontext: Referenz schreibt Cache in allen 9 Vergleichszeilen; Replay nur Nr. 1, Cached=0 überall. Daher ist die Dollarersparnis teilweise Preis-/Cacheeffekt; Kontrollen sparen trotz je 12 zusätzlichen Inputtokens. Nr. 5 spart durch eine nicht abschließende Antwort. Run-1-Kosten aus Usage nachberechnet, ohne historische Dateiänderung. Die Summen der I-/O-Komponenten weichen wegen Aufrundung/Rundung um 0,000001 USD von der Gesamt-Differenz ab.
Nur gültige F-Endantworten: 1.168348→0.779743 USD, 33.26 % Ersparnis. Refkosten in 'Alle' enthalten die drei gepaarten Referenzen nochmals als jeweilige Kontrollbasis.
Laufzeit: gespeicherte elapsed_seconds (Call-Zeit), Summe 649.820 s, Mittel 72.202 s, Bereich 15.204–105.582 s. Referenzlaufzeit/-beschleunigung nicht bestimmbar: kein Zeitfeld in Referenzanfragen; Summe ist keine gesamte Sitzungsdauer.

Abweichungen: L=Lebenszyklus, O=Beobachtung; ∅=kein Ziel. Alter=Meetingdatum minus last_changed in Tagen; Alias lokal je Katalog. Entscheidungsstrings enthalten ausschließlich Aliase und Schema-Kategorien. Fehlende Entscheidungen sind keine erfundenen Modellentscheidungen.

| Nr | Aufruf | Typ | L/O | source_index | Alias | Referenz | Neu | Alter |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | b5e4fddb | verpasst | L | — | W5 | progress | unchanged | 11 |
| 2 | 2d34a51a | verpasst | L | — | W8 | progress | unchanged | 1 |
| 2 | 2d34a51a | anderes Ziel | O | 0 | W8 | ∅/none/status | W8/progress/status | 1 |
| 4 | 8bdacbe2 | verpasst | L | — | W130 | progress | unchanged | 3 |
| 5 | a8c4b587 | verpasst | L | — | W73 | ambiguous | nicht bestimmbar | 3 |
| 5 | a8c4b587 | verpasst | O | 0 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 1 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 2 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 3 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 4 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 5 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 6 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 7 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 8 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 9 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 10 | ∅ | ∅/none | fehlend | — |
| 5 | a8c4b587 | verpasst | O | 11 | ∅ | ∅/none | fehlend | — |
| 6 | d825f68c | anderes Ziel | O | 9 | W147 | ∅/none/status | W147/progress/status | 4 |
| 6 | d825f68c | anderes Ziel | O | 14 | W147 | W147/none/status | ∅/none/status | 4 |
| 7 | b5e4fddb | verpasst | L | — | W5 | progress | unchanged | 11 |
| 7 | b5e4fddb | zusätzlich | L | — | W32 | unchanged | progress | 11 |
| 7 | b5e4fddb | anderes Ziel | O | 1 | W32 | W32/progress/status | W5/progress/status | 11 |
| 8 | 2d34a51a | verpasst | L | — | W8 | progress | unchanged | 1 |
| 8 | 2d34a51a | anderes Ziel | O | 0 | W8 | ∅/none/status | W8/progress/status | 1 |
Muster: drei progress→unchanged in F; zwei davon auch in den gepaarten Kontrollen. Die beiden ambiguous-Flags von Nr. 3/9 bleiben erhalten. Nr. 5 liefert eine Zwischenantwort statt Reconciliation; reine Zielwechsel und update-Abweichungen treten auch ohne Filter auf. Keine dieser Abweichungen entsteht durch verworfene Referenzaufgaben; eine kausale Trennung von Filtereffekt und Modellrauschen gelingt mit diesen Kontrollen nicht.

Positive: F 6 Lifecycle-Änderungen (3 progress, 3 ambiguous), 4 Zielbeobachtungen / 3 unterschiedliche Zielaliase pro Aufruf; K 4 / 1 / 1. Summe inkl. Kontrollduplikaten 10 Lifecycle / 5 Ziele; unabhängige Originaljobs 6. ambiguous ist ein Schema-Flag, keine sichere Statusänderung.
Ziele mit nichtleerem Referenz-update_target: F 3/4=75.00 %, K 0/1=0.00 % Treffer; 61/65 F- und 21/22 K-Referenzziele sind leer. Die hohe Gesamtübereinstimmung wird von leeren Zielen dominiert; positive Zielentscheidungen sind besonders schwach belegt.
Nominale 95-%-Wilson-Intervalle für positive Zieltreffer: F 30.06–95.44 %, K 0.00–79.35 %; dieselben Auswahl-/Korrelationsgrenzen gelten.
Nominale 95-%-Wilson-Intervalle: Lifecycle bei gültigen F-Endantworten 2/5: 11.76–76.93 %; geliefert 2/6: 9.68–70.00 %; K 2/4: 15.00–85.00 %. Ziele gültige F 50/53: 84.63–98.06 %; K 20/22: 72.19–97.47 %.
0 Filterverluste bei 6 Lifecycle-Positiven: exakte einseitige 95-%-Binomialobergrenze 39.30 %; bei 4 Zielbeobachtungen 52.71 %. Nur hypothetisch unabhängige Bernoulli-Fälle: Beobachtungen innerhalb Jobs korreliert, Kontrollen wiederholen Jobs, Auswahl budgetbegrenzt und positiv vorselektiert. Keine repräsentative Fehlerratengarantie oder belastbarer 2-pp-Nichtunterlegenheitsnachweis.
Pflichtfall 4e7b6e03 / W349: in selected_requests.jsonl enthalten (call_index=54), Alter 25 Tage, Rang 12 (lokale codex-rank/metrics.json), vom Filter behalten; Referenz=done. In Vergleichsplan/Run 2 und Ergebnissen nicht enthalten: größte gefilterte Anfrage budgetbedingt entfernt (README). Neue Sol-Entscheidung und Recall dafür nicht bestimmbar; Pflichtfall offen.
Prüfgrenze: Schema gegen den tatsächlich vorkommenden lokalen Keyword-Teilumfang unabhängig validiert; keine allgemeinen Metaschema-/Netzwerkprüfungen. Referenztexte/Usage/Originalanfragen mit model-replay/requests.jsonl abgeglichen; Quellen vor/nach Auswertung SHA-256-identisch. Eigener Code nur im freigegebenen Scratchpad; allein RESULT.md neu angelegt.
