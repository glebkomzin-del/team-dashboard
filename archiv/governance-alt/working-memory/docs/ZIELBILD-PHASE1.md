# Zielbild und Weg: Arbeits-Memory bis zur Übergabe an die Arbeits-KI
Quellen: Chat-Export 08.–12.10.2026 (eingearbeitet)

Stand 13.10.2026. Quelle der Anforderungen: Aussagen von Gleb in dieser Sitzung. Status je Aussage: **belegt** (aus Daten/Code), **Annahme**, **offen**.

## 1. Deine Aussagen, strukturiert

### Ziel
Ein System, das dir die Routine abnimmt: relevante Aufgaben aus deinem Arbeitsalltag notieren, verfolgen (wie weit sind sie), den Kontext mitdenken und beantworten, wenn du fragst. Es endet in Phase 1 mit einer **vollständig vorbereiteten Übergabe an die KI bei der Arbeit**. Phase 2 (danach): Ausführung dort, gegen den Vault.

### Anforderungen
| # | Anforderung | Quelle (sinngemäß) |
|---|---|---|
| R1 | Gegen das System Fragen stellen können (Memory) | "wogegen ich Fragen stellen kann" |
| R2 | Aufgaben automatisch erfassen und verfolgen, Fortschritt kennen | "Aufgaben nicht selber tracken" |
| R3 | Nur Wichtiges erfassen, nicht jeden Klacks | "nicht jeden Klacks … relevante Dinge" |
| R4 | Kontext mitdenken (Personen, Themen, Historie, frühere Gespräche) | "ganzer Kontext muss mitbedacht werden" |
| R5 | Je Aufgabe vorab ermitteln: Art (Power BI?), selbst machbar ohne KI?, Scope, passendes Modell/Bericht vorhanden?, Vorlagen/Vorarbeiten?, frühere Gespräche?, was genau gefordert | Beispielkette Power BI |
| R6 | So weit automatisieren, bis die KI nicht mehr belegt weiterkommt; nie improvisieren oder halluzinieren; "haben wir schon gemacht" nur belegt | "nicht halluzinieren" |
| R7 | Ergebnis immer dir zur Abnahme vorlegen, auch Review, E-Mail-Entwurf, Erinnerung | "mir zur Abnahme festgelegt" |
| R8 | Breite Ausführungsfähigkeit (Review, Entwurf, Erinnerung, Berichtsoptimierung, Entwicklung) | "möglichst vielfältig" |
| R9 | Wissensarchitektur: Dashboard = Arbeitskontext (was passiert bei mir); Obsidian-Vault auf der Arbeit = Modellwissen; getrennt, aber Aufgaben laufen dagegen | "semantisch trennen" |

### Randbedingungen (Präzisierung)
| # | Randbedingung |
|---|---|
| B1 | **Keine UI im Dashboard.** Erinnerung und Bedienung über VS Code, E-Mail, Power BI und was lokal an MCPs/APIs vorliegt |
| B2 | Phase 1 reicht **bis zur Übergabe** an die Arbeits-KI; Ausführung und Vault-Brücke sind Phase 2 |
| B3 | Frühere Optimierungsgespräche liegen in **anderen Chats (nicht Claude Code)**; mir derzeit nicht zugänglich |
| B4 | Kosten: Test bis 2–5 EUR freigegeben; Zugangsdaten im Projekt dürfen genutzt werden |
| B5 | Arbeitsweise: Teilaufgaben bei jeder Möglichkeit an Codex; Tests nur mit vorab definiertem Erfolgskriterium, vollständig ausführen, Fehlschlag analysieren statt verwerfen |
| B6 | Qualität darf bei Kostensenkung nicht sinken; Architektur muss mit wachsendem Bestand tragen |
| B7 | **Arbeitsumgebung (Phase 2):** VS Code mit Claude Code (Opus über Vertex in GCP, Region `eu`), Gemini über `buddy.ps1` und Power-BI-Modeling-MCP; Vault = Markdown-Ordner auf OneDrive, Obsidian nur als Oberfläche; KI-Zugriff: Index → Alias-Grep (`_Alias.md`) → Gist (15 Zeilen) → gezielter Volltext; Befehle `/go`, `/bye`, `/review-vault`; Regeln: Wiederverwendung vor Modellneubau, Notizen nur gezielt editieren, Kontextänderungen nur als Vorschlag, kein Push/Merge/Löschen durch KI (Löschen macht Gleb), `verified:` nur nach echter Live-Prüfung, Teamwissen ohne Personenbezüge (Chat-Export §§0, 3, 6, 7, 9, 11) |

