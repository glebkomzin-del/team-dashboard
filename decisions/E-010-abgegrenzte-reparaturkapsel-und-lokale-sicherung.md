# E-010 Abgegrenzte Reparaturkapsel und lokale Sicherung
2026-10-29T00:31:34: Reparatur und Betriebswerkzeuge wurden in einer abgegrenzten Kapsel gehalten; fremde Hauptstandsdateien wurden nicht überschrieben und kein Push ausgeführt. Grund: zu Beginn war der Hauptstand bereits parallel verändert beziehungsweise teilweise unversioniert. Lokale Commits und vollständiges Rücklesen sichern die geprüfte Kapsel;979 fremde Indexdatensätze einschließlich6 vorgemerkter Änderungen blieben unverändert. Belege: Reparaturkapsel README.md und audit/private/local-save.json. Historischer Einzelauftrag; keine neue oder allgemeine Freigabe.

Bezug: V

## Grund
zu Beginn war der Hauptstand bereits parallel verändert beziehungsweise teilweise unversioniert.

## Verworfene Wege
keine ausdrücklich genannt

## Ersetzt durch
Ersetzungen verwaltet `gov replace` im gemeinsamen Register. `gov show` zeigt die neuere Kennung; diese Datei bleibt unverändert.

Quelle: wissen/verarbeitung/D-20261029-003134-b55b-abgegrenzte-kapsel-und-lokale-sicherung.md:13
