<!-- project-governance-kit:start -->
Projektwissen beginnt in START.md. Nutze /vision für Vision, Features und Freigabe,
/build für Planung, Umsetzung und Abnahme. Eine Session wechselt nie die Rolle.
Aktuellen gemeinsamen Stand mit `.gov/gov roadmap` und `.gov/gov start-info` lesen.
Status, Journal, Entscheidungen und Task-Zähler ausschließlich über `.gov/gov` ändern.
<!-- project-governance-kit:end -->


## Technische Hinweise

Frontend: `src/`; produktiver Einstieg `src/Entry.tsx`, Backend: `working-memory/`, Edge Functions und SQL: `supabase/`. Quelle: src/Entry.tsx:3; working-memory/Dockerfile:3; archiv/governance-alt/PROJECT_STRUCTURE.md:7
Frontend lokal starten: `npm run dev`; bauen: `npm run build`; Linting: `npm run lint`. Quelle: package.json:7; package.json:8; package.json:9
Backend-Tests aus `working-memory/`: `python3 -m unittest discover -v`; Containerstart: `python server.py`. Quelle: archiv/governance-alt/working-memory/README.md:27; working-memory/Dockerfile:16
Der verbindliche Prüfbefehl und die Testverzeichnisse stehen in `.gov/config.json`. Annahme: Die Session übernimmt dort den gegen den Ausgangsstand gemessenen grünen Teil.
Lokale Regressionsergebnisse enthalten private Originale und Zugänge und werden absichtlich nicht versioniert. Quelle: archiv/governance-alt/working-memory/README.md:38
Die Vorschau-Compose-Konfiguration baut aus dem Arbeitsgedächtnisverzeichnis; Backenddateien gehören zu diesem Buildkontext. Quelle: working-memory/compose.yaml:3; working-memory/Dockerfile:3