## 2. Vergleichsplan: was wird wogegen geprüft

Soll = Zielbild-Dimension. Ist = belegte Eigenschaft des Systems. Maßstab = womit gemessen wird.

| Dim. | Soll (aus) | Ist-Beleg | Maßstab / Methode | Stand |
|---|---|---|---|---|
| D1 Erfassung und Relevanz | nur Wichtiges (R3) | Regelbasiertes, erklärbares Relevanz-Gate (`tools/relevance/`, 20 Tests); Relevanzlauf: 663 Aufgaben, wichtig 214 (32,3 %), standard 384 (57,9 %), kleinigkeit 65 (9,8 %); Schwellen nach Erstlauf mit 90 % "wichtig" von 16/36 auf 36/56 angehoben | Nicht an deinem Urteil kalibriert; Stichprobe `tools/relevance/stichprobe.md`; Kalibrierung über die 40er-Bewertungsliste mit `calibrate.py` offen | gebaut; Kalibrierung offen |
| D1b Bestandspflege | Aufgabenbestand bleibt aktuell | Frühere Bestandsauswertung (12.10.): 664 Aufgaben, 509 offen (342 ohne Frist), 218 aktive ≥ 90 Tage alt, Median 55 Tage; M2-Snapshot (13.10.): 581 aktive Aufgaben ohne auswertbare Frist | Prüfhinweise durch M3 vorhanden; Archivlogik offen | teilweise gebaut |
| D2 Verfolgung | Status/Fortschritt automatisch (R2) | Lebenszyklus offen/wartend/erledigt, Ereignisse, Fristen vorhanden; Erinnerung gebaut (`tools/reminders/`, 49 Tests): überfällig 43, bald fällig 0, Stillstand 188, ohne Frist >45 Tage 215, nachfassen 61, Frist unklar 136; Digest 15 Einträge; Sol-Lebenszyklusurteile im ungefilterten Kontroll-Replay nur 2 von 4 reproduziert, beide `progress`-Urteile verpasst (13.10.) | Trefferquote der Statusurteile gegen Nutzerentscheidungen; Modell-gegen-Modell ist kein Wahrheitsmaßstab; Zustellung und Compliance offen | Erinnerung gebaut; Zustellung offen; Sol-`progress`-Urteile instabil |
| D3 Memory/Fragen | Fragen mit Belegen (R1) | Memory-MCP gebaut (`tools/memory-mcp/`, 49 Tests, Review ACCEPT); Snapshot am echten Bestand: 664 Aufgaben (509 offen), 581 aktive Aufgaben ohne auswertbare Frist; Abfrage 0,5–1 ms nach einmaligem Indexaufbau von ca. 100 s; persistenter Cache fehlt; Live-Modus nur lesend; QA mit Quellen, semantische Treffer sind Auswahl, nicht Vollständigkeit (`qa_service.py:307`) | Fragenset mit Soll-Antworten (Goldfragen) gegen Archiv; 65 gespeicherte Fragen als Start | gebaut; Goldfragen-Abnahme nicht gemessen |
| D4 Kontext | Personen, Themen, Historie (R4) | Matter-Verknüpfung, Team/Aliasse, Archivbezug vorhanden | Kontexttreffer je Aufgabe im Test D6 | nicht gemessen |
| D5 Kanäle ohne UI | Übergabe an Claude Code in VS Code als Datei/Prompt, nicht über UI (B1, B7) | Memory-MCP und Erinnerungs-Digest vorhanden; `tools/daily/` in Arbeit (täglicher Lauf lokal, kein Versand); Gmail-Entwurf/Push noch nicht angebunden | Übergabe des Auftragspakets als Datei/Prompt an Claude Code in VS Code testen; Lieferweg zur Arbeit und Compliance offen | MCP/Digest vorhanden; Zustellung offen |
| D6 Übergabe-Vertrag | Markdown-Auftragspaket mit Front-Matter gemäß M4 (R5–R7) | `tools/handover/` gebaut (92 Tests); Gerüst + belegte LLM-Synthese mit gpt-6.1-sol: 5 Aufgaben, 0,117 USD, 0 Belegverstöße; `fertig_wenn` in 0/5 belegt (immer begründete Annahme), 0 Felder "unbekannt"; Wiederverwendungs-Aussagen 8/8 im Beleg; Pakete 4–6 KB, ≤ 51 Zeilen | Test an ≥10 echten Aufgaben: Paket nach M4-Schema gegen Nutzerurteil "reicht der Arbeits-KI zum Loslegen?"; Annahmen sind kein Beleg, Abnahme durch Gleb erforderlich | gebaut; Abnahme offen |
| D7 Vault-Brücke | Aliasbegriffe für den Alias-Grep und Verweise auf Vault-Notizen im Auftragspaket (R9, B7) | nichts vorhanden; Vault extern als Markdown-Ordner auf OneDrive (Chat-Export §3) | Phase 1 liefert Aliasbegriffe und Notizverweise; Zugriff über Index → Alias-Grep → Gist → gezielten Volltext erfolgt auf der Arbeitsseite, nicht aus dem Dashboard | Phase 2 |
| D8 Kosten/Skalierung | günstiger ohne Qualitätsverlust (B6) | Produktionsränge A=30,k=5: 64/64 bei 49,1 % Kandidaten; gefilterter Sol-Replay: 0 Filterverluste bei 6 Lebenszyklus-Positiven/4 Zielbeobachtungen, Endantwort-Recall 2/5; gesamt ≈ −33 bis −38 % Kosten, zusätzlich zum Cache-Fix ≈ −20 bis −27 % nur kontrollnormierte Näherung | Offline-Replay je neues Meeting mit fachlicher Abweichungsprüfung; echter Schattenbetrieb braucht getrennten Ledger/Outbox und Publikationssperre; wöchentlicher Vollabgleich im Batch (50 % Tarifnachlass) als Sicherheitsnetz vorgeschlagen | Stand 13.10.: 69/69 PoC-Tests; Hot-Set weder widerlegt noch bewiesen, Pflichtfall 25 Tage/Rang 12 offen; keine Produktivfreigabe; Luna verworfen |
| D9 Betrieb/Datenfluss | produktiv, sicher (früherer Auftrag) | Betrieb, Sicherung, Restore dokumentiert produktiv | Stichproben; Datenfluss Arbeitsmeetings → privates System → Arbeits-KI klären | offen |

