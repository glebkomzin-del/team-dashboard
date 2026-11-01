# Produktionsränge: lokale Kandidatenfilter-Validierung

Stand: 2026-10-13. Ausschließlich lokale Archiv- und Replay-Auswertung mit Python-Standardbibliothek (`python3 -I`); keine Netzwerk-/API-Aufrufe, Installation oder Produktionsänderung. Meetingtexte, Titel, Claims und echte Aufgaben-IDs werden in diesem Bericht nicht ausgegeben.

## Ergebnis

**Empfehlung im geprüften Raster: A=30, k=5.** Die separate Produktions-Work-Liste liefert dabei **64/64 Recall (100,00 %) bei 6.002/12.223 behaltenen Kandidaten (49,10 %)**. Dies ist eine Empfehlung auf Basis der historischen Stichprobe, keine Garantie für zukünftige Meetings.

Bei A=21,k=5 erreicht die Produktions-Work-Liste **63/64 (98,44 %) bei 5.393/12.223 (44,12 %)**. Gegenüber dem früheren Cosine/Lexikal-Maß (64/64; 6.632/12.223 = 54,258365 %) ist der Recall schlechter, die Kandidatenreduktion stärker. Die Produktionsränge sind somit kein gleichwertiger Ersatz mit unverändertem A=21,k=5. Mit A=30,k=5 wird derselbe belegte Recall mit 630 weniger Kandidaten erreicht (5,16 Prozentpunkte weniger behaltener Anteil).

## Rekonstruktion und Stichprobe

- Replay: 41 Zeilen; 40 auswertbare Aufrufe, eine Fehlerzeile ohne Kandidaten-/Beobachtungsdaten. 36 Aufrufe mit Beobachtungen, 32 verschiedene Jobs. Vier weitere gültige Aufrufe ohne Beobachtungen sind nicht im Vergleichsraster; ihre 67 Kandidaten werden separat auf Identität geprüft.
- Vergleichsraster: 12.223 Kandidatenvorkommen, 64 belegte genutzte Vorkommen; 30 reine Lebenszyklusänderungen und 34 Beobachtungsziele, keine Überschneidung. Zähleinheit ist (Aufruf, Alias), nicht eine global eindeutige Aufgaben-ID.
- Suchrekonstruktion: **36/36 Aufrufe mit Beobachtungen (100 %), 716/716 Beobachtungsanfragen (100 %)**. Die 716 Vorkommen enthalten 653 verschiedene Suchtexte. Pro Vorkommen sind beide Produktionssuchlisten eindeutig rekonstruiert: 716 Work- und 716 gemischte Listen.
- Alle 653 archivierten Query-Embedding-Aufrufe liefern zwei exakt passende Hashes für das Limit 20: 1.306 Hash-Zuordnungen. Keine Hash-Zuordnung beruht auf Scores, Nachbarschaftsberechnung oder Textähnlichkeit.
- Jede Anfrage besitzt innerhalb des belegten Zeitfensters genau ein archiviertes Ergebnis pro Suchart. Beide Listen gehören zum selben Snapshot; alle Beobachtungen eines Aufrufs ebenfalls. Alle Treffer-IDs sind im Snapshot enthalten; ihre target_id entspricht dem archivierten Work-Dokument.
- Identität: **12.290/12.290 Kandidatenvorkommen aus 40 gültigen Aufrufen zugeordnet**, davon alle 12.223 im Raster. 693 unterschiedliche Titel-/Claim-Paare; 691 global eindeutig und zwei global mehrdeutig (5 bzw. 7 echte Aufgaben-IDs). Die beiden mehrdeutigen Paare betreffen 23 Vorkommen; Snapshot-Mitgliedschaft reduziert jedes auf genau eine echte ID. Verbleibende Mehrdeutigkeiten oder fehlende Zuordnungen: **0**.
- Wörtliche IDs: Direktprüfung der vollständigen, im Abgleich-Prompt enthaltenen Originalzeilen aller 40 gültigen Aufrufe gegen sämtliche 706 archivierten Work-Identitäten. **0 wörtliche Aufgaben-IDs**. Regel (c) ist für diese Stichprobe leer; (a)∨(b) und (a)∨(b)∨(c) sind deshalb zahlenmäßig identisch.
- Vier Aufrufe sind Öffnungs-Zwischenrunden mit insgesamt 1.268 Kandidaten, aber ohne work_results-Slots: 0 Slots und nichtleere open_ids. Fehlende Slots werden nicht als Änderungen oder als belegtes unchanged ausgelegt. Wie in der früheren Messung bleiben diese Aufrufe im Kandidaten-Nenner; der Recall bezieht sich auf die 64 belegten genutzten Aufgaben. Eine Sensitivität nur für abschließende Aufrufe steht unten.

