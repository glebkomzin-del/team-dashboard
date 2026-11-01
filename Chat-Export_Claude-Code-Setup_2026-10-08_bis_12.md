# Chat-Export: Claude-Code-Setup, Vault, Hooks, Rollout-Paket, Repo-Sync
Zeitraum: 08.10.2026 – 12.10.2026 · Inhaltlich vollständige Zusammenfassung, kein Wortprotokoll.
Arbeitsweise im Chat: Claude (Chat) formuliert Aufträge, Gleb gibt sie an Opus (Claude Code) weiter, Opus liefert Berichte/Diffs zurück.

---

## 0. Rahmen und Arbeitsprinzipien

- Setup: VS Code + Claude Code (Opus über Vertex, GCP-Projekt `tedi-p-gco-reporting-bi`, Region `eu`), Power-BI-Modeling-MCP, Gemini-Worker über `buddy.ps1`, Obsidian-Vault auf OneDrive als Langzeitgedächtnis.
- Native Claude-Subagents sind im Projekt quota-gesperrt (Haiku/Sonnet = 0). Delegation läuft deshalb nur über den Gemini-Worker.
- Leitprinzipien, die sich durch alles ziehen:
  1. **Regel schlägt Ermessen:** Was nur im Prompt steht, rationalisiert das Modell weg. Wichtiges wird per Hook erzwungen.
  2. **Denken vom Schuften trennen:** Opus urteilt, der Worker liest massenhaft.
  3. **Negativbefund nur mit Evidenz:** „Alles ok“ vom Worker ohne Einzelbeleg gilt als ungeprüft.
- Präferenzen Gleb: direkt, dicht, ehrlich; Reifegrad-Labels; keine Scope-Reduktion; Aufträge immer vollständig neu statt als Ersetzungsanweisung; Schritt für Schritt bei Anleitungen; erst belegen, dann behaupten.

---

## 1. Pläne und Modelle (08.10., abgeschlossen)

- Anthropic: monatliche API-Credits für Max/Team (Max 5x 100 $, Max 20x 200 $), nicht für interaktives Claude Code. „5x/20x“ gilt pro 5-Stunden-Fenster, nicht pro Woche (Sammelklage behauptet geringere reale Faktoren, nur Vorwurf).
- Value-per-Dollar eher Codex, Qualität bei komplexen Aufgaben eher Claude. Empfehlung: Max 20x statt 5x, Testmonat. Keine Entscheidung getroffen.
- Claude Code kann Gemini nicht nativ als Subagent nutzen → Hook + Vertex-CLI-Konstruktion ist der pragmatische Weg.

## 2. Delegations-Gate (08.10., umgesetzt)

- Alter Hook war nur ein Hinweis (`additionalContext`, `once: true`) → Opus delegierte praktisch nie.
- Neu: `delegation-gate.ps1`, blockiert hart (`permissionDecision: deny`) bei `List`/`Export`-Operationen und bei DAX mit `INFO.`, `$SYSTEM.`, `TMSCHEMA`, `DISCOVER_`. Einzel-Get und echte DAX-Abfragen laufen inline (fail-open).
- Erkenntnis: `PreToolUse` kann kein Tool-Ergebnis zurückliefern; Obergrenze ist „blocken + Delegationsbefehl im Deny-Grund“.
- `once: true` wird in `settings.json` ohnehin ignoriert (nur in Skill-Frontmatter gültig).
- Env: `CLAUDE_DELEGATION_BYPASS=1` (Notausgang), Log `~/.claude/logs/delegation-gate.log`.

## 3. Vault-Skill-Umbau (08.10., umgesetzt)

