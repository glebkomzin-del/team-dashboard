# Meeting-Zusammenfassungen – Reparatur am 09.09.2026

Produktiv behoben: Der Drive-Intake archiviert eine neue Dokumenthülle auch bei reinen Metadatenänderungen. Die Archivliste wählt die neueste Hülle, während vorhandene Zusammenfassungen an der vorherigen Dokument-ID gespeichert sind. Dadurch fehlten heute fünf bereits erzeugte Zusammenfassungen in der Oberfläche.

`canonical_archive.summaries` löst erhaltene Notizen über dieselbe Quelle, dasselbe Meetingdatum und den identischen Transkriptkörper einschließlich SHA-256 auf. Notizen später beobachteter Dokumentversionen werden nicht rückwärts eingeblendet. Andere Quellen, geänderte Inhalte und geänderte Termine bleiben getrennt. Die ursprünglichen Notizen werden weder kopiert noch geändert.

21 Archiv-/HTTP-Tests bestanden. Produktionsimage `dashboard-memory-v11:summary-fix-20260909` baut auf dem vorher laufenden Image `dashboard-memory-v11:loading-20260909` auf und ersetzt ausschließlich `canonical_archive.py`. Serverquelle ebenfalls aktualisiert, Rückfallkopien in `/opt/dashboard-memory-canonical-draft/.local/summary-fix-20260909/`. Health bestätigt production/ok. Alle fünf heutigen Zuordnungen auf Archivrevision 539 geprüft. Im authentifizierten Produktionsbrowser die Konso-Zusammenfassung und das vollständige Original mit 23.303 Zeichen geöffnet.

Separat offen: Ein heutiger Job steht wegen `budget_exceeded` auf review, drei weitere stehen dahinter auf queued. Bestehende kumulative Grenze 8.878649 USD unverändert. Eine einmalige Erhöhung um 5 USD wurde dem Nutzer zur Entscheidung vorgelegt; noch keine Freigabe erhalten. Für die Reparatur keine Modellaufrufe und keine neuen Aufgaben erzeugt.

Chat-Befund: `MemoryApp.tsx` enthält keine Chatroute. Der frühere KI-Chat bleibt nur im abgelösten `App.tsx`/`KiPage.tsx`; `ask-memory` wurde bei der produktiven Stilllegung der neun alten KI-Endpunkte mit deaktiviert. In der neuen Server-Routenliste fehlt ein Chat-Ersatz. Damit liegt eine Funktionslücke der Migration vor. Eine gesonderte fachliche Begründung für den Verzicht wurde im geprüften Umstellungsplan nicht gefunden. In diesem Auftrag wurde die Warum-Frage untersucht; kein Todo angelegt.

## Aktualisierung 09.09.2026, 14:43 UTC

Der Nutzer hat die Aufhebung des Gesamtlimits ausdrücklich beauftragt. `wm_processing_config.budget_micro_usd` im aktiven Workspace auf NULL gesetzt (vorhandener Modus ohne Kostenobergrenze). Automatik und Quellenstichtag bleiben aktiv. Den wegen Budget gestoppten Monatsreporting-Job über die reguläre, protokollierte `wm_resolve_job`-Funktion erneut freigegeben; Entscheidungs-ID `dbe8537b-cf7b-4ea0-ad67-b2c159f6141d`. Gespeicherte Providerantworten und Kosten bleiben erhalten. Die frühere Anfrage nach zusätzlichen 5 USD ist damit überholt.