## Hash, Zeitfenster und Rangdefinition

`hybrid_index.py` bildet aus title, subject und search_keywords den Suchtext mit genau einem verbindenden Leerzeichen; es sendet den unveränderten Text und den archivierten Query-Vektor an `search_query`. Sein SHA-256-digest allein definiert nicht den Query-Hash: Der Server bildet diesen in der SQL-Suchfunktion.

```text
query = " ".join([title, subject, *search_keywords])
query_hash = SHA256(UTF8(jsonb_build_array(
    "hnsw-plan-v2", query, query_embedding::text, kinds, 20
)::text))
```

Die Hash-Nachbildung verwendet die PostgreSQL-jsonb-Arraydarstellung mit Leerzeichen und den pgvector-float32-Vektortext. Jede Komponente wird auf IEEE-754-float32 gerundet und mit der kürzesten dezimalen Roundtrip-Darstellung serialisiert. Die exakte Übereinstimmung aller 1.306 Hash-Zuordnungen ist der Nachweis für diese Nachbildung, nicht eine Annahme über Text-Hashing.

Zuordnung: Embedding-Call mit identischem job_id und exakt identischem Suchtext; anschließend `embedding.created_at ≤ search_result.created_at ≤ compact_call.created_at`. Innerhalb dieses Fensters ist pro Suchart genau ein Resultat vorhanden. Snapshot-Erstellungszeit, Mitgliedschaft und gemeinsame Snapshot-ID werden zusätzlich geprüft. Es wird kein zeitlich nächstes Ergebnis geraten.

Die Hauptmessung verwendet die **separate Work-Liste** aus `index.search(query, ["work"], 20)`. Rang ist die unveränderte, nullbasierte Arrayposition des archivierten Suchergebnisses. Bei mehreren Dokumentteilen derselben Aufgabe gilt die kleinste Arrayposition; es wird weder nach Alias sortiert noch nach Entfernung anderer Treffer neu nummeriert. Im rekonstruierten Top-20-Bereich gibt es keine doppelte Work-target_id innerhalb einer Liste.

Die archivierte SQL-Fassung liefert trotz Parameter 20 die Vereinigung aus lexikalischen und Vektortreffern: **715/716 Work-Listen haben mehr als 20 Resultate**. Der Filter testet streng `rank < k`; bei k≤20 sind Positionen ≥20 ausgeschlossen. Die angeforderte Rangliste 0–19 wird als Top-20-Ausschnitt des unveränderten Arrays gespeichert. Beim verpassten Fall wird zusätzlich der tatsächlich archivierte Rang 30 ausgewiesen. Die SQL-Ausgabe wird nicht repariert oder neu gerankt.

Weil die Produktion auch die gemischte Liste abfragt, enthält dieser Bericht ein zweites vollständiges Raster mit `min(Work-Arrayposition, gemischter Arrayposition)`. Bei der gemischten Liste zählt die ursprüngliche Position einschließlich aller Nicht-Work-Treffer. Beide Interpretationen verwenden echte Produktionsränge; ihre Recalls und die Empfehlung sind im geprüften Raster identisch.