- Befehle: `/go` (Start), `/bye` (Ablegen), `/review-vault` (Pflege; erst seit 08.10. ein echter Slash-Command).
- **Abgestuftes Laden:** Index → Pflicht-Grep `_Alias.md` → Gist (`Read limit 15`) → gezielter Volltext (Grep auf `##` + offset/limit). Retrieval-Test 13/13.
- `_Index.md` von 39,6 KB auf 9,6 KB (reine Zeiger), Alias-Block nach `_Alias.md` ausgelagert.
- **„Ersetzen oben, ergänzen unten“:** Gist und Statusblock werden ersetzt, Körper additiv, Überholtes markiert oder nach `## Historie`.
- `verified:` getrennt von `updated:`, nur nach echter Live-Prüfung.
- Statusblöcke (`## Status`) je offenem Faden mit Pflichtfeld „Fertig, wenn“; Board `_Aktuell.md` als Liste der offenen Fäden.
- Schreibsicherheit: nur gezielte Edits mit Ankertext, nie `Write` auf bestehende Notizen; frisch lesen vor Zitat/Handlung (parallele Sessions, Compaction).
- Konzeptfragen geklärt:
  - Reines Wissen (Modell, Konventionen) bleibt als Notiz, kommt nie aufs Board.
  - `/bye` hält den bearbeiteten Faden aktuell; `/review-vault` prüft mitbetroffene Notizen, die `/bye` nicht sieht (z. B. Umbenennungen über viele Notizen).
  - Automatisches „überall ersetzen“ bei `/bye` ist gefährlich (zerstört Historie), daher Review mit Freigabe.
  - Obsidian ist nur die Oberfläche; der Vault ist ein Markdown-Ordner. Für Team-Wissen später: Git-Repo statt OneDrive, geteiltes Modellwissen von persönlichen Fäden trennen.
- Review-Auslöser: nach Deploy (automatischer Queue-Eintrag durch `/bye`), bei Fälligkeit (Eintrag > 7 Tage oder > 5 Einträge), optional wöchentlich (nicht gebaut). Meldung erscheint bei `/go` und `/bye`; gestartet wird nie automatisch.

## 4. Erster Review-Lauf (08.10.)

- Live bestätigt: 79 Tabellen / 528 Measures / 81 Beziehungen; AGG-Filial-Tabellen und DCS-Stammdaten in DEV entfernt; `DIM CostCenter` ist Live-Name; HochAgg = 1.751.655 Zeilen mit CostCenter (Claim „5.562/RLS-frei“ widerlegt).
- Umgesetzt: Gist GCO_Datenmodell, ER_Performance_INSCOPE korrigiert, Umbenennungs-Sweep konservativ (Historie/Alias ausgenommen), Konsolidierungs-Commit `a45bb07` gepusht in `origin/main` (Prod ungeprüft). Queue 12 → 1.
- `verified:` bewusst nicht gesetzt, wo nur Teile geprüft wurden.

## 5. Session-Übergabe-Hooks („ohne /bye“)

- Ursprünglich: Marker beim getippten `/bye`, `SessionEnd` meldet fehlenden Marker, `PreCompact` meldet ebenfalls, `/go` zeigt Treffer, Quittierung per Suffix `· ausgewertet <Datum>`.
- Fehlalarm 1 (08.10.): `/bye` lief, aber ohne `command_name`-Tag → Marker fehlte. Fix: `/bye`-Schritt 7b setzt den Marker selbst (Session-ID aus `CLAUDE_CODE_SESSION_ID`, belegt).
- Fehlalarm 2 (11.10.): Phantom-Sessions ohne Transcript und wieder geöffnete Sessions. Fix v3: Kriterium „Nutzernachricht nach letztem /bye?“, Marker und lastmsg in `~/.claude/state/`, Marker wird nicht mehr gelöscht, PreCompact nur Log.
- Fehlalarm 3 (12.10.): `claude -p`-Pings aus `bootstrap.ps1` (Testaufrufe) zählten als Sessions. Fix v4: Nachrichten mit `turnOrigin=sdk` ignorieren, Klasse `SDK_NOLINE`. Live aktiviert, Paket nachgezogen (12/12 Tests).
- Wichtig für Kollegen: Ohne v4 hätten sie beim ersten `/go` Fehlalarme gesehen.

