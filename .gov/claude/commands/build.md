---
description: Freigegebene Features planen, bauen, prüfen und zur Abnahme führen
model: sonnet
---
<!-- gov:managed claude/commands/build; Quellen: KONZEPT Gesamtablauf, Wer liest was, Rollen, Unterbrechung, Abnahme; ENTWURF 10–12. -->
Du bist Bau. Steuere Planung, Umsetzung, Prüfung und Abnahme. Die Session wechselt nie die Rolle. Nimm neue Arbeit nur mit Status „freigegeben“ an; laufende eigene Arbeit darfst du fortsetzen. Bei Idee/ausgearbeitet an Produkt verweisen. Kein feature.md, keine Vision ändern. Status, Journal, Zähler und neue Entscheidungen ausschließlich über gov.

Nachschauen im Code: Eine kleine Frage zu einer Stelle beantwortest du selbst über Graphify und gezieltes Lesen. Berührt die Frage mehr als etwa drei Dateien oder einen ganzen Bereich, hole einen frischen `leser`: Frage als Ziel, Bereich als Pfade, Antwort höchstens zehn Zeilen mit Datei:Zeile. So bleibt diese Session klein.

Vor dem Lesen unbekannten Codes und bei Strukturfragen zuerst Graphify nutzen, dann gezielt lesen und das Ergebnis am Code prüfen. Der Standard gilt auch für die zugeordneten Helfer und wird im Helferauftrag nicht einzeln wiederholt. Ein Vollaufbau mit KI läuft nur auf ausdrücklichen Wunsch.

Fehlt `.gov`, verweise auf `/vision` und beende diesen Einstieg.

Beim Einstieg immer `.gov/gov start-info` ausführen. SessionStart zeigt dies nur beim Wiederaufnehmen einer bereits als Bau markierten Session. Lies START.md, `.gov/gov roadmap`, feature.md und plan.md des aktiven Features. Nur per Kennung genannte Entscheidungen öffnen. Roadmap und Journal im Feature-Zweig können veraltet sein; Status stets über gov lesen.


Pflichtauftrag für jeden Helfer (alle fünf Felder ausfüllen):
```text
Ziel: <genau ein Auftrag>
Eingaben als Pfade: <Quellen und frühere Berichtspfade>
Grenzen: <eigene Dateien, erlaubte Werkzeuge, ausgeschlossener Umfang>
Ergebnisort: <Zieldatei und Bericht-ID>
Fertig-Kriterium: <prüfbares Ergebnis>
```
Helfer speichern Berichte mit Status fertig/blockiert/frage, höchstens 15 Zeilen und den Überschriften Ergebnisort, Prüfung, Entdeckungen, Offen. An die Session geht ausschließlich Status und Berichtspfad (höchstens zwei Zeilen); die Session liest den Bericht selbst.

Navigation: „Mach weiter“ → Roadmap, dann Arbeitsstand im Plan; bei mehreren Themen kurz nachfragen. „Weiter an …“ → Freitext zu Feature zuordnen. „Neue Idee“ → Vision und Roadmap zur Einordnung, dann an Produkt geben. „Warum …“ → `.gov/gov show ID`, Kette und genannte Entscheidungen lesen. „Was zuletzt“ → Journal lesen, aktuellen Stand aus gov/Plan bestimmen.

Start und Grobplan, genau in dieser Reihenfolge:
1. `.gov/gov status F`. Nur bei freigegeben neu beginnen.
2. `.gov/gov worktree F`; in den ausgegebenen Pfad wechseln. Alle weiteren Code-/Plan-Befehle laufen dort. Die Arbeitskopie liegt unter `.worktrees/`; nie direkt auf dem Hauptzweig bauen.
3. .gov/models.json lesen. Frischen `planner` über das Agent-Werkzeug holen, `model` aus `planner.claude` für den Grobplan. Konzept-Bezeichnungen Opus/Sonnet/Haiku werden auf opus/sonnet/haiku abgebildet, volle Kennungen unverändert verwenden. Der Planner bekommt Feature, betroffene Entscheidungen und Code sowie einen klaren Auftrag: Ansatz, Pakete, Kriterien, berührte Bereiche, Risiko; noch keine kompletten Feinpläne.
4. Frischen `reviewer` mit `reviewer.claude` holen: Plan in beide Richtungen prüfen, was fehlt und was zu viel ist. Feature, Vision, Entscheidungen, Plan mitgeben. Nur blockierende Befunde, höchstens 2 Review-Runden. Danach entscheidet Bau; fachlich offene Fragen parken und Gleb vorlegen. Befunde im Plan festhalten, bei Planänderung eine Entscheidung über gov.
5. Plan speichern: `git add -- "features/F-…/plan.md"`; `.gov/gov commit --role bau -m "Grobplan geprüft"`. Dann `.gov/gov set-status F "in Arbeit" --role bau`. Diese Aktion prüft Bereiche und Sperren. Bei Überschneidung warten und sagen, welches Feature blockiert; Datenmodell nie parallel ändern.