## Filter und Nenner

Alter = meeting_date − last_changed in Kalendertagen. Keine fehlenden Datumswerte; Alter 0–133 Tage. Verwendet wird `age ≤ A`, einschließlich abgeschlossener Aufgaben. Rangregel = mindestens eine Beobachtungsanfrage mit Work-Rang `< k`; k=0 behält über Rang keine Aufgabe.

Genutzt = ein tatsächlich vorhandener work_results-Eintrag ungleich `unchanged` (Zuordnung über work_index), oder Alias als update_target in obs_out. Fehlende Slots erfüllen diese Bedingung nicht. Recall = behaltene genutzte Vorkommen / 64. Behaltener Anteil = behaltene Kandidatenvorkommen / 12.223; dies ist keine gemessene Token- oder Kostenersparnis.

## Raster: (a)∨(b)∨(c), separate Work-Liste

Zelle: Recall mit Zähler/Nenner; behaltener Anteil mit Zähler/Nenner. Wegen leerem (c) zugleich das geforderte Raster für (a)∨(b).

| A / k | 0 | 1 | 3 | 5 | 8 | 12 | 20 |
|---:|---|---|---|---|---|---|---|
| 0 | 12/64 (18,75 %); 167/12223 (1,37 %) | 38/64 (59,38 %); 706/12223 (5,78 %) | 48/64 (75,00 %); 1575/12223 (12,89 %) | 52/64 (81,25 %); 2341/12223 (19,15 %) | 53/64 (82,81 %); 3415/12223 (27,94 %) | 56/64 (87,50 %); 4665/12223 (38,17 %) | 60/64 (93,75 %); 6922/12223 (56,63 %) |
| 7 | 46/64 (71,88 %); 2135/12223 (17,47 %) | 54/64 (84,38 %); 2537/12223 (20,76 %) | 58/64 (90,62 %); 3236/12223 (26,47 %) | 61/64 (95,31 %); 3869/12223 (31,65 %) | 62/64 (96,88 %); 4703/12223 (38,48 %) | 63/64 (98,44 %); 5745/12223 (47,00 %) | 64/64 (100,00 %); 7642/12223 (62,52 %) |
| 14 | 57/64 (89,06 %); 3571/12223 (29,22 %) | 59/64 (92,19 %); 3889/12223 (31,82 %) | 62/64 (96,88 %); 4470/12223 (36,57 %) | 63/64 (98,44 %); 4993/12223 (40,85 %) | 63/64 (98,44 %); 5699/12223 (46,63 %) | 63/64 (98,44 %); 6568/12223 (53,73 %) | 64/64 (100,00 %); 8217/12223 (67,23 %) |
| 21 | 58/64 (90,62 %); 4092/12223 (33,48 %) | 60/64 (93,75 %); 4381/12223 (35,84 %) | 62/64 (96,88 %); 4905/12223 (40,13 %) | 63/64 (98,44 %); 5393/12223 (44,12 %) | 63/64 (98,44 %); 6039/12223 (49,41 %) | 63/64 (98,44 %); 6848/12223 (56,03 %) | 64/64 (100,00 %); 8389/12223 (68,63 %) |
| 30 | 61/64 (95,31 %); 4891/12223 (40,01 %) | 62/64 (96,88 %); 5124/12223 (41,92 %) | 63/64 (98,44 %); 5592/12223 (45,75 %) | 64/64 (100,00 %); 6002/12223 (49,10 %) | 64/64 (100,00 %); 6547/12223 (53,56 %) | 64/64 (100,00 %); 7250/12223 (59,31 %) | 64/64 (100,00 %); 8622/12223 (70,54 %) |

## (a) allein