## 6. `/go`-Startkarte (09.10., umgesetzt)

- Board-Zeile je Faden mit zwei Unterzeilen `worum` (stabil, statusfrei) und `naechster`. `/go` liest nur `_Aktuell.md`, keine Notizen. Status-Label nur zur Sortierung.
- Vier GitOps-Fäden zu „GitOps-Release DEV“ gebündelt (Reihenfolge: Repo-Stand → ACDOCA → Datenstand → ER-Aggregate); Fachnotizen verweisen per „Board: Teil von …“.
- Kontext-Regel: `00_Kontext_*` wird nie automatisch geändert, `/bye` macht nur „Vorschlag Kontext“. Mandat bleibt statusfrei im Kontext.

## 7. Reuse-Gate „Wiederverwendung vor Neubau“

- Regel: vor jedem neuen Modellobjekt inhaltlich prüfen (Name/Synonym, Semantik über Expressions, Vault, Erweiterbarkeit).
- Hook `reuse-gate.ps1` (MCP-Create und TMDL-Edit/Write) blockiert ohne Marker.
- Ausbaustufen: Tabellen-Marker deckt eigene Spalten; Umbenennung erlaubt (Log RENAME); mehrere Objekte → alle fehlenden genannt; Marker als JSON mit Pflichtfeldern; Nachweis eines frischen Worker-Scan-Laufs (explore, success, < 2 h, ausgeführte DAX); Abdeckung je Basisspalte in Modellschreibweise; Tabellenname allein reicht nicht.
- Live-Scan „Umsatz Vorjahr“: fand > 30 VJ-Measures + VJ-Calc-Items → Neubau wäre redundant. Kurzformen (VJ/PY) und Calc-Items als Pflicht-Suchbegriffe ergänzt. `HSL` existiert im Modell nicht (Spalten heißen `AmountInGlobalCurrency` u. a.).
- Grenzen (dokumentiert): TMDL per Shell umgeht das Gate; das Gate belegt, dass gesucht wurde, nicht dass richtig bewertet wurde.

## 8. Gemini-Worker

- Modell: zunächst „3.8 ist Alias auf 3.5“ angenommen, dann widerlegt. Ursache war der **Agent-Router der Gemini-CLI** (`~/.gemini/settings.json` pinnte 3.5). Fix: `model.name=gemini-3.8-flash` + `experimental.dynamicModelConfiguration=true`. Seitdem nachweislich 3.8 in `eu`, keine Fallbacks (auch kein Region-Fallback auf `global`). Model-Gate bricht bei angefordert ≠ bedient ab. Risiko: experimenteller Schalter, CLI-Version gepinnt (0.60.0).
- **Ausführungs-Gate:** `requires_tools` im Contract; 0 erfolgreiche Tool-Aufrufe → `no_execution`, ein Retry, dann sichtbar verworfen. Dabei echten Bug gefunden (`return ,$miss` + `@()`).
- **Notweg** für den Reuse-Scan: Lead darf die feste Scan-Vorlage selbst ausführen, nur nach gescheitertem Lauf mit `purpose=reuse-scan`, TOPN ≤ 30, max. 6 Abfragen, Logzeile mit run_dir.
- **Approval-Modus:** Read-only-Profile liefen in `plan` → multiplexed PBI-MCP-Tools wurden nicht ausgeführt → „Strategie statt Ergebnis“. Fix: fail-closed Erlaubnisliste statt `yolo` + Sperrliste; DAX-`ExecuteQuery` und lesende Calc-Group-Operationen gehören in die Erlaubnisliste (der Reuse-Scan braucht sie).
- Fehlerquote vorher: 2/19 MCP-Aufträge ohne verwertbares Ergebnis (10,5 %), kleine Stichprobe.

## 9. Berechtigungen

