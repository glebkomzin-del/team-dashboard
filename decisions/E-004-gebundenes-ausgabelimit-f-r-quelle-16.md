# E-004 Gebundenes Ausgabelimit für Quelle 16
2026-10-29T00:31:33: Nur die exakt per ursprünglichem Requesthash gebundene Extraktionsanfrage von Quelle16 durfte im geprüften zusätzlichen Versuch 48000 statt 24000 Ausgabetokens verwenden. Prompt, Schema, Modell, Tarif und Inhaltsprüfungen blieben unverändert; Budgetreservierung verwendete das höhere tatsächliche Limit. Grund: der bekannte vollständige Anbieterabschluss benannte max_output_tokens und war bereits korrekt mit 149115 Mikro-USD verbucht. Keine globale Erhöhung der Limits. Beleg: Reparaturkapsel reprocess/README.md. Historischer Eintrag mit dokumentierter Ablösung.

Bezug: V

## Grund
der bekannte vollständige Anbieterabschluss benannte max_output_tokens und war bereits korrekt mit 149115 Mikro-USD verbucht.

## Verworfene Wege
keine ausdrücklich genannt

## Ersetzt durch
Ersetzungen verwaltet `gov replace` im gemeinsamen Register. `gov show` zeigt die neuere Kennung; diese Datei bleibt unverändert.

Quelle: wissen/verarbeitung/D-20261029-003133-6694-quelle16-gebundenes-ausgabelimit.md:13