| A | Genutzt / Recall | Behalten / Anteil | Lebenszyklus | Ziel |
|---:|---|---|---:|---:|
| 0 | 12/64; 18,75 % | 167/12223; 1,37 % | 5/30 | 7/34 |
| 7 | 46/64; 71,88 % | 2135/12223; 17,47 % | 20/30 | 26/34 |
| 14 | 57/64; 89,06 % | 3571/12223; 29,22 % | 25/30 | 32/34 |
| 21 | 58/64; 90,62 % | 4092/12223; 33,48 % | 26/30 | 32/34 |
| 30 | 61/64; 95,31 % | 4891/12223; 40,01 % | 28/30 | 33/34 |

## (b) allein, separate Work-Liste

| k | Genutzt / Recall | Behalten / Anteil | Lebenszyklus | Ziel |
|---:|---|---|---:|---:|
| 0 | 0/64; 0,00 % | 0/12223; 0,00 % | 0/30 | 0/34 |
| 1 | 31/64; 48,44 % | 556/12223; 4,55 % | 12/30 | 19/34 |
| 3 | 42/64; 65,62 % | 1446/12223; 11,83 % | 17/30 | 25/34 |
| 5 | 50/64; 78,12 % | 2229/12223; 18,24 % | 21/30 | 29/34 |
| 8 | 53/64; 82,81 % | 3321/12223; 27,17 % | 24/30 | 29/34 |
| 12 | 56/64; 87,50 % | 4591/12223; 37,56 % | 26/30 | 30/34 |
| 20 | 60/64; 93,75 % | 6871/12223; 56,21 % | 29/30 | 31/34 |

## Verpasste genutzte Aufgaben: A=21, k=5

| Job-Alias | Aufrufindex | Work-Alias | Alter | Art | Bester Rang |
|---|---:|---|---:|---|---:|
| 4e7b6e03 | 54 | W349 | 25 | Lebenszyklus | 12 |

Ränge je Beobachtung des verpassten Falls; O0 bezeichnet die erste Beobachtung im Replay. `—` bedeutet in der vollständigen archivierten Work-Liste nicht enthalten. Rang 30 ist ein belegter Treffer außerhalb des angeforderten Top-20-Ausschnitts.

| Beobachtungsalias | Originaler Work-Rang |
|---|---:|
| O0 | 12 |
| O1 | — |
| O2 | 30 |
| O3 | — |
| O4 | — |
| O5 | — |
| O6 | — |
| O7 | — |
| O8 | — |
| O9 | — |
| O10 | 18 |
| O11 | — |
| O12 | — |
| O13 | — |
| O14 | — |
| O15 | — |
| O16 | — |
| O17 | — |
| O18 | — |
| O19 | — |
| O20 | — |
| O21 | — |
| O22 | — |
| O23 | — |
| O24 | 19 |
| O25 | — |
| O26 | — |
| O27 | — |
| O28 | — |

Bei A=21,k=3 werden zwei Lebenszyklusfälle verpasst: 6856cff5/W341 (Alter 99, bester Rang 4) und 4e7b6e03/W349 (Alter 25, bester Rang 12). Bei k=5 und k=8 bleibt nur W349 verpasst. Alle 34 Beobachtungsziele bleiben bereits bei A=21,k=3 erhalten.

## Sensitivität: beide Produktionssuchlisten

Hier bedeutet (b) mindestens eine ursprüngliche Arrayposition < k in einer der beiden Listen einer Beobachtungsanfrage. Kein Herausfiltern und Neu-Nummerieren gemischter Treffer.

