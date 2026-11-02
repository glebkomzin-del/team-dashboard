# E-016 Keine automatische Rückkehr zur Source nach Writer-Wechsel
2026-10-04: Nach der Writer-Öffnung darf das frühere Source-Supabase nicht als aktueller Datenstand verbunden oder durch den historischen Rückweg reaktiviert werden; der dokumentierte Rückweg verwendet einen Target-Backup. Historischer Auftrag; aktuelle externe Umsetzung ist damit nicht erneut geprüft.

Bezug: V

## Grund
Der tatsächliche Zielstand und inzwischen entstandene Daten müssen erhalten bleiben.

## Verworfene Wege
Keine ausdrücklich festgehalten.

## Ersetzt durch
Ersetzungen verwaltet `gov replace` im gemeinsamen Register. `gov show` zeigt die neuere Kennung; diese Datei bleibt unverändert.

Quelle: working-memory/docs/RESTORE-RUNBOOK.md:201
