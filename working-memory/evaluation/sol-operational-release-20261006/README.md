# SOL-OPS-VERSION-01: vorbereiteter Source-/Release-Rückkehrpunkt

Prepare-only; kein Commit, Refupdate, realer Indexwrite, Push oder Deployment ausgeführt.
Basis-HEAD: 0e68b6d83d4d83b3fb27a1db92ffef6eef50e498.
Backend: 139 Manifesteinträge, davon 138 bytegleich kopiert; 48 ausgewählte SQL-Dateien.
Die Konfiguration evaluation/source-corrections.json enthält Originalpassagen und bleibt außerhalb Git; Hash und externer Wiederbeschaffungspfad stehen im source-manifest.json.
SQL-Autorität bleibt ../supabase/migrations/20261006103000_isolate_processing_job_failures.sql; die Kopie ist keine neue Autorität.
UI: exakte Source ui-stale-disabled-01 ohne node_modules/dist; Build-/Test-/Patchbelege übernommen, keine erneute Ausführung behauptet.

Releasebindung: Basisimage sha256:0bc7b0e106e0625218289bf3a21de1bfb2ca587cc7e970babd522dcd27f59e92 -> deployed sha256:349617c5502c674ed951878118b70656bf3cf5789715e3ba59fcca0e0cebb0d7. Root-Dockerfile ist FROM exaktem Basisimage plus zwei Delta-Dateien; es allein ermöglicht keinen vollständigen Wiederaufbau. Für Wiederherstellung sind verfügbare Images oder vollständige 138 Quellen plus externe geschützte Konfiguration, Abhängigkeiten und kompatible Laufzeit nötig. Git ist weder Datenbackup noch Nachweis einer Wiederherstellung.
Pipeline: v11:compact1:gate1:gpt-6.1-sol:03ab172405e37721:canonical1:42317499c5d8a62a. UI dpl_BHGjJRASsQb4vdj1dt1oiwwyaKeT; UI ist veröffentlicht; public-assets und Owner-CUA-Receipt binden den geprüften Stand. Operativer Gesamtabschluss bleibt offen. Semantische Qualifizierung ist laut Nutzer keine Releasepflicht; keine Antwortqualifizierung beauftragt. Daten-/Kostenbelege bleiben unverändert in ihren bestehenden Autoritäten.

version-release.py in /private/tmp/dashboard-sol-version-prepare-20261006 ist nur vorbereitet. Ausführung benötigt ein neues ausdrückliches Rootmandat, die eingefrorenen eigenen Dateien und explizite Ausführungsautorisierung. Eigene Pfade umfassen diesen Namespace sowie die unverändert eingefrorenen Root-Dokumente working-memory/docs/NEXT-OPERATIONS.md und working-memory/docs/RESTORE-RUNBOOK.md. Keine fremden Arbeitsdateien oder staged Probe übernehmen. Root-Dokumente bleiben textlich Root-Ownership; der Helfer darf ihre hier eingefrorenen Bytes ausschließlich versionieren.
