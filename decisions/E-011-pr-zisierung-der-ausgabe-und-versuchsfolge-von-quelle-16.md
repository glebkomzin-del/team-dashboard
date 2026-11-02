# E-011 Präzisierung der Ausgabe- und Versuchsfolge von Quelle 16
2026-10-29T00:35:17: Quelle16 erhielt nach dem bekannten 24000-Token-Abschluss einen geprüften Vollversuch: Befehl e9a2a394-dab8-5585-b7ee-7570223ac4b8, Startplatz2. Ausschließlich die durch den ursprünglichen Requesthash gebundene Extraktionsanfrage durfte48000 Ausgabetokens verwenden; Prompt, Schema, Modell, Tarif und Inhaltsprüfungen blieben unverändert. Die spätere präzise Kontextprüfung setzte genau diesen Befehl fort und erzeugte keinen weiteren Vollversuch. Grund: der gespeicherte Abschluss benannte max_output_tokens und war bereits korrekt mit149115Mikro-USD verbucht; eine globale Limiterhöhung war unnötig. Präzisierung des älteren Eintrags zur Abgrenzung von neuem Vollversuch und späterer Fortsetzung. Beleg: Reparaturkapsel reprocess/README.md und audit/reprocess22-final.json. Historischer Einzelauftrag; keine neue oder allgemeine Freigabe.

Bezug: V

## Grund
der gespeicherte Abschluss benannte max_output_tokens und war bereits korrekt mit149115Mikro-USD verbucht; eine globale Limiterhöhung war unnötig.

## Verworfene Wege
keine ausdrücklich genannt

## Ersetzt durch
Ersetzungen verwaltet `gov replace` im gemeinsamen Register. `gov show` zeigt die neuere Kennung; diese Datei bleibt unverändert.

Quelle: wissen/verarbeitung/D-20261029-003517-8140-quelle16-ausgabe-und-versuchsfolge.md:13
