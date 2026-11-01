# Delta-Auswertung 2 · 2026-10-13
Lokaler Referenzvergleich; n/b = nicht bestimmbar. Keine fachliche Wahrheitsprüfung der Referenz.
Quellen: selected_requests.jsonl; server-results/{replay_ledger.jsonl,raw-attempt-001..006.sse,compare_delta.py,delta_codec.py,delta_schema.py}; ../../filtered-replay/{RESULT.md,comparison_requests-run2.jsonl,results-filtered-run*.jsonl}; ../../model-replay/{requests.jsonl,RESULT-DETAIL.md}.
Prüfung: `python3 -I -B compare_delta.py --requests ../selected_requests.jsonl --results replay_ledger.jsonl` im server-results-Verzeichnis; Exit 1 = Qualitätskriterien nicht vollständig erfüllt.
Schema 6/6; Endform 5/6; Abdeckung 5/6; Entscheidungen 4/6; Lebenszyklus 4/6; akzeptiert 4/6. SSE-Text und Usage stimmen jeweils 6/6 typstreng mit dem Ledger überein; Streamfehler 0.
Entscheidungen im Comparator = update_target + update + matter_id, NICHT allein update_target.

| Aufruf-ID[:8] / call_index | Alias | Quellen geliefert/Soll | Endform | akzeptiert | Kategorie |
| --- | --- | ---: | ---: | ---: | --- |
| 740b1eb7 / 1 | ∅ | 0/0 | 1 | 1 | keine Abweichung im Gate |
| acc34319 / 2 | ∅ | 0/0 | 1 | 1 | keine Abweichung im Gate |
| ce950c31 / 6 | ∅ | 2/2 | 1 | 1 | keine Abweichung im Gate |
| bb1cc002 / 8 | ∅ | 4/4 | 1 | 1 | keine Abweichung im Gate |
| 8bdacbe2 / 24 | M116, W130; W152 erhalten | 13/13 | 1 | 0 | matter_id fehlt 2×; Lebenszyklus verpasst 1× |
| a8c4b587 / 26 | H439, W73 | 0/12 | 0 | 0 | open_ids-Nachforderung; Beobachtungen fehlen 12×; Lebenszyklus n/b |

8bdacbe2: source_index 9 und 12: Referenz matter_id=M116; Extraktion matter_id=null; Delta changes=[]; Decoder übernimmt null korrekt. Dies ist keine update_target-Abweichung.
W130: Referenz work_results[130].action=progress; Delta work_results=[]; Decoder rekonstruiert unchanged. W152 bleibt bei source_index 1 progress und bei 11 none; W130 wird nicht durch diese Beobachtungen ersetzt.
a8c4b587: Delta open_ids=[H439], observations=[], work_results=null; Referenz open_ids=[], 12 Beobachtungen, W73=ambiguous. H439 ist schema-zulässig und gehört nicht zu den 4 bereits geöffneten IDs; fachliche Notwendigkeit n/b.
W73 ist ohne Endform nicht als falsches unchanged bestimmbar; die 12 fehlenden Beobachtungen sind Bestandteil des Nachforderungszweigs, keine 12 unabhängig belegten Auslassungsfehler.
Final gelieferte Beobachtungen: update_target 19/19, update 19/19, matter_id 17/19; positive update_target 2/2. Weitere 12 Entscheidungen n/b. Zusätzliche Lifecycle-Flags in Endformen 0; Decoderfehler 0/6.

| Abweichung | Delta-Mechanismus / Kontrollbeleg | Klassifikation |
| --- | --- | --- |
| M116 → null, Quellen 9/12 | Nicht ausgegebene Korrektur wird vererbt. Ungefilterte Sol-Kontrollen: 3 matter_id-Abweichungen/22 Quellen, darunter null→M183 und M60→M151. | Auslassung belegt; Zuordnungsrauschen gleicher Kategorie belegt; Formatkausalität n/b. |
| W130 progress→unchanged | Fehlender Slot wird unchanged. Identischer Fall im Filterlauf; ungefilterte Kontrollen verpassen W5 und W8/progress, progress-Recall 0/2. | Rauschkompatibel; gleiche Kategorie ohne Delta belegt, kein ungefilterter Kontrolllauf für W130. |
| H439-Nachforderung / fehlende Endform | Identischer Aufruf im Filterlauf fordert H470/H454 statt Endform. Ungefilterte Kontrollen liefern 3/3 Endformen; kein gepaarter Kontrolllauf für a8c4b587. | Bekanntes Nachforderungsmuster außerhalb Delta; nicht als ungefiltertes Sol-Rauschen oder Formatfehler bewiesen. |
| Weitere Feldabweichungen | 19 gelieferte Quellen: confidence_reason 19, claim 15, uncertainty 13, title 9, subject 5, matter 2, search_keywords 1, state_evidence_ids 1. Alle Kategorien auch in ungefilterten Kontrollen abweichend. | Rauschkompatible Kategorien; fachliche Wirkung und Formatkausalität n/b. |
| Scores | bb1cc002: change_score 2→1 bei Quellen 1/3; 8bdacbe2: assignment_score 1→2 bei Quelle 8. Jeweils Extraktionswert übernommen; beide Score-Kategorien variieren auch ungefiltert. | Auslassung belegt; Rauschkompatibilität, keine eindeutige Formatursache. |
coverage_notes variieren zusätzlich in Anzahl/Text; der Comparator prüft ihre Inhaltsgleichheit nicht. Auch 4/6 akzeptiert bedeutet keine vollständige Feldgleichheit.
Die 6 Referenzantworten und Usage stimmen typstreng mit den gespeicherten model-replay/Sol-Referenzen überein. Sol/Luna-Zahlen in RESULT-DETAIL sind kein Sol-gegen-sich-selbst-Kausalnachweis.
Bestätigte formatverursachte Fehler: 0; bestätigte Decoderfehler: 0. Default-Vererbung ist belegt, ihre Verursachung durch das Format gegenüber normalem Modellrauschen bleibt offen.

