# HZ-MIGRATION-20261003-BACKUP – Übergabevertrag

Stand: 2026-10-03. Technischer Nachtrag für Lead-Integration in die bestehenden Autoritäten; kein zweites Betriebsrunbook.

## Aktivierung und Bestandsschutz

Produktiv unverändert bis Lead-GO. Lokale/live Ausgangsdatei `scheduled_backup.py`: SHA256 `0ce536a2fb4980ab27ad72b621b5d3819491aa61b0150db9d544e5c4ea90a95b`. Bei Deployment diesen Hash erneut prüfen, dann nur beiliegenden Minimalpatch anwenden. Baselineabweichung verhindert blinde Ersetzung. Bei Deployment den `scheduled_backup.py`-Eintrag des vorhandenen `build-manifest.json` konsistent aktualisieren; ansonsten verweigert die bestehende Laufzeitprüfung das Backup. `.local/selfhost-backup.json` mit `{"enabled":true}`, Modus0600, aktiviert den Adapter; Lead besitzt die Cutover-Aktivierung. Hosted-Supabase ohne Marker oder mit `enabled:false` behält den bisherigen Weg. Selfhost-Origin ohne aktivierten Adapter scheitert. Die Aktivierung erlaubt keinen produktiven Restore.

Der Adapter ergänzt `selfhost/` im unveränderten `dashboard-full-backup-v1`-Bundle. Manifest erfasst Länge/SHA256 jeder Datei; vorhandener `offserver_backup.py` prüft Zusatzdateien unverändert. Bestehende Canonical-Export-, n8n-, Laufzeit-, Outbox- und externe Löschbarrierenpfade bleiben erhalten. Bestehende Systemd-Schreibpfade reichen: temporäre Daten unter `/var/backups/dashboard-job`; Targetkonfiguration wird nur gelesen. Kein Zugriff auf zusätzliche kostenpflichtige Dienste.

## Sicherungs- und Restorevertrag

Target `/opt/dashboard-supabase-20261003`, PG `dashboard-supabase-20261003-db-1`, DB `postgres`, Superuser `supabase_admin`, PG17 gepinnt. Enthalten:

- Vollständiger Custom-Dump nach PostgreSQL-Dumpvertrag mit exportiertem REPEATABLE READ Snapshot.
- `pg_dumpall --roles-only` einschließlich privater Passwortverifier, Eigenschaften und Mitgliedschaften.
- `.private.env` (PG/JWT/Anon/ServiceRole/SMTP), Compose, Upstreammanifest/-konfiguration und Edge-Funktionen.
- Vollständige `/etc/postgresql-custom`-Kopie einschließlich `pgsodium_root.key`.
- Image-ID, gestarteter PG-Befehl, privater Quellfingerprint und Restorequittung.

Verzeichnisse0700/Dateien0600. Kein Rollen-SQL/Passwort/Secret im öffentlichen Status oder Fehlerlog. Die tatsächliche PostgreSQL-Service-UID/GID wird per `id` am laufenden gepinnten Image ermittelt und im privaten Imagevertrag gespeichert. `docker cp -a` allein erhielt diese Owner beim tatsächlichen Test nicht; die ausschließlich entbehrliche Konfigkopie wird deshalb diesem Account zugewiesen. Eigener Restorecontainer verwendet das lokal vorhandene identische Image, `--network none`, eigenes Datadir und eigene Konfigkopie, 1GB/1CPU, `cron.launch_active_jobs=off`. Es startet ausschließlich PG; kein Auth/Gateway/Edge/n8n. Existierende Bootstrap-CREATE-ROLE-Anweisungen werden entfernt; ALTER und GRANT bleiben erhalten. Frische DB aus `template0`, Restore mit Eigentümern/Rechten und `--exit-on-error`.

