> AUSGEFÜHRT am 07.09.2026: Produktionsdeployment dpl_BNi8tEkQeM6F3uFKdPJ9KYA8Hu5S, finale Generation angenommen, Altlogik stillgelegt. Maßgeblich ist PRODUCTION-STATUS-2026-09-07.md. Folgender Plan bleibt als historische Checkliste erhalten. Budgetentscheidung für künftige Automatik separat offen.

> Freigabe 07.09.2026: Der Nutzer hat die Reihenfolge und produktive Übernahme einschließlich finaler Korrekturen und Abschaltung der Altlogik ausdrücklich bestätigt. Vorher die technischen Prüfungen und Modellbewertung Terra/Sonnet abschließen. Keine erneute Übernahmefreigabe nötig. Altbestand ohne Modell-API; künftige Automatik bis zu freigegebenem Kostenrahmen pausiert.

> Aktuelle Freigabe 07.09.2026: Der Nutzer bestätigt die Prüfungsreihenfolge und erteilt jetzt ausdrücklich die Abnahme/produktive Übernahme samt finalen Korrekturen und Abschaltung der Altlogik. Frühere Freigabesperren sind hiermit überholt. Technische Prüfungen, Sicherung/Restore und Modellbewertung Terra versus Sonnet zuerst abschließen. Keine zusätzliche Modell-API für Altbestand, keine kostenpflichtigen Vergleichsläufe. Künftige Automatik bis zu festgelegtem Modell und Kostenrahmen pausiert.

> Navigation-/Einstellungsupdate 07.09.2026: Nutzer verlangt ausschließlich Hellmodus. Lokaler Entwurf auf8832 umfasst nun Übersicht, gegliederte Navigation (Arbeit/Wissen/Einstellungen), Bereichssuche Cmd/Ctrl+K, mobile Navigation, persistierte Gerätepräferenzen und Teamverwaltung via configure_team. Source-/Produktivfreigabe weiterhin nicht erfolgt, keine Automatik aktiviert. Neue Dateiübersicht und Prüfung in .design-workflow/reviews/2026-09-07-navigation-settings-light.md. Authentifizierter Produktions-/isolierter Supabase-Schreibtest der neuen Funktionen bleibt vor Umschaltung erforderlich; lokaler Browser-Test arbeitet ausschließlich auf Testkopie.

> Update 07.09.2026: Der Nutzer hat die Übernahme zunächst abgelehnt und eine neue Gestaltung mit persönlicher Wochenplanung/Teamsteuerung beauftragt. Dieser Entwurf ist nur lokal auf8832 umgesetzt; die unten genannte Vercel-Vorschau enthält ihn noch nicht. Vor jeder Umschaltung neue UI abnehmen, Planungsbefehle authentifiziert im isolierten Draft prüfen, planner.py in alle Runtime-/Backupmanifeste aufnehmen, neues Backendimage und Restore prüfen, neue Vorschau bereitstellen. Frühere Login- oder Google-Freigaben sind keine Freigabe dieses neuen Produktstandes. Altlogikablösung und finale produktive Dubletteninventur bleiben offen.

# Konkreter Umschaltplan — noch nicht ausgeführt

Stand 7. September 2026. Die bisherige produktive App bleibt bis zur Freigabe unverändert.

## Geprüftes Ergebnis

- Alle 1.306 vorhandenen Items aus 106 Quellen wurden direkt durch Codex kontrolliert, ohne zusätzliche Modell-API-Verarbeitung des Altbestands.
- Supabase-Draft Revision106, Archiv492: 194 vollständige Drive-Originale und 298 vorhandene Notizen.
- Abschließender Korrekturvorschlag `614621ff-d766-4f20-8f6e-ad9bd0998fdc` (SHA c9509edbafb1f264f1e9533e96e5fb96291bdaf677960e986bfdfd4c1924a8d0), noch offen: 42 Arbeitsänderungen, 36 betroffene Quellen und zehn explizite Identitätszuordnungen. Ergebnis nach Annahme: 1.280 Aussagen, 69 eigene offene Zusagen, zehn bedingte eigene Zusagen, 252 offene fremde Zusagen und 50 erledigte Schritte.
- Vorschau: https://team-dashboard-632tejjr0-glebkomzin-dels-projects.vercel.app/ ; Deployment dpl_yAYP51FEt2oapq6cPHsg4DSLxfRa.
- 210 Python-Tests, TypeScript, ESLint und Build bestanden; Quellenänderung, Reihenfolgekorrektur und verlorene Annahmebestätigung im synthetischen Browserablauf geprüft. Echter Kontozugriff auf diese letzte Vorschau einschließlich Archiv, Original, Zusammenfassung, historischem Stand und beiden Korrekturdialogen am 07.09. bestanden (evaluation/final-owner-browser-20260907.json).
- Aktuelle Datensicherung und tatsächlicher PostgreSQL-/n8n-Rückspieltest bestanden. Zusätzliches Releasepaket auf Server und Mac bytegenau geprüft.

## Reihenfolge nach Freigabe