## 3. Zielbild

```
Meeting / Dokument
   │  Erfassung (heute vorhanden)
   ▼
Arbeits-Memory (Dashboard, Datenbank, Archiv)  ◄── Fragen (VS Code / Claude / Power-BI-Umgebung, MCP/CLI)
   │  Relevanz-Gate (gebaut: regelbasiert und erklärbar; Kalibrierung an deinen Entscheidungen offen)
   │  Verfolgung (Lebenszyklus und Fälligkeitsüberwachung vorhanden; Zustellung offen)
   ▼
Aufgabe (relevant, belegt, mit Kontext)
   │  Aufbereitung (gebaut; Abnahme offen): Art · Bearbeitungsweg · Scope · Vorarbeiten/Vorlagen · frühere Gespräche · Anforderungen · offene Fragen
   ▼
Auftragspaket ──► Übergabe an Arbeits-KI (Phase 1 endet hier) ──► Ausführung gegen Vault (Phase 2) ──► Abnahme durch dich
        ▲
        └── Erinnerungen / Status: MCP und Digest vorhanden; Zustellung per E-Mail/Push offen
```

Grundsatz (Soll): Jede Aussage im Paket ist belegt (Quelle im Memory) oder ausdrücklich als "unbekannt" markiert. Kein Raten. Stand M4: Das Modell füllt Felder lieber mit begründeten Annahmen; 0 Felder "unbekannt" und `fertig_wenn` in 0/5 belegt. Der Grundsatz ist damit noch nicht erfüllt.