Anpassungsvorschläge gegen stille Auslassungen; NICHT umgesetzt oder als Fehlerbehebung validiert:
Prompt Quellen: „Im Endformzweig gib jeden source_index genau einmal aus, auch bei changes=[]. Eine fehlende Quelle darf niemals als unverändert ergänzt werden.“
Prompt Entscheidungen: „Gib für jede Beobachtung decision mit update_target, update und matter_id ausdrücklich aus, auch bei null. Entscheide diese drei Felder neu anhand der Kandidaten; fehlend bedeutet hier niemals unverändert. Nur übrige Felder stehen in changes.“
Schema: Quellpatch required=[source_index,decision,changes]; decision required=[update_target,update,matter_id], mit bisherigen Typen/Enums und additionalProperties=false; Entscheidungsfelder aus changes entfernen.
Decoder: decision vollständig verlangen und übernehmen; doppelte/fehlende Quellen und doppelte Feldentscheidungen verwerfen; keine automatische M116-Zuordnung ohne fachlichen Beleg. Ein ausdrücklich falsches null bleibt möglich.
Prompt Lebenszyklus: „Prüfe jeden work_index. Liste jede Änderung in work_results und jeden ausdrücklich unveränderten Slot in unchanged_work_indices. Ungeprüft bedeutet nicht unchanged. Erhalte die bestehende Regel gegen Doppeländerungen.“
Schema/Decoder: unchanged_work_indices als Pflichtliste; disjunkte Vereinigung mit work_results.work_index muss im Endformzweig exakt alle Slots ergeben. Erst danach unchanged ergänzen; fehlend/unklar ist unvollständig. Eine falsche ausdrückliche unchanged-Entscheidung bleibt möglich.
Prompt Nachforderung: „Neue H-IDs nur bei einem konkret benannten notwendigen historischen Bezug. Nachforderung bleibt observations=[], work_results=null; sie ist keine finale Abnahme. Wiederhole keine bereits geöffneten IDs.“
Decoder/Schema: Nachforderungs- und Endformzweig getrennt prüfen; neue zulässige H-IDs weiter erlauben. Keine künstliche Endform erzwingen und keine automatisch bezahlte Wiederholung. Quellenpflicht gilt nur im Endformzweig.
Tokenwirkung: Für die 5 vorhandenen Endformen (19 Quellen, 412 Slots) kostet decision netto +1.019 JSON-Zeichen, unchanged_work_indices +2.256, zusammen +3.275.
Heuristik ceil(Zeichen/3,6): ungefähr +284 / +627 / +910 sichtbare Tokens, zusammen etwa +0,0091 USD bei 10 USD/Mio. Outputtokens. Kein Tokenizer-/Reasoning-Nachweis; keine Kostenprognose für die fehlende Endform oder nötige zusätzliche Sachkorrekturen.

Empfehlung: derzeit NICHT für Produktion freigeben. Die beiden positiven Referenz-Lifecycle-Fälle sind nicht reproduziert bzw. ohne Endform; die 4 akzeptierten Fälle enthalten keine positiven Referenz-Lifecycle-Änderungen.
Auflagen für erneute Freigabebewertung: Endform nach legitimer Nachforderung nachweisen; W130/progress und W73/ambiguous sowie M116-Zuordnungen prüfen; unveränderte fachliche Validatoren beibehalten; Positivfälle und gleiche ungefilterte Kontrollfälle vergleichen. Pflichtfelder allein beweisen keine fachliche Korrektheit.
Kosten dieser 6 gespeicherten Abgleich-Aufrufe: 0,779416→0,486232 USD; Differenz 0,293184 USD; gemessen −37,62 %. Output inklusive Reasoning: 19.922→3.304 Tokens, −83,42 %.
Davon Outputkostenersparnis 0,166180 USD; übrige Input-/Preiskomponente einschließlich Rundung 0,127004 USD. Referenz: 232.081 Inputtokens, davon 232.063 Cache-Write; Delta: 226.596 Inputtokens, Cache-Write/Cache-Read jeweils 0. Daher keine reine Formatersparnis.
Nur 4 akzeptierte Aufrufe: 0,231838→0,156498 USD, −32,50 %; andere Größen-/Positivfallauswahl, keine Produktionsschätzung.
Rechnerische Erwartung unter gleicher Qualität, gleichem Kostenmix und 74 % Abgleichanteil: 37,62 % Abgleichersparnis × 0,74 = 27,84 % Meeting-Gesamtersparnis (≈37,6 % / 27,8 %).
Qualitätsgleiche Produktionsersparnis einschließlich weiterer Nachforderungsrunden, Prompt-/Schemaänderungen und Reasoning: n/b. Die 37,62 % enthalten 2 nicht akzeptierte Aufrufe; keine garantierte Meeting-Kostenquote.