- Vorher: `bypassPermissions` (Deny-Regeln wirkungslos).
- Neu: `defaultMode: acceptEdits`, Allow für Git-Lesebefehle, Worker-/Hook-Skripte; Deny für `git push`, `git merge`, `reset --hard`, `clean`, `branch -D`, `tag -d`, `rm`/`del`/`Remove-Item`/`rmdir`. Löschen nur noch durch Gleb (Ablage `_to_delete/`).
- MCP-Operationen lassen sich per Settings nicht nach Lesen/Schreiben trennen → Schutz über Hooks (`mcp-write-guard.ps1` mit Readonly-Flag) bzw. für den Worker über die Gemini-Policy.

## 10. Kontext-Überwachung

- Befund: `context-watch` lief nur bei Prompts → bei langen autonomen Läufen keine Warnung; Auto-Komprimierung real bei ~158–169k Tokens, Schwellen lagen zu hoch.
- Fix (aktiviert): zusätzlich `PostToolUse` mit Drosselung, Schwellen 115k/128k/148k, Hinweis nach Komprimierung („Protokoll frisch lesen“), Journalzeile „auto-komprimiert“. Zusatzlaufzeit ~335 ms PS-Start je Werkzeugaufruf.
- Problem danach: „Stufe 2 = beenden“ ließ Sessions nach Minuten stoppen. Für den Repo-Auftrag per Auftrag überstimmt („Checkpoint setzen und weiterarbeiten“). **Offen:** Hook-Texte und Schwellen dauerhaft auf „Checkpoint und weiter“ umstellen, Grundlast (MCP-Werkzeugbeschreibungen) messen.

## 11. Rollout-Paket für Kollegen

- Fünf Bausteine: Lead-Modell (Opus 4.8, Effort medium, Vertex eu), Gemini-Worker (3.8-flash eu, Gates, Policies, `WORKER.md`), Mechanik (Skills, Hooks, CLAUDE.md-Block, Berechtigungs-Fragment, Vault-Vorlage), bereinigtes Modellwissen (52 Notizen, ohne Status, ohne Personen, „Team Lead GCO“ statt Name), Installation (`bootstrap.ps1`, `AUFTRAG_KOLLEGE.md` mit Backup → Abgleich → Mechanik → Worker-Test als harter Stopp → Vault NEU oder Migration → Interview max. 6 Fragen → `verify.ps1`).
- Zwei Fälle: Neuinstallation und Abgleich (bestehender Vault wird migriert, Inhalt bleibt).
- Bereinigungsentscheidungen: Fabric-Inventar, PowerBI_MCP, modellbezogene ADRs, GitOps-Notiz aufgenommen (Maßstab „persönlich“, nicht „TEDi-intern“). `[[Validierung_ER]]` als Klartext (eigene, nicht paketierte Notiz). RLS-Vorfälle anonymisiert.
- Stand: ZIP gebaut (`GCO-Claude-Setup-2026-10-09.zip`, mehrfach überschrieben, zuletzt 118 Dateien), Pilot noch nicht gefahren.
- **Offen vor Pilot:** Kontext-Überwachung „Checkpoint statt beenden“ ins Paket; ZIP auf aktuelles Datum umbenennen; Pilot mit einem Kollegen begleiten (Bootstrap auf leerem Rechner ungetestet).
- Begleitdokument `EINSTIEG.md` (One-Pager zu Zweck, Laden, Befehlen, Hooks, Reuse, Delegation) ist im Paket.

## 12. Repo-Sync DEV ↔ Repo und Berichte

**Auftrag:** Repo führend, DEV hängt hinterher; Ordnerstruktur wie DEV; alle Berichte außerhalb des Archivs eindeutig, valide, funktionsfähig, performant; Composites raus; inhaltlich (nicht per Name) umhängen; bewusst Entferntes nicht zurückholen; ins Archiv nur echte Dubletten und Reste; „Defekt ist kein Archivgrund“; nur lesend gegen DEV; Halt vor Deploy.

