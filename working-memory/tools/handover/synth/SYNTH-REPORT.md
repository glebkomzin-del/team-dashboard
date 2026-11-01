# SYNTH-REPORT

pruefung: mechanisch
fachurteil: 0
pakete: 5
zaehleinheit: assertion
reife: ground_check_ergebnis
verstosse: ground_check_rohantwort
zitatpflicht: wiederverwendung
zitatpruefung: woertlich_in_referenziertem_beleg
wiederverwendung: rohantwort
lexikalisch: substring_oder_wortmenge_casefold
wortfilter: deutsche_funktionswoerter
belegbasis: build_evidence_block
schwelle_prozent: 60
semantische_abnahme: unbekannt

| Paket | belegt | Annahme | unbekannt | Verstöße | erfundene_ID | fehlendes_Zitat | belegt_ohne_ID | zurückgesetzt | entfernte_Wiederverwendung | Zeilen | Bytes | max_Zeile | Limitverstöße |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 5 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 43 | 4904 | 368 | 0 |
| 2 | 6 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 44 | 4451 | 347 | 0 |
| 3 | 9 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 51 | 5862 | 377 | 0 |
| 4 | 7 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 42 | 4557 | 356 | 0 |
| 5 | 5 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 44 | 5093 | 347 | 0 |

| Paket | naechster_gefüllt | naechster_belegt | fertig_wenn_gefüllt | fertig_wenn_belegt | Annahmen_begründet | Annahmen | Anteil_Prozent |
|---|---|---|---|---|---|---|---|
| 1 | 1 | 0 | 1 | 0 | 6 | 6 | 100.00 |
| 2 | 1 | 1 | 1 | 0 | 6 | 6 | 100.00 |
| 3 | 1 | 1 | 1 | 0 | 6 | 6 | 100.00 |
| 4 | 1 | 1 | 1 | 0 | 5 | 5 | 100.00 |
| 5 | 1 | 0 | 1 | 0 | 5 | 5 | 100.00 |

wiederverwendung_eintraege: 8
| Paket | Feld | Teilstring | Überlappung | Inhaltswörter | Anteil_Prozent | Schwelle_erfüllt |
|---|---|---|---|---|---|---|
| 1 | wiederverwendung[0] | 1 | 3 | 3 | 100.00 | 1 |
| 2 | wiederverwendung[0] | 1 | 3 | 3 | 100.00 | 1 |
| 3 | wiederverwendung[0] | 1 | 3 | 3 | 100.00 | 1 |
| 3 | wiederverwendung[1] | 1 | 3 | 3 | 100.00 | 1 |
| 3 | wiederverwendung[2] | 1 | 2 | 2 | 100.00 | 1 |
| 3 | wiederverwendung[3] | 1 | 3 | 3 | 100.00 | 1 |
| 4 | wiederverwendung[0] | 1 | 1 | 1 | 100.00 | 1 |
| 5 | wiederverwendung[0] | 1 | 3 | 3 | 100.00 | 1 |

auffaelligkeiten: 7
| Paket | Feld | Art |
|---|---|---|
| 1 | naechster | annahme_statt_belegt |
| 1 | fertig_wenn | annahme_statt_belegt |
| 2 | fertig_wenn | annahme_statt_belegt |
| 3 | fertig_wenn | annahme_statt_belegt |
| 4 | fertig_wenn | annahme_statt_belegt |
| 5 | naechster | annahme_statt_belegt |
| 5 | fertig_wenn | annahme_statt_belegt |

tests_gesamt: 92
tests_bestanden: 92
tests_fehler: 0
tests_fehlgeschlagen: 0
tests_uebersprungen: 0
tests_exitcode: 0
