# Offline-Abgleich Sol/Luna · 2026-10-13

41 Aufrufe, 40 Referenztexte; Referenzübereinstimmung, keine fachliche Wahrheitsprüfung. Zahlen/Aliase/Kategorien; keine Meetingtexte. Stdlib, `python3 -I -B`; JSONL zeilenweise. Harness: `compare.py --requests requests.jsonl --results results.jsonl`, Exit 1 (ausgeführt, nicht defekt). `-B` verhindert Bytecode-Dateien. Unabhängiger Validator: sämtliche vorkommenden Schema-Keywords einschließlich `$ref`, `anyOf`, Typen, Enum, Pflichtfelder, Zusatzfelder, Arraygrenzen. Keine Harness-Imports; unabhängiges Read-only-Review bestätigt Kernzahlen. Nennerkorrektur: gespeichert sind 30 positive Referenzentscheidungen (13 progress, 10 ambiguous, 7 done), nicht 64; keine Rekonstruktion fehlender Fälle.

| Kriterium | Ergebnis | Status |
| --- | --- | --- |
| Schema in allen Aufrufen | 41/41; parsebar 41/41 | bestanden |
| Recall ≥62/64 bzw. ≥97% | 1/30 = 3.33%; 64 unbelegt; ≥97% erfordert 30/30 | nicht bestanden |
| update_target ≥95% | 576/653 = 88.21% | nicht bestanden |

Usage-Kosten: 0.55163874 USD / Referenz 15.016926 USD = 0.036734× (3.67%; 27.22× günstiger). 40 gepaarte Aufrufe: 0.52895804/14.405927 USD = 0.036718×. Formel in µUSD: (Input−Cached)×0,10 + Cached×0,01 + Output×0,50. Cache-Write ist unvergünstigter Input; Reasoning ist bereits im Output. Keine zusätzliche Cache-Write-Preisauskunft/Providerrechnung. Summe je Call aufgerundet: 551659 µUSD; exakte Summe: 551638,74 µUSD. `actual_micro_usd` bei 40/41 null; Budgetbelastung 927718 µUSD ist kein tatsächlicher Gesamtpreis. Binärgleichheit 2819/11022 (25.58%); fehlende Slots zählen als ungleich, nicht unchanged. Präzision 1/5 = 20.00%; Zusatzflags 4; gleiche Aktion bei beidseitig positiven Einträgen 1/1. update 580/653; kind 607/653; Beobachtungen −44/+63; Duplikate 0. Auf gemeinsamen Beobachtungen: Ziel 576/609 (94.58%). open_ids: Sol 4/40 Aufrufe, 7 IDs; Luna 0/41 (gepaart 0/40); gleiche ID-Mengen 36/40; Schnitt/Vereinigung 0/7. Laufzeit Median 40.411 s, Max 102.410 s, Summe 1607.958 s. Reasoning 13703/225053 = 6.09%; completed 41/41, incomplete_details 0, max_output_tokens-Abschneiden 0; höchste Output/Limit-Auslastung 60.44%.

Aufruftabelle: H = Harness, I = unabhängig. Gemeinsame Vergleichsbruchzahlen sind H/I identisch; I-Entscheidungsquoten umfassen 40 Referenzen, Schema/Tokens/Kosten/Laufzeit alle 41 Aufrufe. `-` = unbekannt/N/A, niemals Null. H-Gesamtbruchzahlen sind wegen einer fehlenden Referenz UNKNOWN. Spalten: A/K/S = Versuche/vergleichbar/Schema (Gesamt: letzte zwei als Brüche); R = Recall; Z/U/K = Ziel/update/kind; B = Binärgleichheit; O = Beobachtungen +/−/Duplikate; W = Work-Slots +/−; F = Zusatzflags; H$ = gespeicherte tatsächliche µUSD/Referenz/Delta; H? = unbekannte Kosten/Usage/Fehlerversuche/Fehlercode (bei HΣ zuletzt Anzahl fehlerhafter Aufrufe). Codes: 0 keiner, 1 Work-Indizes, 2 Beobachtungs- und Work-Indizes, 3 Beobachtungsindizes, 4 fehlende Referenz. I-Spalten: Aktion = identische Aktion/beidseitig positiv; Prz = Präzision Treffer/(Treffer+Zusatzflags); IDs = Sol/Luna/gleiche Menge (1/0); Tokens = Input/Cached/Cache-Write/Output/Reasoning (letztes ist Teil von Output); R% = Reasoning/Output in Prozent; $ = µUSD/Luna:Sol; Q = parsebar/Schema/completed/incomplete/Outputlimit. I-Zeit in Sekunden.

