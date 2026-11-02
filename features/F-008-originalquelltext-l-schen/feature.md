# F-008 Originalquelltext löschen
Ein angemeldeter Eigentümer kann bei aktivierter Funktion die Löschung eines Originalquelltexts beantragen und den Status abfragen. Quelle: working-memory/server.py:219

Bezug: V

## Kernsatz
Ein angemeldeter Eigentümer kann bei aktivierter Funktion die Löschung eines Originalquelltexts beantragen und den Status abfragen. Quelle: working-memory/server.py:219

## Recherche
Quelle: working-memory/server.py:219
<!-- Quellen als URL oder als „Quelle: …“ eintragen. -->

## Abnahme
- A-008-1: Der Löschvorgang startet erst nach Bestätigung und kann nach Unterbrechung fortgesetzt werden. Quelle: src/pages/ArchivePage.tsx:63
- A-008-2: Der Auftrag wird für die Eigentümerrolle angenommen und kann bei längerer Ausführung einen Zwischenstatus liefern. Quelle: working-memory/server.py:319
- A-008-3: Die Löschung erstellt einen vorbereiteten, quellbezogenen Bereinigungsplan und verarbeitet Kandidaten seitenweise. Quelle: working-memory/original_deletion_service.py:36
- A-008-4: Die Ausführung prüft den Projektionsstand vor dem Löschaufruf. Quelle: working-memory/original_deletion_service.py:66
<!-- Kriterien mit gov id next A vergeben; Format: - Kennung: sichtbares Ergebnis. -->

## Vereinbarungen

## Annahmen

## Arbeitsstand
<!-- Offene Punkte und nächster Schritt; beim Ereignis pflegen. Ohne Offenes leer lassen. -->