| A / k | 0 | 1 | 3 | 5 | 8 | 12 | 20 |
|---:|---|---|---|---|---|---|---|
| 0 | 12/64 (18,75 %); 167/12223 (1,37 %) | 38/64 (59,38 %); 710/12223 (5,81 %) | 48/64 (75,00 %); 1584/12223 (12,96 %) | 52/64 (81,25 %); 2353/12223 (19,25 %) | 53/64 (82,81 %); 3417/12223 (27,96 %) | 56/64 (87,50 %); 4665/12223 (38,17 %) | 60/64 (93,75 %); 6922/12223 (56,63 %) |
| 7 | 46/64 (71,88 %); 2135/12223 (17,47 %) | 54/64 (84,38 %); 2539/12223 (20,77 %) | 58/64 (90,62 %); 3244/12223 (26,54 %) | 61/64 (95,31 %); 3881/12223 (31,75 %) | 62/64 (96,88 %); 4705/12223 (38,49 %) | 63/64 (98,44 %); 5745/12223 (47,00 %) | 64/64 (100,00 %); 7642/12223 (62,52 %) |
| 14 | 57/64 (89,06 %); 3571/12223 (29,22 %) | 59/64 (92,19 %); 3891/12223 (31,83 %) | 62/64 (96,88 %); 4478/12223 (36,64 %) | 63/64 (98,44 %); 5002/12223 (40,92 %) | 63/64 (98,44 %); 5701/12223 (46,64 %) | 63/64 (98,44 %); 6568/12223 (53,73 %) | 64/64 (100,00 %); 8217/12223 (67,23 %) |
| 21 | 58/64 (90,62 %); 4092/12223 (33,48 %) | 60/64 (93,75 %); 4383/12223 (35,86 %) | 62/64 (96,88 %); 4913/12223 (40,19 %) | 63/64 (98,44 %); 5402/12223 (44,20 %) | 63/64 (98,44 %); 6041/12223 (49,42 %) | 63/64 (98,44 %); 6848/12223 (56,03 %) | 64/64 (100,00 %); 8389/12223 (68,63 %) |
| 30 | 61/64 (95,31 %); 4891/12223 (40,01 %) | 62/64 (96,88 %); 5125/12223 (41,93 %) | 63/64 (98,44 %); 5598/12223 (45,80 %) | 64/64 (100,00 %); 6010/12223 (49,17 %) | 64/64 (100,00 %); 6549/12223 (53,58 %) | 64/64 (100,00 %); 7250/12223 (59,31 %) | 64/64 (100,00 %); 8622/12223 (70,54 %) |

Bei A=21,k=5 ergibt das 63/64 bei 5.402/12.223 (44,20 %); bei A=30,k=5 sind es 64/64 bei 6.010/12.223 (49,17 %). Der Schluss zum Recall-Verlust bei unverändertem A=21,k=5 und die Empfehlung A=30,k=5 ändern sich nicht.

## Sensitivität: abschließende Aufrufe

Die vier Öffnungs-Zwischenrunden ohne Slots werden hier aus dem Kandidaten-Nenner entfernt. Es bleiben 32 abschließende Aufrufe, 10.955 Kandidaten und dieselben 64 belegten genutzten Aufgaben. Dieser Nenner entspricht nicht dem früheren 54,3-%-Vergleich.

| Suchliste | A | k | Genutzt / Recall | Behalten / Anteil |
|---|---:|---:|---|---|
| Work | 21 | 3 | 62/64; 96,88 % | 4401/10955; 40,17 % |
| Work | 21 | 5 | 63/64; 98,44 % | 4837/10955; 44,15 % |
| Work | 21 | 8 | 63/64; 98,44 % | 5430/10955; 49,57 % |
| Work | 30 | 5 | 64/64; 100,00 % | 5398/10955; 49,27 % |
| Beide | 21 | 3 | 62/64; 96,88 % | 4409/10955; 40,25 % |
| Beide | 21 | 5 | 63/64; 98,44 % | 4846/10955; 44,24 % |
| Beide | 21 | 8 | 63/64; 98,44 % | 5432/10955; 49,58 % |
| Beide | 30 | 5 | 64/64; 100,00 % | 5406/10955; 49,35 % |

## Zuordnungsnachweis je Aufruf