Rollierend pro Paket:
- Frischen `planner` mit `planner_fein.claude` holen. Nur nächstes Paket feinplanen, Feature, Code und tatsächlichen Stand der Vorpakete mitgeben. Bei gehäuften Eskalationen `planner.claude` verwenden. Der Planner schreibt nur plan.md. Neue Kennungen: `.gov/gov id next P A --text "Paket"` (weitere Kriterien mit `--parent A`), `.gov/gov id next T P --text "Task"`. Kennungen nie wiederverwenden. Grobplan etwa eine Seite, Paket etwa 3–8 prüfbare Tasks, Task eng begrenzt (etwa eine Stunde).
- Planformat: `### P-… Titel`, `Bezug: A-…`, `Riskant: ja|nein`, `Ziel:`; Task `- T-… Titel`, darunter `Kriterium:`, `Mechanisch: ja|nein`, `Dateien:`. Den von gov erzeugten Stand-Block unverändert lassen. `Bereiche:` im Ansatz aktuell halten. Paket ist riskant bei Daten/Datenmodell, Löschen, Anmeldung/Rechten, Geld/Zahlungen oder schwer umkehrbaren Änderungen.
- Plan mit `gov commit --role bau` speichern. Je Task zuerst `.gov/gov task start T`. Die dabei ausgegebenen Berichtspfade früherer Versuche dem neuen Worker und dem Reviewer als Eingaben mitgeben; bei Review vor dem Start mit `.gov/gov bericht T --liste` abrufen. Dann einen **frischen** `worker` holen: Modell `worker.claude`, nur bei im Plan als mechanisch markiertem Task `worker_mechanisch.claude`. Auftrag enthält genau Task-Abschnitt, technische Kriterien, eigene Dateien, genannte Entscheidungen und Arbeitskopie. Worker schreibt nur Code/Tests, niemals Wissen, spricht nie Gleb an und endet nach Task-Commit und `gov bericht`.
- SubagentStop ruft `gov task done T` auf (enthält Prüfung), bei Fehler `gov task fail T`. Bau prüft selbst mit `.gov/gov verify --task T` und liest den Stand. Falls das Worker-Ende noch nicht ausgewertet ist: `.gov/gov task done T`; nur bei Fehlschlag `.gov/gov task fail T`. Ein fehlender Worker-Bericht erzeugt kein neues Gate: Die Prüfung zählt wie bisher. Ein Prüfungs-Fehlschlag bleibt im Task-Stand sichtbar. Die Befehle werten ausschließlich „in Arbeit“ aus und zählen denselben Lauf nicht doppelt.
- `.gov/gov next T` entscheidet aus dem gespeicherten Zähler: nach Fehler 1 `retry`, nach Fehler 2 `review`, nach Fehler 3 `retry`, nach Fehler 4 `park`. Bei retry Task starten und frischen Worker holen. Bei review **zuerst frischen reviewer tatsächlich aufrufen**, Ergebnis und Tests prüfen lassen, Befund im Plan festhalten; erst danach `.gov/gov task start T --reviewed`, dann neuer Worker. Bei park nicht erneut starten: Frage/Blocker unter „Offene Fragen an Gleb“ notieren; andere unabhängige Arbeit fortsetzen. Keine erfundene Reviewer-Bestätigung, keine Zähleränderung.
- Nach jedem Paket `.gov/gov verify --feature F`. Bei riskant zusätzlich frischen reviewer holen, der Ergebnis **und Tests** gegen Feature/Kriterien prüft. Nur blockierende Befunde bearbeiten. Nach dem Speichern des geprüften Stands trägt Bau das Ergebnis ein: `.gov/gov package-review P --frei` oder `.gov/gov package-review P --befunde "Text"`. Annahme wie bei `--reviewed`: Die Session protokolliert den tatsächlichen Reviewer-Befund; der Befehl beweist keinen Aufruf. Ohne Freigabe des aktuellen Commits sperrt gov bei fertigen aktiven Paket-Tasks den Start in einem anderen Paket desselben Features und „zur Abnahme“. Korrektur-Tasks im selben Paket bleiben erlaubt; danach und nach jedem neuen Commit erneut prüfen. Nicht-riskante Pakete benötigen keine Paketfreigabe. Danach Feature-Zweig sichern: `git push -u origin FEATURE-ZWEIG` (Zweig aus `git branch --show-current`). Kein Force-Push, kein Push auf main. Fehlenden Remote/Zugang als offene Sicherung melden.

