---
id: "D-20261029-003947-10c1-minimaler-speicher-und-diagnosefix"
typ: "entscheidung"
status: "aktiv"
thema: "verarbeitung"
tags: []
geltung: "lokal"
ersetzt_durch: "-"
change: "processing-repair-20261028"
datum: "2026-10-29T00:39:47"
quelle: "codex:01a18271-5360-7231-a80f-6b730726589a"
---
Der produktive Reparaturumfang blieb auf memory.py, openai_provider.py und die daraus abgeleitete Pipelinekennung begrenzt. Bereits vom Gate gesperrte Aufgabenänderungen werden als Wissen des ursprünglichen bekannten Bereichs erhalten und erzeugen kein Arbeitsereignis; wirksame bereichsfremde Änderungen bleiben abgewiesen. Der Provideradapter erhält ausschließlich begrenzte technische Streamdiagnosen, keine freien Fehlertexte oder Geheimnisse; automatische Wiederholungen und Modelle wurden nicht global erweitert. Grund: die doppelte Wirksamkeitsprüfung hatte zwei gesamte Quellen trotz bereits gesperrter Aufgabenwirkung abgewiesen, während sichere Diagnosen für die späteren Altfehler fehlten. Echte Vorher-Nachher-Wiederholungen und29 Tests bestätigten diese eng begrenzte Reparatur. Belege: Reparaturkapsel replay/README.md, replay/overlay/memory.py und provider/openai_provider.py.