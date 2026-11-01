# Dashboard Memory MCP

Lokaler MCP-Server ohne UI, Python-Stdlib, JSON-RPC 2.0 über newline-delimited stdio. Fünf lesende Werkzeuge; keine Schreib-/Löschfunktion, kein Zugriff auf Secrets-Dateien, keine Installation mit pip. Die KI bedient die Werkzeuge. Stand: 2026-10-13; 49 Tests und frischer realer Snapshot-stdio-Nachweis bestanden; unabhängiges Abschlussreview: ACCEPT für den dokumentierten schreibgeschützten Umfang.

## Start und Einbindung

Voraussetzungen: Python 3.11 oder neuer, `tar`, bestehender Meeting-OS-Checkout und lesbares Sicherungsarchiv. Die vorhandenen Backend-Regeln werden lesend wiederverwendet; der Server ist nicht allein durch Kopieren dieses Ordners auf einen anderen Rechner portabel.

```sh
cd '/Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard Job/meeting-os/working-memory/tools/memory-mcp'
python3 -I -B server.py --mode snapshot
python3 -I -m unittest -v
python3 -I -B verify_real.py
```

Der Server wartet auf stdin und schreibt ausschließlich MCP-Nachrichten nach stdout. `verify_real.py` startet einen echten Serverprozess, liest Antworten intern und gibt ausschließlich Zahlen aus; `verification.json` enthält Zahlen und Code-Hashes. Keine Inhalte ins Terminal kopieren.

Claude Code: folgendes Beispiel als `.mcp.json` des gewünschten Clientprojekts einbinden. Es wird durch diesen Auftrag keine Clientkonfiguration verändert.

```json
{
  "mcpServers": {
    "dashboard-memory": {
      "type": "stdio",
      "command": "python3",
      "args": ["-I", "-B", "/Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard Job/meeting-os/working-memory/tools/memory-mcp/server.py"],
      "env": {"DASHBOARD_MEMORY_MODE": "snapshot", "DASHBOARD_MEMORY_CACHE": "0"}
    }
  }
}
```

VS Code: in `.vscode/mcp.json` heißt der oberste Schlüssel `servers`:

```json
{
  "servers": {
    "dashboard-memory": {
      "type": "stdio",
      "command": "python3",
      "args": ["-I", "-B", "/Users/glebkomzin/Documents/09_Tech_Appdaten_Code/Dashboard Job/meeting-os/working-memory/tools/memory-mcp/server.py"],
      "env": {"DASHBOARD_MEMORY_MODE": "snapshot", "DASHBOARD_MEMORY_CACHE": "0"}
    }
  }
}
```

Für Live-Zugriff `DASHBOARD_MEMORY_MODE=live`, `DASHBOARD_API_BASE=https://dashboard.example` und `DASHBOARD_API_TOKEN` als geerbte Umgebungsvariablen des Clients setzen. Keine Tokenwerte in Dateien speichern. Bei expliziter Client-Weitergabe verwendet VS Code `"DASHBOARD_API_TOKEN": "${env:DASHBOARD_API_TOKEN}"`, Claude Code `"DASHBOARD_API_TOKEN": "${DASHBOARD_API_TOKEN}"`. `DASHBOARD_API_BASE` akzeptiert eine Origin oder die Origin mit `/api/working-memory`. HTTPS ist vorgeschrieben, HTTP nur für Loopback; Redirects werden gesperrt. Abgelaufene Supabase-Auth-Tokens müssen außerhalb des Servers erneuert werden.