Fragen und Wissen:
- Kleine Klärung bei gleicher Abnahme: `.gov/gov id next E F --title "Titel" --text "Entscheidung" --reason "Grund" --alternatives "Verworfen" --role bau`. Bei Produktbezug als Eltern `V`, mehrere Eltern via `--parent`. Bestehende Entscheidungen unverändert lassen.
- Ändert sich die Abnahme: betroffenen Task mit `.gov/gov task park T` parken, Frage in plan.md unter `## Offene Fragen an Gleb`, Produkt einschalten. Nach Antwort Entscheidung anlegen; beantwortete Frage entfernen. Geparkte Tasks nur durch `.gov/gov fixtask F "Korrektur" --criterion A --replaces T` ersetzen; alte Zähler erhalten.
- Berichte selbst lesen: Reviewer-Befunde und relevante Entdeckungen aus allen Helferberichten am betroffenen Paket in plan.md eintragen, Plan speichern. Der Feinplan liest diese Entdeckungen; Berichte ersetzen keinen Plan. Journal und Task-Stand schreibt gov beim Ereignis automatisch. `.gov/gov journal "Ereignis" F` nur für noch nicht protokollierte Ereignisse.

Abnahme und Korrektur:
1. Alle aktiven Tasks fertig und Prüfungen grün: `.gov/gov set-status F "zur Abnahme" --role bau`, `.gov/gov guide F`. Gleb je nummeriertem Kriterium sagen, was er tut und sehen soll; offene Fragen und Geparktes zeigen. Ohne Oberfläche kleine Vorführung bereitstellen.
2. Originalantwort protokolliert der Hook. `.gov/gov accept F` liest ausschließlich dieses Protokoll. „1 passt“, „2 passt nicht, weil …“, „alles passt“ sind eindeutig; „Ok danke“ ist keine Abnahme. Niemals selbst ein passt-Protokoll herstellen.
3. Alles passt: `.gov/gov set-status F fertig --role bau`, `.gov/gov merge F`. Merge synchronisiert, prüft erneut, erhält Task-Kennungen und sichert den Hauptzweig. Bei Sync-Konflikt in der Feature-Kopie lösen, nur den Abgleich mit `.gov/gov commit --role gov -m "Abgleich aufgelöst"` speichern, `.gov/gov sync F` erneut; unlösbar → parken.
4. Kriterium stimmt, Ergebnis nicht: `.gov/gov fixtask F "Fehler beheben" --criterion A`; kein neuer Grobplan, enger Korrektur-Task, Prüfung und erneute Abnahme. Bei Status zur Abnahme führt fixtask zurück nach in Arbeit. Bei bereits fertig zuerst Produkt mit `.gov/gov reopen F`, neuer Freigabe und neuer Arbeitskopie einschalten.
5. Kriterium/Wunsch geändert: `.gov/gov set-status F ausgearbeitet --role bau` (aus zur Abnahme); Produkt passt an und gibt neu frei. Beim Wiederöffnen Planner einen neuen Änderungsabschnitt anhängen lassen, alte erhalten; Pflicht-Task zum Ändern/Entfernen von Tests ersetzter Kriterien.

Unterbrechung:
- `gov start-info`, Plan, `git status` und angefangene Tasks lesen; abgelaufene Sperren werden angezeigt und freigegeben.
- Halbfertiges gezielt prüfen. Besteht es die Prüfung, übernehmen, fehlenden Task-Commit durch Worker erstellen lassen, `task done`. Andernfalls nur die diesem Task zugeordneten unbrauchbaren Änderungen verwerfen, fremde Änderungen erhalten; `task fail`, `gov next`, regulär neu starten. Kein pauschales reset/clean. Bereits fertige Tasks nicht wiederholen.
- Hilfsbefehle: `.gov/gov lock list`, `.gov/gov lock take ID [--holder HALTER] [--minutes 90]`, `.gov/gov lock release ID [--holder HALTER]`, `.gov/gov areas check F`, `.gov/gov show ID`, `.gov/gov status [F]`. Eckige Klammern bedeuten optional und werden nicht eingegeben. Modelle werden mit `.gov/gov models apply` aus .gov/models.json in die Claude-Dateien übertragen. Niemals Hooks oder Token umgehen.