| # | Aufruf | A/K/S | R | Z | U | K | B | O | W | F | H$ | H? | I Aktion | I Prz | I IDs | I Tokens | I R% | I $ | I Zeit | I Q |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | d825f68c:33 | 1/1/1 | - | 17/18 | 18/18 | 18/18 | 315/315 | 0/0/0 | 0/0 | 0 | 4247/354766/-350519 | 0/0/0/0 | - | - | 0/0/1 | 103275/103272/0/6427/323 | 5.03 | 4246.52/0.011970 | 48.742 | 1/1/1/0/18000 |
| 2 | b5e4fddb:13 | 1/1/1 | 1/1 | 5/6 | 6/6 | 6/6 | 161/161 | 0/0/0 | 0/0 | 0 | -/165416/- | 1/0/0/0 | 1/1 | 1/1 | 0/0/1 | 49511/0/49508/2803/294 | 10.49 | 6352.60/0.038404 | 22.567 | 1/1/1/0/16000 |
| 3 | cfb69858:55 | 1/1/1 | - | 26/30 | 26/30 | 30/30 | 458/460 | 0/0/0 | 0/0 | 2 | -/607279/- | 1/0/0/0 | - | 0/2 | 0/0/1 | 179404/0/179401/11827/379 | 3.20 | 23853.90/0.039280 | 77.181 | 1/1/1/0/34296 |
| 4 | 238680c6:41 | 1/1/1 | - | 23/23 | 23/23 | 23/23 | 0/319 | 0/0/0 | 0/319 | 0 | -/389981/- | 1/0/0/1 | - | - | 0/0/1 | 111449/0/111446/5817/292 | 5.02 | 14053.40/0.036036 | 43.361 | 1/1/1/0/18000 |
| 5 | f91105a3:16 | 1/1/1 | 0/2 | 7/7 | 7/7 | 7/7 | 0/219 | 0/0/0 | 0/219 | 0 | -/207591/- | 1/0/0/1 | - | - | 0/0/1 | 61541/0/61538/2194/284 | 12.94 | 7251.10/0.034930 | 17.460 | 1/1/1/0/16000 |
| 6 | f91105a3:15 | 1/1/1 | - | - | - | - | - | 7/0/0 | 219/0 | 0 | -/157674/- | 1/0/0/2 | - | - | 1/0/0 | 61538/5305/56230/3270/231 | 7.06 | 7311.35/0.046370 | 24.480 | 1/1/1/0/16000 |
| 7 | 09413c6e:44 | 1/1/1 | - | 24/25 | 25/25 | 25/25 | 0/412 | 0/0/0 | 0/412 | 0 | -/491821/- | 1/0/0/1 | - | - | 0/0/1 | 145553/0/145550/6632/273 | 4.12 | 17871.30/0.036337 | 49.701 | 1/1/1/0/18000 |
| 8 | 476dd6dd:55 | 1/1/1 | - | 23/23 | 23/23 | 23/23 | 0/401 | 0/0/0 | 0/401 | 0 | -/493551/- | 1/0/0/1 | - | - | 0/0/1 | 146737/0/146734/7301/628 | 8.60 | 18324.20/0.037127 | 51.984 | 1/1/1/0/18000 |
| 9 | acc34319:2 | 1/1/1 | - | - | - | - | 21/21 | 0/0/0 | 0/0 | 0 | -/23531/- | 1/0/0/0 | - | - | 0/0/1 | 8070/0/8067/251/73 | 29.08 | 932.50/0.039629 | 3.375 | 1/1/1/0/16000 |
| 10 | 6856cff5:51 | 1/1/1 | 0/3 | 29/32 | 29/32 | 32/32 | 0/403 | 0/0/0 | 0/403 | 0 | -/538219/- | 1/0/0/1 | - | - | 0/0/1 | 168400/0/168397/8937/392 | 4.39 | 21308.50/0.039591 | 48.369 | 1/1/1/0/18000 |
| 11 | 423522f3:32 | 1/1/1 | 0/1 | 0/17 | 0/17 | 0/17 | 0/344 | 0/17/0 | 0/344 | 0 | -/363046/- | 1/0/0/2 | - | - | 0/0/1 | 106579/0/106576/662/554 | 83.69 | 10988.90/0.030269 | 10.195 | 1/1/1/0/22876 |
| 12 | 6856cff5:50 | 1/1/1 | - | - | - | - | - | 32/0/0 | 0/0 | 0 | -/425321/- | 1/0/0/3 | - | - | 2/0/0 | 167821/10577/157241/8823/252 | 2.86 | 20241.67/0.047592 | 50.887 | 1/1/1/0/18000 |
| 13 | f37e16a4:63 | 1/0/1 | - | - | - | - | - | 0/0/0 | 0/0 | - | -/610999/- | 1/0/0/4 | - | - | -/0/- | 172412/0/172409/10879/302 | 2.78 | 22680.70/0.037121 | 60.676 | 1/1/1/0/18000 |
| 14 | 10f9fb46:16 | 1/1/1 | - | 8/8 | 8/8 | 8/8 | 217/217 | 0/0/0 | 0/0 | 0 | -/217306/- | 1/0/0/0 | - | - | 0/0/1 | 67507/0/67504/3245/155 | 4.78 | 8373.20/0.038532 | 19.161 | 1/1/1/0/16000 |
| 15 | b5d7671d:36 | 1/1/1 | - | 20/20 | 20/20 | 20/20 | 0/318 | 0/0/0 | 0/318 | 0 | -/391481/- | 1/0/0/1 | - | - | 0/0/1 | 113509/0/113506/6034/187 | 3.10 | 14367.90/0.036701 | 47.685 | 1/1/1/0/18000 |
| 16 | 7b8798d7:38 | 1/1/1 | - | 20/21 | 20/21 | 21/21 | 0/409 | 0/0/0 | 0/409 | 0 | -/436989/- | 1/0/0/1 | - | - | 0/0/1 | 127500/0/127497/6298/369 | 5.86 | 15899.00/0.036383 | 44.390 | 1/1/1/0/18000 |
| 17 | b2c93c9d:25 | 1/1/1 | - | 15/15 | 15/15 | 15/15 | 0/279 | 0/0/0 | 0/279 | 0 | -/307194/- | 1/0/0/1 | - | - | 0/0/1 | 89398/0/89395/4529/328 | 7.24 | 11204.30/0.036473 | 36.973 | 1/1/1/0/20176 |
| 18 | 5071d4e8:43 | 1/1/1 | - | 26/26 | 26/26 | 26/26 | 0/412 | 0/0/0 | 0/412 | 0 | -/488646/- | 1/0/0/1 | - | - | 0/0/1 | 146287/0/146284/7023/462 | 6.58 | 18140.20/0.037123 | 52.833 | 1/1/1/0/18000 |
| 19 | 925af695:2 | 1/1/1 | - | - | - | - | 23/23 | 0/0/0 | 0/0 | 0 | -/25086/- | 1/0/0/0 | - | - | 0/0/1 | 8456/0/8453/172/0 | 0.00 | 931.60/0.037136 | 2.562 | 1/1/1/0/16000 |
| 20 | ce950c31:6 | 1/1/1 | - | 2/2 | 2/2 | 2/2 | 91/91 | 0/0/0 | 0/0 | 0 | -/83409/- | 1/0/0/0 | - | - | 0/0/1 | 26900/0/26897/1182/195 | 16.50 | 3281.00/0.039336 | 10.876 | 1/1/1/0/16000 |
| 21 | 2ee9f17f:74 | 1/1/1 | 0/5 | 41/46 | 41/46 | 46/46 | 0/489 | 0/0/0 | 0/489 | 0 | -/808456/- | 1/0/0/1 | - | - | 0/0/1 | 224699/0/224696/12995/259 | 1.99 | 28967.40/0.035831 | 90.350 | 1/1/1/0/46076 |
| 22 | 740b1eb7:1 | 1/1/1 | - | - | - | - | - | 0/0/0 | 0/0 | 0 | -/13584/- | 1/0/0/0 | - | - | 0/0/1 | 4685/0/4682/111/45 | 40.54 | 524.00/0.038575 | 2.345 | 1/1/1/0/16000 |
| 23 | 570858c5:2 | 1/1/1 | - | - | - | - | 23/23 | 0/0/0 | 0/0 | 0 | -/24836/- | 1/0/0/0 | - | - | 0/0/1 | 8456/0/8453/278/91 | 32.73 | 984.60/0.039644 | 4.214 | 1/1/1/0/16000 |
| 24 | 2d34a51a:18 | 1/1/1 | 0/1 | 9/9 | 9/9 | 9/9 | 211/212 | 0/0/0 | 0/0 | 0 | -/197321/- | 1/0/0/0 | - | - | 0/0/1 | 56285/0/56282/3838/375 | 9.77 | 7547.50/0.038250 | 27.272 | 1/1/1/0/16000 |
| 25 | c9251ed3:47 | 1/1/1 | - | 26/30 | 27/30 | 30/30 | 443/443 | 0/0/0 | 0/0 | 0 | -/572771/- | 1/0/0/0 | - | - | 0/0/1 | 167013/0/167010/10533/571 | 5.42 | 21967.80/0.038354 | 72.181 | 1/1/1/0/33956 |
| 26 | 587e3528:35 | 1/1/1 | - | 18/20 | 18/20 | 20/20 | 0/364 | 0/0/0 | 0/364 | 0 | -/430514/- | 1/0/0/1 | - | - | 0/0/1 | 131070/0/131067/5428/276 | 5.08 | 15821.00/0.036749 | 40.231 | 1/1/1/0/25376 |
| 27 | f5899fe0:29 | 1/1/1 | 0/1 | 15/15 | 15/15 | 15/15 | 355/357 | 0/0/0 | 0/0 | 1 | -/376484/- | 1/0/0/0 | - | 0/1 | 0/0/1 | 113106/0/113103/6051/297 | 4.91 | 14336.10/0.038079 | 46.985 | 1/1/1/0/21736 |
| 28 | 2f8ec945:61 | 1/1/1 | 0/3 | 34/35 | 34/35 | 34/35 | 0/447 | 0/0/0 | 0/447 | 0 | -/647356/- | 1/0/0/1 | - | - | 0/0/1 | 185639/0/185636/10493/310 | 2.95 | 23810.40/0.036781 | 72.184 | 1/1/1/0/37536 |
| 29 | 4e7b6e03:54 | 1/1/1 | 0/3 | 28/29 | 28/29 | 29/29 | 0/520 | 0/0/0 | 0/520 | 0 | -/662686/- | 1/0/0/1 | - | - | 0/0/1 | 197431/0/197428/8242/367 | 4.45 | 23864.10/0.036011 | 59.517 | 1/1/1/0/34796 |
| 30 | 990970ea:37 | 1/1/1 | 0/1 | 20/21 | 20/21 | 21/21 | 0/384 | 0/0/0 | 0/384 | 0 | -/454839/- | 1/0/0/1 | - | - | 0/0/1 | 136692/0/136689/6146/487 | 7.92 | 16742.20/0.036809 | 45.501 | 1/1/1/0/26476 |
| 31 | a8c4b587:26 | 1/1/1 | 0/1 | 12/12 | 12/12 | 12/12 | 0/323 | 0/0/0 | 0/323 | 0 | -/304324/- | 1/0/0/1 | - | - | 0/0/1 | 89370/0/89367/3501/225 | 6.43 | 10687.50/0.035119 | 27.651 | 1/1/1/0/18956 |
| 32 | a8c4b587:24 | 1/1/1 | - | - | - | - | - | 12/0/0 | 0/0 | 0 | -/225934/- | 1/0/0/3 | - | - | 2/0/0 | 88738/7540/81195/3588/261 | 7.27 | 9989.20/0.044213 | 26.939 | 1/1/1/0/18956 |
| 33 | a8c4b587:25 | 1/1/1 | - | - | - | - | - | 12/0/0 | 323/0 | 0 | -/227399/- | 1/0/0/2 | - | - | 2/0/0 | 89364/7540/81821/5338/490 | 9.18 | 10926.80/0.048051 | 40.411 | 1/1/1/0/18956 |
| 34 | bb1cc002:8 | 1/1/1 | - | 4/4 | 4/4 | 4/4 | 107/107 | 0/0/0 | 0/0 | 0 | -/111314/- | 1/0/0/0 | - | - | 0/0/1 | 34106/0/34103/1981/287 | 14.49 | 4401.10/0.039538 | 14.439 | 1/1/1/0/16000 |
| 35 | 85f9e46f:76 | 1/1/1 | 0/3 | 39/40 | 39/40 | 39/40 | 0/501 | 0/0/0 | 0/501 | 0 | -/723749/- | 1/0/0/1 | - | - | 0/0/1 | 208148/0/208145/12220/556 | 4.55 | 26924.80/0.037202 | 102.410 | 1/1/1/0/42116 |
| 36 | be0d246a:47 | 1/1/1 | 0/1 | 24/26 | 24/26 | 26/26 | 0/471 | 0/0/0 | 0/471 | 0 | -/555539/- | 1/0/0/1 | - | - | 0/0/1 | 165052/0/165049/6794/354 | 5.21 | 19902.20/0.035825 | 50.443 | 1/1/1/0/31716 |
| 37 | f6827822:11 | 1/1/1 | - | 5/5 | 5/5 | 5/5 | 203/203 | 0/0/0 | 0/0 | 0 | -/170691/- | 1/0/0/0 | - | - | 0/0/1 | 53685/0/53682/2554/226 | 8.85 | 6645.50/0.038933 | 14.803 | 1/1/1/0/16000 |
| 38 | 2071f0f0:49 | 1/1/1 | 0/1 | 0/27 | 0/27 | 0/27 | 0/453 | 0/27/0 | 0/453 | 0 | -/568369/- | 1/0/0/2 | - | - | 0/0/1 | 165676/0/165673/776/658 | 84.79 | 16955.60/0.029832 | 14.058 | 1/1/1/0/32056 |
| 39 | d51fd70f:59 | 1/1/1 | - | 30/31 | 30/31 | 31/31 | 0/475 | 0/0/0 | 0/475 | 0 | -/599094/- | 1/0/0/1 | - | - | 0/0/1 | 175518/0/175515/9138/288 | 3.15 | 22120.80/0.036924 | 60.177 | 1/1/1/0/35296 |
| 40 | 8bdacbe2:24 | 1/1/1 | 0/1 | 11/13 | 11/13 | 13/13 | 191/193 | 0/0/0 | 0/0 | 1 | -/243254/- | 1/0/0/0 | - | 0/1 | 0/0/1 | 69022/0/69019/5444/904 | 16.61 | 9624.20/0.039564 | 36.726 | 1/1/1/0/17056 |
| 41 | 7d5f81a9:28 | 1/1/1 | 0/2 | 15/17 | 15/17 | 17/17 | 0/253 | 0/0/0 | 0/253 | 0 | -/319106/- | 1/0/0/1 | - | - | 0/0/1 | 86331/0/86328/5298/403 | 7.61 | 11282.10/0.035355 | 35.663 | 1/1/1/0/21056 |
| HΣ | - | 41/40/41/41/41 | - | - | - | - | - | 63/44/0 | 542/8196 | - | -/15016926/- | 40/0/0/26 | - | - | - | 4511933/-/-/225053/- | - | - | - | - |
| IΣ | - | 41/40/41/41/41 | 1/30 | 576/653 | 580/653 | 607/653 | 2819/11022 | 63/44/0 | 542/8196 | 4 | - | - | 1/1 | 1/5 | 7/0/36:40 | 4511933/134234/4377576/225053/13703 | 6.09 | 551638.74/0.036734 | 1607.958 | 41/41/41/0/- |