1. Google-Drive-Zugang ist am 07.09. erneut verbunden und direkt geprüft: frischer Refresh ohne Sieben-Tage-Laufzeitangabe, Lesezugriff HTTP200; Google-App In Produktion. Neue Automatik bleibt pausiert.
2. Frische Basisrevision106 und unveränderten Vorschlag prüfen. Den freigegebenen Vorschlag mit einer eindeutigen Eigentümerentscheidung annehmen; Ergebnisrevision107 überprüfen.
3. Neue Oberfläche auf der produktiven Domain veröffentlichen und stabile API-Weiterleitung auf den geprüften kanonischen Dienst umstellen. Den Arbeitsbereich kontrolliert aktiv setzen.
4. Make-Szenario5388913 deaktivieren; alte Dashboard-n8n-Workflows inaktiv lassen. Vorbereitetes `ops/cutover/retire-legacy.sql` nach erneuter Inventarprüfung ausführen: 41 Trigger, 30 alte Anwendungsfunktionen, DML-Rechte auf 21 Alttabellen und die beiden alten Cronjobs stilllegen.
5. Neun alte Dashboard-Edge-Endpunkte durch den vorbereiteten 410-Endpunkt ohne Datenbank- oder Modellaufrufe ersetzen. `working-memory-journal` erhalten. Alten Dienst auf Port8797 nach erfolgreicher Routenumschaltung anhalten. Andere Anwendungen und Picnic unverändert weiterbetreiben.
6. Nur für neue Meetings einen ausdrücklich freigegebenen Quellenstichtag und ein kumulatives API-Budget in Server und Supabase setzen. Vorhandener Anthropic-Zugang ist verfügbar; keine Schlüsselwerte ins Protokoll. Den neuen n8n-Workflow und Worker erst nach übereinstimmenden Einstellungen aktivieren. Vor dem Stichtag liegende Quellen bleiben auch bei späterem Auffinden von Modellverarbeitung ausgeschlossen.
7. Produktive Anmeldung, Archiv, Originalbeleg, Arbeitsstand, historische Ansicht, Korrekturprüfung und automatische Aufnahme prüfen. Anschließend eine neue Sicherung des tatsächlich aktiven Standes erstellen und unabhängig kopieren.

## Was die Freigabe umfasst

Die Freigabe muss den obigen Korrekturvorschlag, die produktive Veröffentlichung und die Ablösung der alten Schreibwege umfassen. Ein Quellenstichtag und eine Gesamtkostengrenze für neue Meetings sind noch festzulegen. Die Kostenobergrenze ist kumulativ; ein monatlicher automatischer Reset ist nicht implementiert. Es wird keine erneute API-Verarbeitung des Altbestands genehmigt oder ausgeführt.

Die alten Supabase-Daten, 3.197 Chunks und 71 verbliebenen Embeddings bleiben erhalten. Ihre bisherigen Schreib-/Verarbeitungswege werden abgeschaltet. Der frühere Stichtagsauftrag bis einschließlich31.05.2026 ist keine fortlaufende Löschregel.

## Rückweg

Neue Verarbeitung zuerst pausieren. Vorhandene neue Journalrevisionen und Entscheidungen behalten. Das Releasepaket enthält bisherige Edge-Quellen, Rechte, Triggerzustände, Crondefinitionen und Nginx-Konfiguration. Alte Schreibwege niemals allein aufgrund eines UI-Rollbacks reaktivieren. Details und Grenzen stehen in RESTORE-RUNBOOK.md.

## Ergänzter Auftrag vom 7. September 2026

Alle am heutigen Tag in der Inbox liegenden Meetings/Transkripte werden durch Codex direkt kontrolliert. Keine Modell-API und keine erneute Workflow-Verarbeitung für diesen Bestand. Zum Inventurzeitpunkt sind es 19 offene Meetings vom3.–31.08.2026. Alle19 sind bereits Teil der vollständig manuellen Überführung; die frischen Inbox-Transkripte stimmen exakt mit den archivierten Exporten einschließlich ursprünglichem UTF-8-BOM überein. Die manuell geprüften Textkörper entsprechen den Originalen. Nachweis: evaluation/inbox-manual-followup-20260907.json, privates ID-/Zeilenhash-Inventar unter .local/inbox-manual-followup-20260907.json.

Vor Aktivierung und zum Abschluss die Inbox erneut abgleichen. Bis dahin neu hinzugekommene, zu diesem Auftrag gehörende Quellen ebenfalls direkt bearbeiten, ohne Modell-API oder Workflow. Automatische Quellenverarbeitung frühestens für Meetingdaten ab08.09.2026 freigeben; vorhandene bzw. nachträglich eintreffende ältere Quellen bleiben manuell. Dieser Stichtag ist eine Mindestgrenze, keine schon erfolgte Aktivierung oder Ausgabenfreigabe.

Nach produktiver Umschaltung den gesamten sichtbaren Bestand außer den Meetings selbst auf redundante Einträge prüfen und bereinigen. Aufgaben, fremde Zusagen, Bedingungen, Informationen, Entscheidungen, Risiken und Themenzuordnungen berücksichtigen. Wiederholungen derselben belegten Verpflichtung bzw. desselben Wissenspunkts zusammenführen; unterschiedliche Verantwortliche, eigenständige Lieferungen, Voraussetzungen und widersprüchliche zeitliche Stände nicht pauschal verschmelzen. Originale, Belege und nachvollziehbare Änderungshistorie bewahren. Keine erneute Einzelabnahme hunderter Items durch den Nutzer verlangen. Die abschließende Bestandsprüfung nach der Bereinigung wiederholen und verbleibende Unklarheiten knapp dokumentieren.

## Freigabeanfrage 07.09., 12:15 Berlin

Konkrete Umschaltung und finale Korrekturen dem Nutzer zur Freigabe vorgelegt, Antwort noch ausstehend. Optional vorgeschlagen: ausschließlich neue Meetings ab08.09. mit bisheriger Opus-5-Konfiguration, höchstens10USD kumulativ; alternativ Oberfläche und Bestand umschalten, neue Automatik pausiert lassen. Kein Betrag und kein Modellwechsel bisher genehmigt. Neue Sicherung dashboard-20260907T101250Z.tar.gz mit erneuertem Google-Zugang auf Server und Mac verifiziert,87Dateien, SHA74bd14ca72463885e7e780e909cc0ea9cda6f692f93d566b74f80399b7ed99a7.
