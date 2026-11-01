---
id: "D-20261029-003134-b55b-abgegrenzte-kapsel-und-lokale-sicherung"
typ: "entscheidung"
status: "aktiv"
thema: "verarbeitung"
tags: []
geltung: "lokal"
ersetzt_durch: "-"
change: "processing-repair-20261028"
datum: "2026-10-29T00:31:34"
quelle: "codex:01a18271-5360-7231-a80f-6b730726589a"
---
Reparatur und Betriebswerkzeuge wurden in einer abgegrenzten Kapsel gehalten; fremde Hauptstandsdateien wurden nicht überschrieben und kein Push ausgeführt. Grund: zu Beginn war der Hauptstand bereits parallel verändert beziehungsweise teilweise unversioniert. Lokale Commits und vollständiges Rücklesen sichern die geprüfte Kapsel;979 fremde Indexdatensätze einschließlich6 vorgemerkter Änderungen blieben unverändert. Belege: Reparaturkapsel README.md und audit/private/local-save.json.