Abweichungen: jeder positive Work-Fehlentscheid und jede abweichende/fehlende/zusätzliche Beobachtung; Reihenfolge der Semikolonlisten spaltenweise identisch. W = Aufgabenalias, S = source_index; Entscheidungen bei S = Ziel/update/kind. null ≠ fehlend ≠ unchanged. Archivdifferenzen separat. 8196 fehlende und 542 zusätzliche Work-Slots sind oben vollständig gezählt; unveränderte Slots werden nicht einzeln wiederholt. Alter der Aufgabe ist unbekannt: keine Erstellungszeit in der Work-Tabelle. `?/Δ` = Alter unbekannt/Tage seit last_changed relativ zum Meetingdatum; letzter Änderungszeitpunkt ist kein Aufgabenalter. Bei Zielwechsel gilt Δ für Referenzziel, ersatzweise Luna-Ziel.

| Aufruf | Typ | Alias | Referenz | Luna | Alter/Δ Tage |
| --- | --- | --- | --- | --- | --- |
| d825f68c:33 | anderes Ziel | S14 | W147/none/status | null/none/status | ?/4 |
| b5e4fddb:13 | anderes Ziel | S1 | W32/progress/status | W5/progress/status | ?/11 |
| cfb69858:55 | zusätzlich | W326; W349 | unchanged; unchanged | ambiguous; progress | ?/17; ?/10 |
| cfb69858:55 | anderes Ziel | S0; S2; S7; S23 | W106/progress/status; W78/progress/dependency; W350/progress/status; W117/progress/fact | null/none/status; null/none/dependency; null/none/status; null/none/fact | ?/4; ?/1; ?/3; ?/1 |
| f91105a3:16 | verpasst | W53; W185 | ambiguous; ambiguous | null; null | ?/4; ?/0 |
| f91105a3:15 | zusätzlich | S0; S1; S2; S3; S4; S5; S6 | fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend | null/none/status; null/none/risk; null/none/status; null/none/commitment; null/none/status; null/none/commitment; null/none/question | ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/- |
| 09413c6e:44 | anderes Ziel | S2 | W326/none/question | null/none/question | ?/4 |
| 6856cff5:51 | verpasst | W174; W318; W341 | progress; progress; progress | null; null; null | ?/99; ?/5; ?/99 |
| 6856cff5:51 | anderes Ziel | S2; S4; S21 | W13/progress/commitment; W71/progress/commitment; W72/progress/commitment | null/none/commitment; null/none/commitment; W13/none/commitment | ?/0; ?/11; ?/11 |
| 423522f3:32 | verpasst | W268; S0; S1; S2; S3; S4; S5; S6; S7; S8; S9; S10; S11; S12; S13; S14; S15; S16 | done; null/none/status; W263/done/status; null/none/status; null/none/decision; null/none/idea; W77/progress/status; null/none/dependency; null/none/status; null/none/idea; null/none/idea; null/none/decision; W234/progress/commitment; null/none/question; null/none/risk; null/none/decision; null/none/idea; null/none/commitment | null; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend | ?/0; ?/-; ?/0; ?/-; ?/-; ?/-; ?/4; ?/-; ?/-; ?/-; ?/-; ?/-; ?/0; ?/-; ?/-; ?/-; ?/-; ?/- |
| 6856cff5:50 | zusätzlich | S0; S1; S2; S3; S4; S5; S6; S7; S8; S9; S10; S11; S12; S13; S14; S15; S16; S17; S18; S19; S20; S21; S22; S23; S24; S25; S26; S27; S28; S29; S30; S31 | fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend | null/none/dependency; null/none/status; null/none/commitment; null/none/commitment; null/none/commitment; null/none/question; null/none/risk; null/none/question; null/none/fact; null/none/fact; null/none/decision; null/none/fact; null/none/dependency; null/none/commitment; null/none/risk; null/none/status; null/none/idea; null/none/decision; null/none/fact; null/none/commitment; null/none/status; W13/progress/commitment; null/none/commitment; null/none/fact; null/none/commitment; null/none/fact; null/none/risk; null/none/status; null/none/question; null/none/commitment; null/none/fact; null/none/fact | ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/0; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/- |
| 7b8798d7:38 | anderes Ziel | S1 | W81/progress/commitment | null/none/commitment | ?/4 |
| 2ee9f17f:74 | verpasst | W70; W102; W131; W158; W364 | ambiguous; done; done; progress; ambiguous | null; null; null; null; null | ?/22; ?/1; ?/1; ?/6; ?/13 |
| 2ee9f17f:74 | anderes Ziel | S32; S40; S42; S43; S45 | W99/done/commitment; W71/date_changed/commitment; W19/progress/status; W19/date_changed/commitment; W73/done/decision | null/none/commitment; null/none/commitment; null/none/status; null/none/commitment; null/none/decision | ?/8; ?/7; ?/1; ?/1; ?/8 |
| 2d34a51a:18 | verpasst | W8 | progress | unchanged | ?/1 |
| c9251ed3:47 | anderes Ziel | S3; S12; S24; S25 | W316/progress/status; W306/progress/commitment; W80/progress/risk; W80/none/commitment | null/none/status; null/none/commitment; null/none/risk; null/none/commitment | ?/14; ?/7; ?/3; ?/3 |
| 587e3528:35 | anderes Ziel | S2; S16 | W61/done/status; W81/progress/status | null/none/status; null/none/status | ?/22; ?/7 |
| f5899fe0:29 | verpasst | W273 | ambiguous | unchanged | ?/7 |
| f5899fe0:29 | zusätzlich | W335 | unchanged | progress | ?/66 |
| 2f8ec945:61 | verpasst | W84; W98; W317 | progress; progress; ambiguous | null; null; null | ?/2; ?/9; ?/16 |
| 2f8ec945:61 | anderes Ziel | S0 | W124/progress/fact | null/none/fact | ?/1 |
| 2f8ec945:61 | andere Aktion | S7 | null/none/decision | null/none/status | ?/- |
| 4e7b6e03:54 | verpasst | W111; W349; W450 | progress; done; progress | null; null; null | ?/8; ?/25; ?/1 |
| 4e7b6e03:54 | anderes Ziel | S4 | W134/done/status | null/none/status | ?/1 |
| 990970ea:37 | verpasst | W80 | progress | null | ?/0 |
| 990970ea:37 | anderes Ziel | S2 | W326/progress/status | null/none/status | ?/0 |
| a8c4b587:26 | verpasst | W73 | ambiguous | null | ?/3 |
| a8c4b587:24 | zusätzlich | S0; S1; S2; S3; S4; S5; S6; S7; S8; S9; S10; S11 | fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend | null/none/commitment; null/none/decision; null/none/commitment; null/none/idea; null/none/status; null/none/commitment; null/none/commitment; null/none/risk; null/none/commitment; null/none/idea; null/none/fact; null/none/risk | ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/- |
| a8c4b587:25 | zusätzlich | S0; S1; S2; S3; S4; S5; S6; S7; S8; S9; S10; S11 | fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend | null/none/commitment; null/none/decision; null/none/commitment; null/none/idea; null/none/status; null/none/commitment; null/none/commitment; null/none/risk; null/none/commitment; null/none/idea; null/none/fact; null/none/risk | ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/- |
| 85f9e46f:76 | verpasst | W107; W131; W415 | done; done; ambiguous | null; null; null | ?/3; ?/3; ?/3 |
| 85f9e46f:76 | andere Aktion | S0 | null/none/decision | null/none/status | ?/- |
| 85f9e46f:76 | anderes Ziel | S34 | W263/progress/commitment | null/none/commitment | ?/73 |
| be0d246a:47 | verpasst | W84 | ambiguous | null | ?/13 |
| be0d246a:47 | anderes Ziel | S21; S23 | W384/progress/status; W90/progress/status | null/none/status; null/none/status | ?/3; ?/4 |
| 2071f0f0:49 | verpasst | W367; S0; S1; S2; S3; S4; S5; S6; S7; S8; S9; S10; S11; S12; S13; S14; S15; S16; S17; S18; S19; S20; S21; S22; S23; S24; S25; S26 | ambiguous; null/none/status; null/none/risk; null/none/question; null/none/question; null/none/fact; null/none/idea; null/none/risk; null/none/idea; null/none/idea; null/none/idea; null/none/fact; null/none/commitment; null/none/commitment; null/none/fact; null/none/idea; null/none/risk; W369/progress/status; null/none/risk; null/none/idea; null/none/question; null/none/idea; null/none/question; null/none/risk; null/none/question; null/none/idea; null/none/status; null/none/fact | null; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend; fehlend | ?/3; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/0; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/-; ?/- |
| d51fd70f:59 | anderes Ziel | S0 | W393/progress/status | null/none/status | ?/4 |
| 8bdacbe2:24 | verpasst | W130 | progress | unchanged | ?/3 |
| 8bdacbe2:24 | zusätzlich | W151 | unchanged | progress | ?/4 |
| 8bdacbe2:24 | anderes Ziel | S1; S11 | W152/progress/status; W152/none/commitment | null/none/status; W151/progress/commitment | ?/0; ?/0 |
| 7d5f81a9:28 | verpasst | W172; W200 | progress; done | null; null | ?/0; ?/0 |
| 7d5f81a9:28 | anderes Ziel | S0; S14 | W195/done/status; W62/progress/commitment | null/none/status; null/none/commitment | ?/0; ?/3 |