Snapshot-IDs sind als S-Aliase dargestellt. Ein Job kann mehrere Abgleich-Aufrufe haben; Aufrufindex und Zeitstempel unterscheiden sie. Die vollständige technische Rangzuordnung mit echten target_ids liegt ausschließlich im benannten Scratch-Verzeichnis.

| Job-Alias | Aufrufindex | Meetingdatum | Abgleich created_at (UTC) | Snapshot-Alias | Anfragen | Kandidaten | Genutzt |
|---|---:|---|---|---|---:|---:|---:|
| d825f68c | 33 | 2026-10-05 | 2026-10-07T00:17:53.130127+00:00 | S19 | 18 | 315 | 1 |
| b5e4fddb | 13 | 2026-10-06 | 2026-10-07T00:54:52.34974+00:00 | S23 | 6 | 161 | 2 |
| cfb69858 | 55 | 2026-10-09 | 2026-10-09T10:17:50.46155+00:00 | S27 | 30 | 460 | 4 |
| 238680c6 | 41 | 2026-10-05 | 2026-10-07T00:27:24.015038+00:00 | S11 | 23 | 319 | 0 |
| f91105a3 | 16 | 2026-10-05 | 2026-10-07T00:34:53.519405+00:00 | S22 | 7 | 219 | 2 |
| f91105a3 | 15 | 2026-10-05 | 2026-10-07T00:34:40.920938+00:00 | S22 | 7 | 219 | 0 |
| 09413c6e | 44 | 2026-10-05 | 2026-10-07T00:43:11.680889+00:00 | S28 | 25 | 412 | 1 |
| 476dd6dd | 55 | 2026-10-05 | 2026-10-07T00:08:53.94756+00:00 | S17 | 23 | 401 | 0 |
| 6856cff5 | 51 | 2026-10-06 | 2026-10-07T01:04:06.101805+00:00 | S8 | 32 | 403 | 6 |
| 423522f3 | 32 | 2026-10-12 | 2026-10-12T14:26:55.493654+00:00 | S24 | 17 | 344 | 4 |
| 6856cff5 | 50 | 2026-10-06 | 2026-10-07T01:03:45.055911+00:00 | S8 | 32 | 403 | 0 |
| 10f9fb46 | 16 | 2026-10-06 | 2026-10-07T01:24:06.443603+00:00 | S20 | 8 | 217 | 0 |
| b5d7671d | 36 | 2026-10-06 | 2026-10-07T01:32:06.924024+00:00 | S20 | 20 | 318 | 0 |
| 7b8798d7 | 38 | 2026-10-06 | 2026-10-07T01:40:57.023826+00:00 | S13 | 21 | 409 | 1 |
| b2c93c9d | 25 | 2026-10-12 | 2026-10-12T15:35:51.027077+00:00 | S2 | 15 | 279 | 0 |
| 5071d4e8 | 43 | 2026-10-06 | 2026-10-07T01:50:25.495686+00:00 | S21 | 26 | 412 | 0 |
| ce950c31 | 6 | 2026-10-07 | 2026-10-07T08:19:00.720007+00:00 | S3 | 2 | 91 | 0 |
| 2ee9f17f | 74 | 2026-10-07 | 2026-10-07T08:59:11.995726+00:00 | S3 | 46 | 489 | 9 |
| 2d34a51a | 18 | 2026-10-08 | 2026-10-08T08:15:18.956544+00:00 | S6 | 9 | 212 | 1 |
| c9251ed3 | 47 | 2026-10-08 | 2026-10-08T08:57:26.381707+00:00 | S7 | 30 | 443 | 3 |
| 587e3528 | 35 | 2026-10-08 | 2026-10-08T09:26:26.078732+00:00 | S18 | 20 | 364 | 2 |
| f5899fe0 | 29 | 2026-10-08 | 2026-10-08T10:05:45.122051+00:00 | S12 | 15 | 357 | 1 |
| 2f8ec945 | 61 | 2026-10-08 | 2026-10-08T12:28:03.716933+00:00 | S5 | 35 | 447 | 4 |
| 4e7b6e03 | 54 | 2026-10-09 | 2026-10-09T09:17:28.661405+00:00 | S4 | 29 | 520 | 4 |
| 990970ea | 37 | 2026-10-09 | 2026-10-09T10:46:48.336031+00:00 | S26 | 21 | 384 | 2 |
| a8c4b587 | 26 | 2026-10-12 | 2026-10-12T07:16:06.123693+00:00 | S1 | 12 | 323 | 1 |
| a8c4b587 | 24 | 2026-10-12 | 2026-10-12T07:15:32.146972+00:00 | S1 | 12 | 323 | 0 |
| a8c4b587 | 25 | 2026-10-12 | 2026-10-12T07:15:50.898176+00:00 | S1 | 12 | 323 | 0 |
| bb1cc002 | 8 | 2026-10-12 | 2026-10-12T07:23:18.104193+00:00 | S1 | 4 | 107 | 0 |
| 85f9e46f | 76 | 2026-10-12 | 2026-10-12T08:49:38.99831+00:00 | S1 | 40 | 501 | 4 |
| be0d246a | 47 | 2026-10-12 | 2026-10-12T09:03:40.591001+00:00 | S16 | 26 | 471 | 3 |
| f6827822 | 11 | 2026-10-12 | 2026-10-12T09:13:14.521801+00:00 | S10 | 5 | 203 | 0 |
| 2071f0f0 | 49 | 2026-10-12 | 2026-10-12T09:28:23.356604+00:00 | S9 | 27 | 453 | 2 |
| d51fd70f | 59 | 2026-10-12 | 2026-10-12T10:19:02.100354+00:00 | S15 | 31 | 475 | 1 |
| 8bdacbe2 | 24 | 2026-10-12 | 2026-10-12T12:55:38.123019+00:00 | S25 | 13 | 193 | 2 |
| 7d5f81a9 | 28 | 2026-10-12 | 2026-10-12T14:16:17.860226+00:00 | S14 | 17 | 253 | 4 |

