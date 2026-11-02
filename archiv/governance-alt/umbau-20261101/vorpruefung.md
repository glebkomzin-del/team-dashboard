# Umbau-Vorprüfung · 2026-11-01

Status: Ausgangsbestand zu klären; migrate start/apply/finish noch nicht ausgeführt.

## Ausgangsstand
- Eindeutige Git-Wurzel: meeting-os; Remote https://github.com/glebkomzin-del/team-dashboard.git.
- Aktiv: codex/working-memory-redesign, d6f3906c4d62615fbc074ba9677718c96a98cf80; 104 Commits vor main, 0 zurück.
- main: 87aa669baaa02078bf0e20fefe528a429793ab31. Eine Arbeitskopie; kein lokaler hooksPath/aktiver Git-Hook gefunden.
- Beim Scan 538 Status-Einträge einschließlich Verzeichniszusammenfassungen. Wesentlicher aktueller Produktcode ist unversioniert, darunter src/pages/MemoryApp.tsx und working-memory/memory.py.
- Außenbestand: supabase/ sowie Projektwissen und Governance-Unterlagen im übergeordneten Projektordner. Noch nichts zugezogen.

## Prüfungen
- node --test tests/*.test.mjs: 16 Tests, 15 bestanden, 1 fehlgeschlagen. tests/planning-route.test.mjs:9 erwartet eine eigene Betriebsroute; planning.ts leitet #betrieb zu Einstellungen um.
- Node-Teilmenge ohne planning-route.test.mjs: 15/15 bestanden; Protokoll node-gruener-teil.txt.
- working-memory: python3 -m unittest discover -v; 521 Tests, Fehlerzahl 7, Exit 1. Fehler in test_canonical_archive_http und PipelineIntegrationTests aus test_compact_reconcile. Keine Produktcodekorrektur vorgenommen.
- npm run build in ursprünglicher Arbeitskopie wegen anhaltend langsamer Dependency-Dateizugriffe nach knapp fünf Minuten beendet; kein Erfolg behauptet.
- Isolierte Kopie: pnpm install --offline --frozen-lockfile --ignore-scripts und npm run build jeweils Exit 0. 103 kopierte Build-Eingaben per SHA-256 identisch; Manifest build-quellen.json, Ergebnis isolierter-build.json, Protokoll isolierter-build.txt.
- Keine reale Browser-/Produktionsabnahme durchgeführt.

## Inventare
- inventar/ausgangsstand.json; Helferbericht berichte/ausgangsstand/1.md.
- inventar/entscheidungen.json; Helferbericht berichte/entscheidungen/1.md: 13 Entscheidungen, vier Annahmen, fünf Fragen/Hypothesen, acht verworfene Ansätze, drei Regeln.

## Offene Auswahl nach B3
Die Session hat gefragt, ob der vollständige aktuelle Produktstand einschließlich des äußeren supabase/-Ordners oder nur der letzte Commit des Arbeitszweigs zur Umbau-Basis werden soll. Empfehlung: vollständiger aktueller Produktstand; lokale private Daten und Geheimnis-Pfade ausschließen; bekannte rote Tests als offene Punkte übernehmen. Eine Antwort liegt noch nicht vor.

## Unveränderte Grenzen
Keine Branch-/Tag-/Index-/Produktcodeänderung durch die Session, kein Merge/Push/Deployment und keine Kit-Installation. Geschrieben wurden nur Vorprüfungsunterlagen unter _umbau sowie isolierte temporäre Build-Dateien; Werkzeuge können lokale ignorierte Build-/Python-Caches erzeugt haben. Geheimnis-Inhalte wurden nicht gelesen.
