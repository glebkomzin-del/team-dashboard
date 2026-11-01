# (1) Aufrufe und Abweichungskategorien
Belegstatus: lokale Aggregate; Einzelantworten nicht lokal vorhanden; n/b = nicht bestimmbar.
Quellen: server-results/run.out, server-results/compare_delta.py, selected_requests.jsonl.
6 Aufrufe; 6 Versuche; 0 fehlgeschlagen; Schema 6/6; akzeptiert 4/6; abgelehnt 2/6.
Endform 5/6; Beobachtungsabdeckung 5/6; Entscheidungsübereinstimmung 4/6; Lebenszyklusübereinstimmung 4/6.
Entscheidungen = update_target + update + matter_id; Lebenszyklus = vollständige Änderungsobjekte, keine reine Aktionszählung.
Ablehnung: beide Aufrufe mit Entscheidungs- UND Lebenszyklusabweichung (Ableitungsbasis: jeweils 2 Fehler, insgesamt 2 Ablehnungen).
Fehlende Endform/Nachforderung: 1; fehlende Quellenabdeckung: 1; gleiche Aufruf-ID dafür n/b; Legitimität der Nachforderung n/b.
Anderes Ziel / verpasste Lebenszyklusänderung / zusätzliche Flags: jeweils n/b; konkrete IDs und Aliase der 2 Ablehnungen n/b.
Kandidaten aus selected_requests.jsonl; Aliase ausschließlich Referenz, keine behaupteten Delta-Abweichungen:
| Aufruf-ID[:8] | Referenzalias | Kategorie |
| --- | --- | --- |
| 740b1eb7 | ∅ | akzeptiert, abgeleitet: 0 Quellen, maxItems=0, Entscheidungsprüfung zwingend erfüllt |
| acc34319 | ∅ | akzeptiert, abgeleitet: 0 Quellen, maxItems=0, Entscheidungsprüfung zwingend erfüllt |
| ce950c31 | ∅ | Ablehnung n/b |
| bb1cc002 | ∅ | Ablehnung n/b |
| 8bdacbe2 | W130 / W152 / M116 | Ablehnung n/b; Referenz progress / Ziel / matter_id |
| a8c4b587 | W73 | Ablehnung n/b; Referenz ambiguous |
Benötigte Serverdateien, ausschließlich Pfadangaben; nicht abgerufen, Existenz nicht geprüft:
`/root/v13-delta-20261013/replay_ledger.jsonl`
`/root/v13-delta-20261013/raw-attempt-001.sse`, `/root/v13-delta-20261013/raw-attempt-002.sse`
`/root/v13-delta-20261013/raw-attempt-003.sse`, `/root/v13-delta-20261013/raw-attempt-004.sse`
`/root/v13-delta-20261013/raw-attempt-005.sse`, `/root/v13-delta-20261013/raw-attempt-006.sse`
`/root/v13-delta-20261013/results` (Auftragsbezeichnung; Typ/Einzeldateinamen n/b).
Ledger genügt für ID-/Alias-/Kategoriezuordnung; SSE für Rohantwortprüfung (replay_delta.py: attempt.text, usage, Nummerierung).

# (2) Delta-Format oder Modellrauschen
Quellen: delta_codec.py, delta_schema.py, measurements.json; ../../filtered-replay/RESULT.md; ../../model-replay/RESULT-DETAIL.md.
Codec-Rundreise 40/40; Nachweis gespeicherter Rekonstruktionen, kein Nachweis korrekter Modellausgabe.
Delta-Regel: fehlendes Beobachtungsfeld → Extraktionswert; fehlender Arbeitsslot → unchanged; fehlende Quelle wird nicht ergänzt.
Hypothese Format-Auslassung: eine unterlassene Korrektur kann syntaktisch gültig bleiben; fehlende Endform ist als Nachforderungszweig ausdrücklich zulässig.
Bekanntes Kontrollrauschen: update_target 20/22 = 90,91 %; Lebenszyklus 2/4 reproduziert; progress 0/2; zusätzliche Flags 1.
Historischer Fall 8bdacbe2 / W130: progress → unchanged; a8c4b587 / W73: Nachforderung, Endform fehlt, Lebenszyklus n/b (Filterlauf, keine Kontrolle).
Zusätzlicher historischer Vergleich: 15 gepaarte Sol/Luna-Endformen; Zielübereinstimmung 128/140; Lebenszyklus-Recall 1/4 (anderer Modellvergleich).
Kategorienüberschneidung belegt; Fallgleichheit im Delta-Lauf n/b; Kausalität Delta/Rauschen n/b; 4/6 Aufrufe nicht mit 20/22 Beobachtungen vergleichbar.