## Mehrdeutigkeiten

Zwei Titel-/Claim-Paare sind global mehrdeutig; die folgende Liste zeigt sämtliche 23 Kandidatenvorkommen. Jede Zuordnung ist im Aufruf-Snapshot eindeutig; keiner dieser Kandidaten ist eine belegte genutzte Aufgabe.

| Job-Alias | Aufrufindex | Work-Alias | Global mögliche IDs | IDs im Snapshot |
|---|---:|---|---:|---:|
| cfb69858 | 55 | W47 | 5 | 1 |
| cfb69858 | 55 | W304 | 7 | 1 |
| f91105a3 | 16 | W152 | 7 | 1 |
| f91105a3 | 15 | W152 | 7 | 1 |
| 476dd6dd | 55 | W280 | 7 | 1 |
| 423522f3 | 32 | W34 | 5 | 1 |
| 423522f3 | 32 | W206 | 7 | 1 |
| 7b8798d7 | 38 | W280 | 7 | 1 |
| 2ee9f17f | 74 | W334 | 7 | 1 |
| c9251ed3 | 47 | W286 | 7 | 1 |
| 587e3528 | 35 | W242 | 7 | 1 |
| 2f8ec945 | 61 | W52 | 5 | 1 |
| 2f8ec945 | 61 | W290 | 7 | 1 |
| 4e7b6e03 | 54 | W55 | 5 | 1 |
| 4e7b6e03 | 54 | W339 | 7 | 1 |
| 990970ea | 37 | W238 | 7 | 1 |
| a8c4b587 | 26 | W191 | 7 | 1 |
| a8c4b587 | 24 | W191 | 7 | 1 |
| a8c4b587 | 25 | W191 | 7 | 1 |
| be0d246a | 47 | W302 | 7 | 1 |
| d51fd70f | 59 | W312 | 7 | 1 |
| 8bdacbe2 | 24 | W24 | 5 | 1 |
| 8bdacbe2 | 24 | W117 | 7 | 1 |

