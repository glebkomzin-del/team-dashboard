# Offline-Kandidaten-Selektor

Deterministischer, isolierter Prototyp; Python-Stdlib, keine Netzwerk-/Modellaufrufe.
Aufgaben bleiben, wenn `age_days <= A` oder ein Embedding-/Lexikalrang bei
irgendeiner Beobachtung `< k` ist. `done` bleibt zulässig. Reihenfolge und
Tie-Break folgen dem Kandidatenindex. Gründe: `age`, `emb`, `lex`.

```sh
cd /Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard\ Job/meeting-os/working-memory/evaluation/poc-tiered-reconcile-20261012/selector
python3 -I -m unittest -v
python3 -I replay.py --calls /private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl --vectors /private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/vectors.pkl --A 21 --k 5
```

„Genutzt“ bedeutet je Aufruf/Kandidatenposition:
`work_results[str(work_index)] != 'unchanged'` **oder** der Alias ist
`update_target` einer `obs_out`-Beobachtung. Beide Wege zusammen zählen einmal.
Fehlende Ergebnisse sind unbekannt, außer ein Update-Target beweist Nutzung;
sie zählen separat als `unknown_usage`, niemals als `unchanged`. Recall = behaltene
belegte genutzte / alle belegten genutzten; ohne genutzte Kandidaten `null`. Behaltener Anteil =
alle behaltenen / alle Kandidaten. Fehlerzeilen ohne `work` zählen separat.
Die Hauptzahlen und das Raster verwenden wie das vorhandene Messskript
`scratchpad/recall2.py` nur Aufrufe mit nichtleerem `work` und `obs_in`.
`all_complete_metrics` zeigt zusätzlich alle vollständigen Aufrufe, inklusive
leerer Beobachtungen; ausgeschlossene Aufrufe und Kandidaten werden gezählt.

`select` erhält optional reine Callbacks `embed_candidate(candidate)` und
`embed_query(observation)`; fehlende Vektoren liefern `None`. `stats` enthält
Alter und minimale Ränge je Kandidatenindex. Das Raster nutzt diese gleichen
Ränge ohne erneute Ähnlichkeitsberechnung. Lexikaltext der Aufgabe:
`title claim matter`; Lexikalsuchtext: `title subject search_keywords claim`.
Embedding-Suchtext: `title subject search_keywords`.
Diese Feldwahl entspricht der historischen Messung in `recall2.py`.
Tokenisierung: Unicode-`\w`, Kleinschreibung mit `casefold`, mindestens vier Zeichen, erste
sechs Zeichen, eindeutige Menge. Auch Nullscores erhalten einen Rang.

Vektoren werden ausschließlich aus dem primitiven Pickle geladen. Titel werden
als vollständige, getrimmte Zeile in den ersten drei Body-Zeilen gesucht;
mehrere Treffer werden über `claim[:60]`
aufgelöst. Ohne eindeutigen Claim-Treffer gilt das Embedding als fehlend und wird
gezählt. Query-Schlüssel verwenden JSON-Listen mit Unicode, danach ASCII-Fallback.
Datumsdifferenzen sind Kalendertage; fehlende/ungültige Daten ergeben 9999,
zukünftige Daten negative Werte. `A` und `k` sind nichtnegative Ganzzahlen.

Geprüft am 2026-10-12: **29/29 Tests**, 36 Replay-Aufrufe, 12.223 Kandidaten,
64 belegte genutzte, **100 % Recall**, 6.632 behalten (**54,258365 %**).
Vollständige Testausgabe und 30 Rasterzellen: [validation.txt](validation.txt).
Der Rohbestand umfasst 40 vollständige Aufrufe mit 12.290 Kandidaten; vier
Aufrufe ohne Beobachtungen enthalten 67 Kandidaten. Zusätzlich eine Fehlerzeile.
Alle benötigten Vektoren sind zugeordnet. 1.268 Kandidaten haben kein
`work_results`-Label; tatsächlicher Recall über diese Fälle bleibt unbekannt.

Grenzen: historische Labels sind keine unabhängige Wahrheitsreferenz;
keine Produktionsintegration. Ausgaben enthalten nur Zahlen sowie bei verpassten
genutzten Kandidaten Alias, Alter, Status und Ränge. Keine Meeting-Texte.
Keine Git-Versionierung gemäß Auftrag. Rückweg: dieses neue Verzeichnis entfernen.