**Entscheidungen Gleb:**
- Für alle Berichte außer FTE hat das Modell alles; nichts Neues im Modell.
- Ausnahmen (bewusst freigegeben): 3 FTE-Measures; Calc-Item **„FYTD bis Auswahl“** in `Time Intelligence` (YTD bis gewähltem Monat, generisch); 2 Measures **Raumkosten - Filiale / m²** und **Raumkosten - Filiale (in %vUE extern)**.
- Entfernung der Aggregations-/VGL-Schicht (89 Measures, 5 Tabellen) ist gewolltes Refactoring (Commits vor Tag `pre-sync-2026-10-09`).
- RaumKo Filialen nicht archivieren, sondern umbauen: MTD- und YTD-Matrizen nebeneinander (Visual-Filter auf Freie Selektion bzw. FYTD bis Auswahl), EUR-Filter, gleiches für den Sachkonten-Pivot.

**Ergebnis:**
- Alle Berichte binden direkt ans Zentralmodell; `referenzen.csv` 3.073 Referenzen, 0 unaufgelöst.
- FTE Report und Länderübersicht ohne lokale Measures; Vertrieb, Template_Neu, PBIR-Berichte repariert (~1.200 wirkungslose Elemente bereinigt).
- Wertnachweise RaumKo MTD/YTD alt = neu (Δ = 0, auch je Sachkonto). Sachkonten-Pivot: alter Seitenfilter war ebenfalls Raumkosten → keine Kontenverluste.
- 21 berichtslokale Measures bleiben vorerst (Marketing 3 inkl. TEST, Einkauf 18), nachweislich ohne Bezug zu entfernten Objekten → laufen weiter; als Restposten in POST-DEPLOY §7.
- Archiv: Items, die im Workspace existieren, im Sync-Bereich belassen; Quellcodeverwaltung DEV vorher 0 → origin/main als exakter Stellvertreter.

**Deploy (12.10.):** Gates G1–G6 bestanden (G5 mit Ausnahme der 21 Restposten), Merge-Commit `ea4a4fc` auf `main` gepusht, Doku-Commit `543b0da`. Fabric „Alle aktualisieren“ ohne Konflikte. Deny-Regeln danach wieder eingesetzt.
Rollback: `git revert -m 1 ea4a4fc`, push, Fabric „Alle aktualisieren“.

**Post-Deploy (läuft, Branch `post-deploy-2026-10-12`):** Encoding-Bug in Abfrage-Generatoren gefunden und behoben; schwerste FTE-Abfrage 766 ms; alle 21 Berichte statisch 0 unaufgelöst; Marketing/Einkauf wertgetreu.
**Fachlich zu entscheiden:** Zentrale Δ-Measures kappen Abweichungen auf ±100 % (Absolutwerte unverändert).

## 13. Offene Punkte (Stand 12.10. abends)

1. Post-Deploy abschließen: Voll-Test aller Visuals (§2), Restposten Marketing/Einkauf auflösen (§7), Abschlussbericht, Branch reviewen.
2. ±100 %-Kappung der Δ-Measures fachlich entscheiden.
3. Darstellung im Dienst prüfen (neue RaumKo-Matrizen, Zeilengleichheit).
4. Kontext-Überwachung: „Checkpoint und weiterarbeiten“ dauerhaft, Schwellen/Grundlast, ins Paket.
5. Paket-Pilot mit einem Kollegen; ZIP umbenennen.
6. Board und Vault nach Deploy nachziehen, `/review-vault` (u. a. alter Partition-Exception-Eintrag).
7. Auswertung Delegations-Messung (geplant 15.10.), danach Messhook entfernen; Worker-Fehlerquote nach Retry mit erfassen.
8. Optional später: REST-Zugang zu Fabric/Power BI (Modul `MicrosoftPowerBIMgmt`, IT-Freigabe klären); Wissensschicht ins Git-Repo.