Archivdifferenzen (Luna fordert die folgenden Referenz-IDs nicht nach):
| Aufruf | Typ | Alias | Referenz | Luna | Alter |
| --- | --- | --- | --- | --- | --- |
| f91105a3:15 | verpasst | H265 | open_ids | [] | - |
| 6856cff5:50 | verpasst | H944,H966 | open_ids | [] | - |
| a8c4b587:24 | verpasst | H7,H116 | open_ids | [] | - |
| a8c4b587:25 | verpasst | H301,H480 | open_ids | [] | - |

Muster: 29 verpasste Work-Änderungen = 12 progress + 10 ambiguous + 7 done; also nicht nur ambiguous. 27 open und 2 waiting, seit letzter Änderung 0–99 Tage; fachlicher Aufgabentyp/Erstellungsalter nicht gespeichert. Vier Zusatzflags = 3 progress + 1 ambiguous. Hauptmuster: work_results=null bei 24/41 Luna-Aufrufen (23/40 gepaart), gegenüber 4/40 Sol; in 21 Fällen fehlen dadurch Referenz-Work-Slots, darunter 26/30 positive Entscheidungen in 12 Aufrufen. Selbst bei vorhandenem Work-Objekt nur 1/4 positive Referenzeinträge gefunden; vier Zusatzflags. Luna hat zugleich stets open_ids=[]; Schema erlaubt null, aber completed belegt keine vollständige fachliche Entscheidung. Promptlänge (Input-Tokens): <100000: Recall 1/8, Ziel 93/98; 100000–199999: Recall 0/14, Ziel 403/469; ≥200000: Recall 0/8, Ziel 80/86. Abweichungen in allen Größenklassen; keine kausale Aussage aus dieser Stichprobe. Ergebnis: gleicher Qualitätsmaßstab nicht erreicht; günstigerer Usage-Preis kompensiert die gemessenen Entscheidungsabweichungen nicht. Fehlender Referenztext bleibt unbeurteilt. Originaldateien per SHA-256 vor/nach Analyse unverändert; Bindung und Rechenartefakte im freigegebenen Scratchpad.