### Lücken (Ist → Soll)
1. Relevanz-Gate gebaut; Kalibrierung an deinem Urteil offen (D1).
2. Erinnerung/Fälligkeitsüberwachung gebaut; Zustellung und Compliance offen (D2).
3. Memory-MCP und Digest vorhanden; Abruf aus VS Code und Lieferweg noch abzunehmen (D5).
4. Auftragspaket gebaut; Annahmen statt "unbekannt" und Abnahme durch dich offen (D6).
5. Kosten wachsen linear mit dem Bestand (D8).
6. Frühere Gespräche mit Optimierungswissen fehlen im Kontext (B3).

## 4. Weg (Phase 1)

| Meilenstein | Ergebnis | Abnahmekriterium (vorab) |
|---|---|---|
| M0 Kosten-Fundament | Sol-Abgleich mit Hot-Set-Filter A=30,k=5, Sicherheitsnetz durch wöchentlichen Vollabgleich im Batch (50 % Tarifnachlass), Delta-Ausgabe; Evidenzsammlung per Offline-Replay oder isoliertem Parallelbetrieb | Kosten je Meeting einschließlich Sicherheitsnetz ≥ 40 % niedriger bei ≥ 62/64 Treffern (bzw. ≥ 97 %) und ≥ 95 % gleichen Zielaufgaben auf ≥ 20 neuen Meetings; vollständige Endantworten, fachlich geprüfte Abweichungen und Pflichtfall Alter 25 Tage/Rang 12 nachgewiesen; Parallelbetrieb nur mit getrenntem Ledger/Outbox und Publikationssperre |
| M1 Relevanz-Gate | Baustein gebaut (`tools/relevance/`, 20 Tests); am Bestand: 663 Aufgaben, wichtig 214 (32,3 %), standard 384 (57,9 %), kleinigkeit 65 (9,8 %); Schwellen nach Erstlauf (90 % "wichtig") von 16/36 auf 36/56 angehoben; regelbasiert, erklärbar, nicht an deinem Urteil kalibriert; Stichprobe `tools/relevance/stichprobe.md`; Kalibrierung über die 40er-Bewertungsliste (`calibrate.py`) offen | Du bewertest 30–50 Aufgaben (wichtig/Klacks/unklar, ~15 Minuten); Gate trifft dein Urteil auf ≥ 85 % der Aufgaben; verworfene bleiben auffindbar |
| M2 Memory als Werkzeug | Gebaut (`tools/memory-mcp/`, 49 Tests, Review ACCEPT); Snapshot-Modus am echten Bestand: 664 Aufgaben (509 offen); Abfrage 0,5–1 ms nach einmaligem Indexaufbau von ca. 100 s (persistenter Cache fehlt noch); Live-Modus nur lesend; 581 aktive Aufgaben ohne auswertbare Frist | Fragenset (≥ 30 Goldfragen): ≥ 90 % belegt richtig; Abruf aus VS Code nachgewiesen |
| M3 Erinnerung | Gebaut (`tools/reminders/`, 49 Tests); am Bestand: überfällig 43, bald fällig 0, Stillstand 188, ohne Frist >45 Tage 215, nachfassen 61, Frist unklar 136; Digest 15 Einträge; Zustellung (Gmail-Entwurf/Push) noch nicht angebunden, Compliance offen | 5 reale Aufgaben erzeugen rechtzeitige, belegte Erinnerungen, keine Doppelmeldungen |
| M4 Auftragspaket | Gebaut (`tools/handover/`, 92 Tests); Markdown-Gerüst mit Front-Matter (Schema unten), Klassifikator und Kontextsuche + belegte LLM-Synthese (gpt-6.1-sol, 5 Aufgaben, 0,117 USD, 0 Belegverstöße); `fertig_wenn` in 0/5 belegt (immer begründete Annahme), 0 Felder "unbekannt" (Modell füllt lieber mit Annahmen); Wiederverwendungs-Aussagen 8/8 im Beleg; Pakete 4–6 KB, ≤ 51 Zeilen; Abnahme durch Gleb erforderlich | 10 reale Aufgaben: ≥ 8 Pakete von dir als "reicht zum Loslegen" bewertet; 0 erfundene Vorarbeiten |
| M5 Phase-1-Abnahme | Zusammenschluss `tools/daily/` in Arbeit (täglicher Lauf lokal, kein Versand); Ziel: End-to-End Meeting → Aufgabe → Paket → deine Abnahme, Kostenbericht | Alle vorherigen Kriterien erfüllt; Betrieb und Sicherung unverändert grün |

