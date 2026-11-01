---
worum: "Fehlerhafte zweite Ebenen im ER-Mapping korrigieren; als Ursache wurden Nullwerte an eigentlich leeren zweiten Ebenen erkannt." # [belegt B1,B4]
naechster: "Gleb nimmt die direkte Anpassung der betroffenen zweiten Ebenen im Dienst vor." # [belegt B4]
fertig_wenn: "Die betroffenen zweiten Ebenen sind nach der Anpassung im Dienst tatsächlich leer und weisen dort keine fehlerhaften Nullwerte mehr auf." # [Annahme: Das prüfbare Kriterium wird aus dem Korrekturauftrag und der benannten Ursache a…; B1,B4]
art: "power-bi-modell" # [Annahme: Die Korrektur des ER-Mappings im Kontext „Power BI Ergebnisrechnung: Modell und …; B1,B28]
bearbeitungsweg: "selbst" # [Annahme: Da Gleb als Verantwortlicher genannt ist und die direkte Anpassung übernimmt, wi…; B2,B4]
relevanz: "wichtig" # Eingabemetadatum
---

Entwurf zur Abnahme. Formale Belegprüfung ersetzt keine fachliche Prüfung.

## Auftrag
Aufgabe: Fehlerhafte zweite Ebenen im ER-Mapping korrigieren; als Ursache wurden Nullwerte an eigentlich leeren zweiten Ebenen erkannt. [belegt B1,B4]
Nächster Schritt: Gleb nimmt die direkte Anpassung der betroffenen zweiten Ebenen im Dienst vor. [belegt B4]
Fertig wenn: Die betroffenen zweiten Ebenen sind nach der Anpassung im Dienst tatsächlich leer und weisen dort keine fehlerhaften Nullwerte mehr auf. [Annahme: Das prüfbare Kriterium wird aus dem Korrekturauftrag und der benannten Ursache a…; B1,B4]
Art: power-bi-modell [Annahme: Die Korrektur des ER-Mappings im Kontext „Power BI Ergebnisrechnung: Modell und …; B1,B28]
Bearbeitungsweg: selbst [Annahme: Da Gleb als Verantwortlicher genannt ist und die direkte Anpassung übernimmt, wi…; B2,B4]

## Scope
Drin: direkte Korrektur der fehlerhaften zweiten Ebenen im ER-Mapping durch Gleb im Dienst. Draußen: Anpassung der Reihenfolge der Darstellungszeilen; diese übernimmt Mathias. [belegt B1,B4]

## Kontext
Die Aufgabe gehört zur Power-BI-Ergebnisrechnung mit dem Thema Modell und Performance; eine bereits abgeschlossene Korrektur ist nicht belegt. [belegt B28,B4]

## Vorarbeiten/Vorgespräche
In der „Meeting Transcription“ vom 01.06.2026 wurden die Nullwerte als Ursache sowie die Aufteilung zwischen Glebs direkter Anpassung und Mathias’ Arbeit an der Zeilenreihenfolge festgehalten. [belegt B3,B4]

## Wiederverwendung
Power-BI-Marketingbericht [belegt B16]

## Offene Fragen
Wie sollen die eigentlich leeren zweiten Ebenen im Dienst konkret abgebildet werden? [Annahme: Die erkannte Ursache begründet die Klärung der Sollabbildung, ohne dass der Bele…; B4]
An welchen betroffenen Mapping-Einträgen soll die Korrektur geprüft werden? [Annahme: Für die Prüfung des benannten Fehlers werden konkrete betroffene Einträge benöti…; B1,B4]

## Abnahme
Der Nutzer prüft nach der Anpassung, ob die betroffenen zweiten Ebenen wie vorgesehen leer sind und die fehlerhaften Nullwerte beseitigt wurden. [Annahme: Die vorgeschlagene Nutzerprüfung folgt aus dem beschriebenen Fehlerbild, während…; B1,B4]

## Belege
B1 | dashboard-20261012T155114Z.tar.gz/canonical/journal.jsonl:L289; feld=worum | unbekannt | Fehlerhafte zweite Ebenen im ER-Mapping korrigieren [belegt B1] ; B2 | dashboard-20261012T155114Z.tar.gz/canonical/journal.jsonl:L289; feld=aufgabe.owner | unbekannt | Komzin, Gleb [belegt B2]
B3 | dashboard-20261012T155114Z.tar.gz/canonical/journal.jsonl:L289; feld=verlauf[0].source_title | 2026-06-01 | Meeting Transcription [belegt B3]
B4 | dashboard-20261012T155114Z.tar.gz/canonical/journal.jsonl:L289; feld=verlauf[0].claim | 2026-06-01 | Gleb übernimmt die direkte Anpassung im Dienst, nachdem Nullwerte an eigentlich leeren zweiten Ebenen als Ursache erkannt wurden. Die Reihenfolge der Darstellungszeilen übernimmt dagegen Mathias. Eine bereits abgeschlossene Korre [belegt B4]
B16 | dashboard-20261012T155114Z.tar.gz/canonical/notes.jsonl:L50; feld=wiederverwendung[1].bestandsaussage | unbekannt | Das bilaterale Meeting zwischen Gleb und Niko diente primär als Statusupdate zu laufenden Arbeitspaketen. Zunächst wurde kurzfristig geklärt, dass der morgige Termin auf 15–17 Uhr verschoben wird, damit Darius te [belegt B16]
B28 | dashboard-20261012T155114Z.tar.gz/canonical/journal.jsonl:L289; feld=kontext.thema | unbekannt | Power BI Ergebnisrechnung: Modell und Performance [belegt B28]
Formale Verstöße: 0; Darstellungskürzungen: 410; Quellenkürzungen: 0; gekürzte Zeichen: 53552; ausgelassene Belege: 27.