Erfolg verlangt identische Tabellenzahlen aller durch pg_dump abgedeckten Relationen, Auth-User-Inhaltshash, Vault-Entschlüsselungshash und Rollenattribute/Passwortverifierhash. Extensioninterne, nicht über `extconfig` gesicherte Tabellen sind bewusst nicht Teil dieses PostgreSQL-Dumpvertrags (hier `net.http_request_queue`, `net._http_response`, transiente HTTP-Zustände). Fehlende Konfiguration/Vaultkey, Docker/PG-Fehler, Platzmangel oder Fingerprintabweichung verhindern Erfolg. Konkrete Dump-/Rollen-/Config-SHA256 und Tabellenzahlen liegen in privater `selfhost/restore-check.json`, deren Hash im Bundlemanifest steht. Die tägliche Sicherung ersetzt keine Freigabe eines produktiven Restores und hebt die externe Löschbarriere des bestehenden Runbooks nicht auf.

Bei realem Wiederanlauf nur freigegebenes leeres Ziel verwenden; aktuelle externe Löschbarriere prüfen und bereits gelöschte Originale gemäß bestehendem Runbook vor Dienste-/Triggerfreigabe behandeln. Nicht einfach Dienste aus dem Voll-Dump einschalten. Lead/Backend müssen diesen Integrationsschritt abnehmen.

## Prüfpaket und Stop

Offene Frage: Erfasst und restauriert der Adapter den tatsächlichen PG17/Auth/Vault-/Rollen-/Config-Vertrag vollständig, ohne Hosted- oder Transferregression? Pflicht: aktivierter Selfhost scheitert bei Lücken; konkrete isolierte Restorequittung vor Success. Umfang: 3 gezielte Risikochecks, 12 vorhandene Backup-/Offserverchecks, Syntax, vorhandener Livebaseline-/Datenträgercheck, abgestimmter einmaliger echter Stage-Dump/isolierter Restore. Bestehen: an Lead zur Integration/Deploymentfreigabe; Scheitern: konkrete Ursache innerhalb maximal2 Zyklen reparieren oder belegte Lücke zurückgeben. Keine parallelen schweren Backendrestores. Paketbudget max2 vollständige Implementierungs-/Validierungszyklen; Marker STALL/LOW_YIELD an Lead, GOAL_GATE vor Cutover.

Lokale Checks bestanden: `python3 ops/hetzner-migration/backup-test.py` (3), `python3 -m unittest test_backup_operations test_offserver_backup` (12), Syntaxkompilierung. Live-Datenträgercheck: 41.453.740.032 Bytes frei. Echte Restoreprüfung und produktive Veröffentlichung werden separat in `backup-evidence.json` ausgewiesen; fehlende Nachweise gelten nicht als bestanden.

Primärvertrag: [PostgreSQL17 pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html) / [pg_dumpall](https://www.postgresql.org/docs/17/app-pg-dumpall.html). Supabase-Changelog am2026-10-03 gelesen; Adapter verwendet die vorhandenen gepinnten Images und keine neuen Auth-/Gateway-APIs.

Echter Adapterrestore: Zyklus1 scheiterte am nachgewiesenen Konfigurations-Owner; Zyklus2 nach gezielter Reparatur bestanden. Zusätzlich1 Testharness-Vorabbruch (exklusive vorhandene Markerdatei), ohne PG-Restorestart. Identisch restauriert:89 dumpabgedeckte Tabellen/68.572 Zeilen; Auth1 Benutzer/22 Sitzungen, Vault1 Secret, Rollenattribute und Passwortverifier;30 private Configdateien mit SHA256. Keine dritte Lösungsrunde. Private Quittung `/var/backups/dashboard-job/.adapter-check-HZ20261003-1/selfhost/restore-check.json`, SHA256 `3febc28a2332bcc8cfb9dbea682cd5a36edea824b013a185c1394f033a7306a7`. Source-Stage wurde durch dieses Paket nur gelesen. Produktionsbackupscript/Marker unverändert. Der echte Selfhost-Testteil wurde als35-Dateien-v1-Bundle übertragen; das ist keine durchgelaufene tägliche produktive Komplettsicherung.
