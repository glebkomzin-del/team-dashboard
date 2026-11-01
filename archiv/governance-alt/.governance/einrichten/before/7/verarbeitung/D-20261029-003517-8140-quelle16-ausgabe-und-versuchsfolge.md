---
id: "D-20261029-003517-8140-quelle16-ausgabe-und-versuchsfolge"
typ: "entscheidung"
status: "aktiv"
thema: "verarbeitung"
tags: ["praezisierung"]
geltung: "lokal"
ersetzt_durch: "-"
change: "processing-repair-20261028"
datum: "2026-10-29T00:35:17"
quelle: "codex:01a18271-5360-7231-a80f-6b730726589a"
---
Quelle16 erhielt nach dem bekannten 24000-Token-Abschluss einen geprüften Vollversuch: Befehl e9a2a394-dab8-5585-b7ee-7570223ac4b8, Startplatz2. Ausschließlich die durch den ursprünglichen Requesthash gebundene Extraktionsanfrage durfte48000 Ausgabetokens verwenden; Prompt, Schema, Modell, Tarif und Inhaltsprüfungen blieben unverändert. Die spätere präzise Kontextprüfung setzte genau diesen Befehl fort und erzeugte keinen weiteren Vollversuch. Grund: der gespeicherte Abschluss benannte max_output_tokens und war bereits korrekt mit149115Mikro-USD verbucht; eine globale Limiterhöhung war unnötig. Präzisierung des älteren Eintrags zur Abgrenzung von neuem Vollversuch und späterer Fortsetzung. Beleg: Reparaturkapsel reprocess/README.md und audit/reprocess22-final.json.