# (3) Prompt-/Schema-Vorschläge; Hypothesen, nicht umgesetzt oder validiert
Ableitungsbasis: Delta-Vererbungsregeln, zulässiger Nachforderungszweig, fehlende Vollständigkeitsbedingungen in delta_schema.py.
Prompt Endform: „Im Endformzweig: open_ids=[], work_results als Liste, jede source_index genau einmal. Eine notwendige neue H-ID bedeutet Nachforderung, keine Endform; der Abgleich bleibt bis zur Endform offen.“
Schema Endform: open_ids.maxItems=0; work_results nur array, kein null; observations.minItems=maxItems=N; Decoder prüft exakt die N source_index.
Grenze: Endformschema nur bei belegter Endformphase; zulässige neue Nachforderungen erhalten, keine erzwungenen Sachentscheidungen.
Prompt Entscheidungen: „Gib je Quelle update_target, update und matter_id ausdrücklich an, auch null. Änderungen sämtlicher übrigen Felder gegenüber der Extraktion vollständig in changes ausgeben; Auslassen bedeutet Übernahme.“
Schema Entscheidungen: je Quellpatch Pflichtobjekt decision mit update_target/update/matter_id als required; Decoder übernimmt diese Werte; übrige Felder bleiben Delta.
Prompt Lebenszyklus: „Bestätige jeden work_index ausdrücklich als Änderung oder unchanged gemäß bestehender Doppeländerungsregel. Ungeprüft bedeutet nicht unchanged; fehlende Bestätigung ist unvollständig.“
Schema Lebenszyklus: zusätzlich unchanged_work_indices; disjunkte Vereinigung mit work_results.work_index muss exakt alle Slots ergeben; fehlende Slots als Fehler, keine stille Ergänzung.
Grenze: Vollständigkeitsprüfungen verhindern strukturelle Auslassungen; falsche unchanged-/Zielurteile bleiben möglich; neue Tokenkosten n/b.

# (4) Empfehlung und Kosten
Empfehlung: derzeit NICHT für Produktion freigeben; 2/6 Ablehnungen, 1/6 ohne Endform, 1/6 ohne vollständige Abdeckung; Ursachen n/b.
Auflagen für erneute Bewertung: Einzelzuordnung aus vorhandenen Rohdaten; Endform-/Abdeckungsprüfung; Prüfung der Auslassungshypothese; kein neuer Replay beauftragt.
Quellen Kosten: selected_requests.jsonl.reference_usage, replay_common.py.RATES/usage_micro_usd, server-results/run.out.
Reale Ausgabetokens inklusive Reasoning: 19.922 → 3.304; Reduktion (1−3.304/19.922)×100 = 83,42 % ≈ 83 %.
Referenzkosten: Σ ceil[2×(I−C−W)+0,10×C+2,50×W+10×O] Mikro-USD = 0,779416 USD; I=232.081, C=0, W=232.063, O=19.922.
Gesamtersparnis dieser 6 Abgleich-Aufrufe: (1−0,486232/0,779416)×100 = 37,62 %; Differenz 0,293184 USD.
Outputkomponente: (19.922−3.304)×10/1.000.000 = 0,166180 USD; übrige Input-/Preiskomponente inklusive Rundung 0,127004 USD, Aufteilung n/b ohne Ledger.
Grenze: Kosten enthalten 2 nicht akzeptierte Aufrufe; Ersparnis bei gleichwertigen Endformen n/b; keine reine Formatwirkung oder Produktionsquote belegt.
Stichprobengrenze: 6 budgetselektierte Fälle; obere Größenbereiche nicht vollständig abgedeckt (README.md, measurements.json).