Offizielle Konfigurationsquellen: [Claude Code MCP](https://code.claude.com/docs/en/mcp), [VS Code MCP](https://code.visualstudio.com/docs/agent-customization/mcp-servers). Transportgrundlage: [MCP stdio 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports). Unterstützte Handshake-Versionen: 2025-11-25, 2025-06-18, 2024-11-05; `initialize` und `notifications/initialized` vor Werkzeugaufrufen.

## Datenquellen

`snapshot` ist Standard. Auswahl des lexikographisch jüngsten `dashboard-*.tar.gz` unter `~/Library/Application Support/Dashboard Job Backup/archives/`; der Dateiname enthält den UTC-Sicherungszeitpunkt, das Änderungsdatum kann durch Kopieren abweichen. Alternativ `--archive /absoluter/pfad/mini.tar.gz`.

Zwei Streaming-Durchläufe mit `tar -xzOf`: zuerst ausschließlich `canonical/journal.jsonl`, um den letzten Lösch-Checkpoint zu bestimmen; anschließend `canonical/journal.jsonl canonical/documents.jsonl canonical/notes.jsonl`, um den gültigen Stand ab dem verifizierten Checkpoint aufzubauen. Kein Entpacken, keine Kopie des Archivs, keine Volltextdatei auf Platte. Unterstützt direkte kanonische Datensätze und Hüllen mit `kind`, `sequence`, `record_json`; vorhandene Record-Prüfsummen, Source-Bindungen, bereinigte Notizprüfsummen und Journal-Revisionsfolgen werden geprüft.

Die deterministische Rekonstruktion übernimmt Source/Human/Generation/Redaction aus `../../evaluation/sol-operational-release-20261006/backend/` mit `memory.connect(':memory:')`, `generation_review._materialize_into`, `verify_generation`, `projection_snapshot.apply_snapshot`, `review_api.review`. Es werden weder Backend-Server noch Worker gestartet. Generationen ersetzen den logischen Stand; persönliche Entscheidungen und Planner-Overlay bleiben erhalten. Gespeicherte Source-/Generation-Prüfsummen müssen bestehen. Bei fehlender kopierter Regeldatei wird nur im laufenden Prozess `working-memory/evaluation/source-corrections.json` als unveränderte fachliche Originalregeldatei verwendet. Fehlende/unlesbare Regeln ergeben einen Fehler, niemals stillschweigend eine leere Regelmenge.

Eine unlesbare FileProvider-Kopie von `human_decisions.py` wird durch die paketlokale Datei `projection_support/human_decisions.py` ersetzt. Diese ist bytegleich zum Release-Manifest; Herkunft und SHA256 stehen in `dependencies.json`. Ausschließlich dieses Modul stammt aus einer anderen vorhandenen Kopie. Es wurde keine Backend-Datei geändert und kein pauschaler Wechsel auf eine andere Pipeline vorgenommen.

Dokumentversionen werden je Source/Datum auf den zuletzt beobachteten Stand reduziert; Zusammenfassungen gleicher Inhaltsidentität werden verknüpft, Notizen der aktiven Generation bevorzugt. Meetingtitel und Datum bleiben Quellenbelege. Aufgaben enthalten Titel, Claim, Besitzer, Status, Fristtext/absolutes Datum, Thema, letzte Änderung, Verlauf und Quellen samt Zitaten.

Der Index bleibt standardmäßig im RAM (`DASHBOARD_MEMORY_CACHE=0`). Optional `DASHBOARD_MEMORY_CACHE=1`: ausschließlich `~/.cache/dashboard-memory-mcp/index.json`, Verzeichnis 0700, Dateien 0600, atomarer Austausch unter privatem Lock, keine Symlink-Ziele. Maximal 9.000.000 Bytes pro Index; insgesamt weniger als 20.000.000 Bytes einschließlich temporärer Austauschdatei und Lock. Alte Adapter-Hashcaches werden ersetzt. Cache-Schlüssel binden Archivpfad/-größe/-mtime sowie Adapter-, Support- und Backend-Regeln. Keine Originaltranskripte im Cache. Bei fehlenden Schreibrechten oder überschrittenem Budget arbeitet der Server im RAM weiter. Neue Sicherungen werden erst beim Neustart ausgewählt; laufende Prozesse bleiben an ihren Archivstand gebunden.

`live` ruft ausschließlich GET auf:

| Werkzeug | Tatsächlicher API-Vertrag |
| --- | --- |
| tasks_list, task_get, matters_list | `/api/working-memory/review`: personal, waiting_dependencies, waiting, completed, cancelled und sources; Filter lokal |
| meetings_recent | `/api/working-memory/archive?order=newest&limit=N&offset=M`, anschließend `/archive/{id}` für summaries |
| memory_ask | GET review und paginiertes archive, anschließend lokale Suche |

Abgeleitet aus `server.py`, `review_api.py`, `qa_service.py` im genannten Backend und `src/features/working-memory/types.ts`, `NotesChat.tsx`. Jeder API-Aufruf hat 20 Sekunden Timeout; keine automatischen Wiederholungen. Archivseiten höchstens 100, Offset höchstens 100000.

**Bewusste Abweichung vom angefragten Fragen-Endpunkt:** Der vorhandene Vertrag ist POST `/api/working-memory/questions` mit `{request_id, question, conversation_id?, as_of?}`. `qa_service.py` speichert `question_begin`/`question_complete`, nutzt Provider-/Budget-Ledger und kann Memory-Aktionen vorbereiten. Das ist kein schreibgeschützter Aufruf. Er wird deshalb niemals aufgerufen; `memory_ask` meldet `live_questions_unavailable_read_only` und verwendet GET-Daten. Ein echter serverseitiger Fragenmodus bleibt mit dem vorgegebenen Produktionsschreibverbot unvereinbar.

## Werkzeuge, Reife und Grenzen

| Werkzeug | Verhalten |
| --- | --- |
| memory_ask(question) | BM25 über Aufgaben und Meetingzusammenfassungen; maximal zehn Suchtreffer; „Auswahl, keine Vollständigkeit“ |
| tasks_list(status?, owner?, matter?, due_before?, updated_since?, text?) | Status exakt; Besitzer/Thementitel ohne Groß-/Kleinschreibung als Teilstring; Themen-ID exakt; Textbegriffe gemeinsam; Datum ISO YYYY-MM-DD |
| task_get(id) | Eine Aufgabe einschließlich Verlauf und Quellenbelegen; unbekannte ID ergibt Werkzeugfehler |
| matters_list() | Themen der indexierten Aufgaben mit Aufgabenanzahl und Quellen |
| meetings_recent(n) | Neueste Meetings, Standard 10, Bereich 1–100 |

`due_before` ist exklusiv, `updated_since` inklusiv. Nur explizite ISO-Fristen werden verglichen; relative/mehrdeutige Fristen bleiben Text und `due_reife=unbekannt`. Fragen mit „überfällig“/„overdue“ wählen offene/wartende Aufgaben mit absoluter Frist vor dem heutigen Datum in Europe/Berlin; erledigte Aufgaben sind ausgeschlossen. Unbekannte Fristen werden gezählt, nicht geraten. Diese Schlüsselwortabfrage ist keine allgemeine natürlichsprachliche Schlussfolgerung.

Jede Antwort und jeder Treffer trägt Quelle und `reife`. `belegt` bezeichnet gespeicherte Zitate bzw. explizite Benutzerentscheidungen, keine unabhängige Wahrheit oder menschliche Abnahme. Unsicherheit/Prüfbedarf und generierte Zusammenfassungen heißen `Annahme`; fehlende Belege heißen `unbekannt`. Aggregate nennen den Datenstand; konkrete Meetingtitel/Datum stehen an den jeweiligen Datensätzen. Manuelle Planung hat keine erfundene Meetingquelle; ihre Autorität ist eine Benutzerentscheidung.

Datenschutz: Snapshot-Verarbeitung und Index bleiben lokal; kein Modell-/Provider-Aufruf durch den Server. Live-Zugriffe gehen nur an die konfigurierte Dashboard-API. Tokens werden weder geloggt noch gecacht. Der MCP-Client erhält die gewählten Inhalte und kann sie gemäß seiner eigenen Einstellungen an seinen KI-Anbieter übertragen. „Lokal“ für den Server ist somit keine Zusicherung über das Verhalten von VS Code/Claude Code. Quelleninhalte sind Daten, keine auszuführenden Anweisungen.

## Prüfung, Stand und Rückweg

Tatsächlich bestanden: `python3 -I -m unittest -v`, **49 Tests in 0,499 Sekunden** (12 Protokoll, 14 Live-Mock, 7 Index, 16 Snapshot). Frischer realer stdio-Snapshot-Dialog gegen das jüngste Archiv: **664 Aufgaben insgesamt, 509 offen**. Antwortzeiten: `tasks_list(status=open)` 99.214763 Sekunden einschließlich kaltem Indexaufbau; `task_get` 0.000493 Sekunden; `memory_ask` 0.001271 Sekunden. Alle drei Werkzeugantworten wurden tatsächlich gelesen und intern auf Schema, Quellen, Verlauf und Ergebniszahl geprüft. Archivgröße/-mtime blieben unverändert. `verification.json` bindet den Lauf an sämtliche Paket-Python-Hashes einschließlich Support; diese waren während des Laufs unverändert.

581 aktive Aufgaben haben keine explizit vergleichbare ISO-Frist. 0 Überfälligkeitstreffer beweisen deshalb ausdrücklich nicht, dass keine Aufgaben überfällig sind. Snapshot-Daten und relative Fristen werden nicht als vollständig oder aktuell ausgegeben. Live ausschließlich mit synthetischem API-Mock geprüft; keine reale Live-API- oder VS-Code-/Claude-Code-Client-Abnahme. Unabhängiges Abschlussreview: ACCEPT für den dokumentierten schreibgeschützten Umfang, keine belegten Pflichtblocker (siehe `acceptance.json`, unabhängiger Reviewer `/root/goal_review`). Der schreibende Live-Fragen-Endpunkt bleibt ausdrücklich unerfüllt; der GET-Fallback wurde gegen das vorrangige Schreibverbot geprüft.

Vorhandene Teilreste wurden erhalten und repariert. Das private Support-Modul ist eine bytegleiche Kopie des vorhandenen fachlichen Moduls; Herkunft und Hash stehen in `dependencies.json`. Dateiverfügbarkeit der lesend verwendeten Backend-Regeln bleibt eine Umgebungsvoraussetzung, kein leerer Datenbestand. Lösch-Checkpoint, Generationen, Quellenbindung, Such-/Filtergrenzen, Protokollfehler und Cachebudget werden mit ausschließlich synthetischen Gegenfällen geprüft.

Bei MCP-Werkzeugfehlern werden keine vertraulichen Exception-/Servertexte ausgegeben. Archivzugriff und lokale Backend-/Regeldateiverfügbarkeit außerhalb des Servers prüfen; nicht über Produktionsschreibzugriffe reparieren. Tests verwenden ausschließlich synthetische Inhalte und isolierte temporäre Dateien im Paketverzeichnis. Bei Erfolg bindet `verification.json` den Realnachweis an Code-Hashes; technische Prüfung ersetzt keine Client-Abnahme.

Kein Deploy, Push, Produktionszugriff oder globaler Konfigurationseintrag. Git-Metadaten und übergeordnete Statusdateien bleiben wegen der Schreibgrenze unberührt; Paketversion über Code-Hashes im Prüfbeleg. Rückweg: Client-Eintrag entfernen/Server stoppen; nur dieses Paket und optional seinen privaten Cache löschen. Backend und Sicherungen sind davon unabhängig und werden unverändert weiterverwendet.