Stand M0 (13.10.): Rangvalidierung 64/64 bei 49,1 % Kandidaten; abschaltbare Kopie mit 69/69 PoC-Tests. Gefilterter Replay: 0 beobachtete Filterverluste, Lebenszyklus-Endantwort-Recall 2/5, Zielübereinstimmung 50/53 = 94,3 %; ungefilterte Kontrolle nur 2/4 Lebenszyklusurteile reproduziert. Keine Abnahme: kleine vorselektierte Stichprobe, eine Nachforderung statt Endform, Pflichtfall budgetbedingt nicht ausgeführt, neue Meetings und Sicherheitsnetz ungeprüft. Gesamtqualitätsmaßstab nicht erfüllt; Vollsuite der Kopie weiterhin mit zehn Baseline-Fehlern. Belege und Kostenabgrenzung: [PoC-README](../evaluation/poc-tiered-reconcile-20261012/README.md#ergebnis-hot-set-replay-1310).

Auftragspaket-Schema für M4 (gemäß Auftrag; nicht im Export spezifiziert):

```markdown
---
worum: "Worum geht es?"
naechster: "Nächster Schritt"
fertig_wenn: "Prüfbare Fertig-Bedingung"
art: "power-bi-bericht | review | entwurf | erinnerung (z. B.)"
bearbeitungsweg:
  weg: "selbst | ki | delegieren"
  begruendung: "Begründung für den Bearbeitungsweg"
scope: "Umfang und Grenzen des Auftrags"
wiederverwendung:
  - vorhanden: "Vorhandenes Modell, Bericht oder Vorlage; falls unbekannt: offen"
    quelle: "Quelle, die die Wiederverwendung belegt; falls fehlend: offen"
alias_begriffe:
  - "Suchbegriff für den Alias-Grep im Vault"
kontext:
  thema: "Thema mit Beleg"
  personen: "Personen mit Beleg"
  meetings:
    - datum: "Datum; falls unbekannt: offen"
      beleg: "Quelle zum Meeting"
vorarbeiten_und_vorgespraeche:
  - "Vorarbeit/Vorgespräch mit Beleg oder: keine gefunden"
offene_fragen:
  - "Noch zu klärende Frage"
abnahme: "Was du am Ergebnis prüfst"
belege:
  - "Quelle → Aussage"
reifegrad:
  - aussage: "Jede Aussage im Paket einzeln"
    status: "belegt | Annahme | unbekannt"
---
```

Lieferweg des Pakets zur Arbeitsseite (OneDrive-Ordner, Git, E-Mail) ist offen und braucht eine Compliance-Klärung.

Reihenfolge: M0 und M1 zuerst (tragen alles weitere), M2 vor M3/M4 (Kanal), M4 setzt M1 und M2 voraus.

## 5. Offene Punkte an dich
1. Frühere Chats mit Optimierungswissen: Export/Zusammenfassung oder Ablageort (ich sehe sie nicht).
2. Primärkanal für Erinnerungen: E-Mail, Push, VS Code?
3. Was zählt als "wichtig"? Das regelbasierte Gate ist noch nicht an deinem Urteil kalibriert; Maßstab ist deine Bewertung der 40er-Liste (siehe Punkt 6).
4. Datenfluss: Arbeitsmeetings laufen durch dieses private System; die Übergabe an die Arbeits-KI muss das ausdrücklich zulassen.
5. Lieferweg des Pakets (OneDrive/Git/E-Mail) und ob dafür Arbeitsdaten das private System verlassen/betreten dürfen: offen; nicht im Export geklärt.
6. Bewertung der 40 Aufgaben in `evaluation/poc-tiered-reconcile-20261012/m1-bewertung/aufgaben-bewertung.md` als Maßstab für den Relevanzfilter: offen; nicht im Export enthalten.

## 6. Risiken und Grenzen
- Modelllabels aus dem Replay sind keine fachliche Wahrheit; Sol reproduziert im ungefilterten Vergleich nur 2/4 Lebenszyklusurteile, beide `progress`-Urteile werden verpasst (R2). Auch Schattenbetrieb allein beweist keine allgemeine Verlustfreiheit; neue Meetings und fachliche Prüfung sind erforderlich.
- Hot-Set-Restrisiko (A=30,k=5): Relevante Aufgabe Alter 31 Tage, Suchrang ≥ 5, keine exakte ID-Nennung → still nicht geprüft. 0 Filterverluste bei 6 Lebenszyklus-Positiven bedeuten nur eine einseitige 95-%-Obergrenze von 39,30 % unter hypothetischer Unabhängigkeit; kleine vorselektierte Stichprobe, Pflichtfall Alter 25 Tage/Rang 12 offen.
- Sicherheitsnetz vorgeschlagen: wöchentlicher Vollabgleich im Batch (50 % Tarifnachlass), mit Evidenzsammlung per Offline-Replay je neues Meeting. Umsetzung und Wirksamkeit sind offen; der reguläre Worker veröffentlicht, echter Parallelbetrieb braucht getrennten Ledger/Outbox und Publikationssperre. Hot-Set nicht ohne weiteres produktiv.
- Relevanzurteil kann echte Zusagen verwerfen: Verworfenes bleibt auffindbar, nicht gelöscht.
- Vault ist extern; Phase 1 beweist nur den Schnittstellenvertrag, nicht die Ausführung.
- Modell füllt Felder lieber mit Annahmen statt "unbekannt" (M4: 0 Felder "unbekannt", `fertig_wenn` in 0/5 belegt); Belegverstöße und unbelegte Annahmen sind getrennt zu prüfen.
- Relevanzschwellen 36/56 sind noch nicht an deinem Urteil kalibriert; die Anpassung nach dem Erstlauf ersetzt die 40er-Bewertung nicht.
- Memory-Indexaufbau dauert ca. 100 s; persistenter Cache fehlt noch, schnelle Abfragen gelten erst nach dem Aufbau.
- Datenträger des Macs zu ~100 % voll; Sicherungen gefährdet.
- Lieferweg zur Arbeit und Compliance ungeklärt; Zustellung (Gmail-Entwurf/Push) noch nicht angebunden.