## Quellen und Wiederholbarkeit

- Replay: `/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl`.
- Archiv: `~/Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz`, Member `canonical/queue.jsonl`. Zweimal vollständig gestreamt; kein Archiv entpackt. Ein zusätzlicher Original-Prüflauf wurde nach einer Typ-Assertion abgebrochen und anschließend korrekt mit dem dict-Format der Originalzeilen wiederholt.
- Produktionscode: `working-memory/evaluation/sol-operational-release-20261006/backend/hybrid_index.py` (encode/digest, Dokumentaufbau, search, queries), `hybrid_pipeline.py` (Sucharten und Suchquota, Kandidatenauswahl) und `processor.py` (Originalzeilen).
- Hash-/Such-SQL: `backend/schema/20260920174816_working_memory_search_vector_index_scan.sql`, Zeile 14; dieselbe Hashidentität in den vorangehenden Work-/Lexikal-Fassungen.
- Frühere Messung: `selector/README.md`, Zeilen 22 und 45: gleiche 36 Aufrufe und 12.223 Kandidaten, 64 belegte genutzte, 6.632 behalten. Das historische Cosine/Lexikal-Maß wurde hier nicht erneut ausgeführt.
- Eigener Code, pseudonymisierte Zwischenergebnisse und technische Identitäten ausschließlich unter `/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/codex-rank`: `extract.py`, `hash_probe.py`, `analyze_probe.py`, `metrics.py`, `check_originals.py`, `report.py`, `verify.py`, `extracted.json`, `hash_links.json`, `probe_summary.json`, `metrics.json`, `literal-check.json`, `production-ranks.jsonl`, `verification.json` und `report-draft.md`.
- `production-ranks.jsonl`: je Aufruf/Beobachtung die originale Work-Reihenfolge 0–19 mit echten target_ids, Query-Hash, Snapshot-ID und created_at sowie die ursprünglichen gemischten Work-Positionen. Keine Meetinginhalte.
- Tatsächlich geprüft: 1.306 exakte Hashmatches; 716 eindeutige Zeit-/Job-/Snapshot-Zuordnungen für beide Listen; Snapshot-Mitgliedschaft sämtlicher Treffer; target_id-Gleichheit mit Work-Dokumenten; alle Kandidatenidentitäten; direkte wörtliche ID-Prüfung; Nenner 12.223 und Positivmenge 64; alle 35 Rasterzellen je Suchlisten-Interpretation. Zusätzlich unabhängige mengenbasierte Nachrechnung sämtlicher 70 Zellen, Monotonie und k=0-Gleichheit zum Altersfilter bestanden. Keine Provider-, Live-Produktions- oder Produktabnahme.
- Arbeitsmodus: Quellcode, Daten und Projektstatus bleiben unverändert. Kein Commit, Push oder Deployment. Die einzige neue Projektdatei ist dieser Bericht. Kein Graphify-Lauf: nicht für die eng begrenzte Hash-/Rangrekonstruktion erforderlich; Erstellung wäre außerhalb der erlaubten Schreiborte und der Stdlib-Vorgabe.

### Dateibindung

| Datei-Kategorie | SHA-256 |
|---|---|
| Replay | 3de893f45ef4c55ff569a0df6385abd6781170460ed6ca0dd82a239b566f9211 |
| Index | 5c4c18b8f436c6a9e88198e214a3a05270bcf3c2ff6c413d2487161bf5baa72d |
| Pipeline | 5a7562fb72bc72e6ee3632c21c596f1a6f85a4792a1488c5123e26007a8b5a68 |
| SQL | 339c8ffbdcd033435a2ae53e9999febfd19d09fe5c7188b6b3d116c52d0bfec1 |
