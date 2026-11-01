# Dashboard Job – Projektstruktur

Stand: 2026-07-08

## Aktiver Arbeitsordner

Dieser Ordner ist der maßgebliche lokale Arbeitsort:

- Backend / Supabase Edge Functions: `supabase/`
- Frontend / Meeting OS: `meeting-os/`
- Dokumentation / Screenshots / Inventur: direkt in diesem Ordner

## Frontend

Aktiver Git-Checkout:

`/Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Claude_Code_Gleb/Dashboard Job/meeting-os`

Remote:

`https://github.com/glebkomzin-del/team-dashboard.git`

Aktiver Stand nach Bereinigung:

`d7cbc112c70e75a788af0e9662dd15780fcd078e`

## Bereinigter alter Downloads-Ordner

Der alte doppelte Projektbaum wurde aus dem aktiven Pfad entfernt und in den Papierkorb verschoben:

`/Users/glebkomzin/.Trash/team-dashboard-old-downloads-20260630-081524`

Grund:

- alter Checkout direkt unter `Downloads/team-dashboard` war dirty und veraltet
- aktueller Frontend-Checkout lag verschachtelt unter `Downloads/team-dashboard/meeting-os`
- dadurch bestand dauerhaft Verwechslungsgefahr

Wenn nach einigen Tagen nichts fehlt, kann der Papierkorb geleert werden.

## Archivierter alter Root-Build (2026-07-08)

Im Projekt-Root lag ein veralteter Vite-Build (`index.html`, `assets/`,
`icons.svg`, `favicon.svg` — Bundle-Hash `index-CEmZLahG.js`). Er stammte aus
einem früheren manuellen Export und hatte keinerlei Funktion mehr (Deploy läuft
über Vercel aus `meeting-os/`). Verschoben nach:

`_archiv_alter_root_build_20260708/`

Kann gelöscht werden, wenn nichts fehlt.

## Edge Functions — Status (2026-07-08, abends)

- **`ask-memory`** — aktiver KI-Assistent. Seit 2026-07-08 geschichtet:
  gecachter Basis-Block nur mit Executive Summaries (61k statt 186k Tokens,
  1h-Cache-TTL); Themen-Summaries gehen selektiv als `TOPIC_DETAILS` in den
  Frage-Block; strukturierte Items recency-gekappt (max. 500). Ping-Guard
  für den Cron-Warmhalter (`{"question":"ping"}`); interne Aufrufer dürfen
  sich mit dem Service-Key ausweisen (für run-eval).
- **`run-eval`** — testet seit 2026-07-08 `ask-memory` (vorher das gelöschte
  `semantic-search`). intent_accuracy ist dauerhaft n/a (kein Intent-System
  mehr); source_hit misst die von ask-memory belegten Meeting-IDs. Achtung:
  Die `expected_source_ids` der Eval-Fragen stammen vom Mai-Stand und
  gehören neu kalibriert.
- `semantic-search` und `semantic-search-v2` — am 2026-07-08 aus Supabase
  gelöscht; Code archiviert unter `_archiv_legacy_functions_20260708/`.
- Cron: jobid 8 `keep-ask-memory-warm` (*/4 Min) ersetzt jobid 6
  `keep-semantic-search-warm`; siehe Migration
  `20260708192500_move_warm_ping_to_ask_memory.sql`.

## Frontend-Struktur (seit 2026-07-08)

`meeting-os/src/App.tsx` (1.289 Zeilen) hält Daten-State, CRUD-Handler,
Dialoge, Routing und Chat-Zustand. Die Seiten liegen unter `src/pages/`
(CommandCenter, Inbox, Meetings, Actions, Projects inkl. Kanban/Gantt/Druck,
Ki, TextSearch, Activity); gemeinsame Typen/Helfer/Kleinst-Komponenten in
`src/lib/shared.tsx`. Seitenlokale Filter/Sortierungen leben in den Seiten
und setzen sich beim Seitenwechsel zurück.

## Konfiguration Frontend

`meeting-os/src/supabase.ts` liest `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`
aus einer `.env`; ohne `.env` greifen die eingebauten Fallbacks (Produktionswerte).
Die KI-Kosten pro Antwort liefert seit 2026-07-08 das Backend (`cost_usd` im
`done`-Event bzw. in der JSON-Antwort von `ask-memory`); die Preisliste im
Frontend ist nur noch Fallback für eine noch nicht deployte Backend-Version.
