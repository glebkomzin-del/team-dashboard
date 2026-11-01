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

Die getestete Source-Stage-Datenbank hat Owner`postgres`, Standard-Datenbank-ACL und0 datenbankspezifische Rollen-/DB-Settingzeilen (direkte Metadatenabfrage). Der geprüfte frische-DB-Restore deckt diesen aktuellen Vertrag ab. Bei künftig abweichenden DB-ACL/ALTER-DATABASE-Einstellungen ist deren Wiederherstellung über die im Dump archivierten DATABASE-Einträge gesondert zu prüfen; dieser Test behauptet dafür keine Abnahme.

## Produktionsinstallation und Lead-Cutover-Kommandos

Folgepaket autorisiert die hashgesicherte Produktionsinstallation und einen vollständigen bestehenden Hosted-Tages-/Offserverlauf. Vor Installation: Systemd MainPID0, exklusiver bestehender Backup-Lock, identischer Ausgangshash. Installiert: ScriptSHA256 `58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9`; ausschließlich dessen Buildmanifest-Eintrag geändert. Kein Dienstrestart, kein Env-/Markerwechsel. Private ursprüngliche Script-/Manifestkopie unter `/opt/dashboard-memory-canonical-draft/.local/backup-adapter-rollback-HZ20261003/`.

Produktions-Prüfpaket: Offene Frage ist, ob der vollständige etablierte Tageslauf nach der Datenträgererweiterung wieder funktioniert und seine unveränderte Mac-Zweitkopie samt Löschbarriere belegt ist. Pflicht: Systemd und `backup-status.json` melden erst nach komplettem Export, isoliertem n8n-Restore und Paketprüfung Erfolg; vorhandenes Offserverwerkzeug bestätigt denselben Archivhash und sämtliche Manifestdateien. Umfang: ein regulärer Hosted-Systemdlauf, danach das installierte unveränderte Mac-Pullwerkzeug; Containeridentitäten/Startzeiten vor/nach vergleichen. Bestehen: installations-/Cutoverbereit an Lead übergeben. Scheitern: konkrete Diagnose, maximal2 Produktionszyklen, keine automatische zusätzliche Runde. Die2 bereits verbrauchten PG17-Restorezyklen bleiben separat erhalten. Aktivierung und Selfhost-Produktionslauf sind bis ausdrücklichem Leadkommando offen.

Ausgeführte Installation (nicht wiederholen):

```sh
ssh root@178.105.167.26 'python3 /var/backups/dashboard-job/.adapter-code-HZ20261003/backup-install.py --patch /var/backups/dashboard-job/.adapter-code-HZ20261003/backup-scheduled.patch'
ssh root@178.105.167.26 'systemctl start --no-block dashboard-job-backup.service'
```

Hosted-Rollbackkommando, vorbereitet und hashgesichert, **nicht ausgeführt**:

```sh
ssh root@178.105.167.26 'python3 /var/backups/dashboard-job/.adapter-code-HZ20261003/backup-install.py --rollback'
```

Rollback verlangt unveränderten Kandidathash/-Manifesteintrag, inaktiven Backupdienst, Hosted-Origin und inaktiven Selfhostmarker. Es stellt nur das Script und seinen Manifesthash zurück und erhält fremde Manifeständerungen. Nach Selfhost-Cutover kein isolierter Scriptrollback; zuerst muss der Lead den gemeinsamen Writer-/Env-Rückweg verantworten.

Lead-Aktivierung, **vorbereitet, nicht ausgeführt**. Der Hostservice muss bereits den mit Backend bestätigten öffentlichen Origin `https://178-105-167-26.nip.io/supabase` ohne TrailingSlash verwenden. `http://api-gw:8000` ist ausschließlich containerintern und am Host kein Backuporigin. Das folgende Kommando verändert nur den privaten Marker und verlangt den bestehenden Backup-Lock; es ist keine Cutoverfreigabe:

```sh
ssh root@178.105.167.26 'python3 -' <<'PY'
import fcntl, hashlib, json, os, tempfile
from pathlib import Path
root=Path('/opt/dashboard-memory-canonical-draft')
with open('/run/lock/dashboard-job-backup.lock','a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cfg=dict(line.split('=',1) for line in (root/'.local/service.env').read_text().splitlines() if line and not line.startswith('#'))
    if cfg.get('SUPABASE_URL')!='https://178-105-167-26.nip.io/supabase':raise SystemExit('Host origin not switched; marker remains unchanged')
    expected='58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9'
    if hashlib.sha256((root/'scheduled_backup.py').read_bytes()).hexdigest()!=expected or json.loads((root/'build-manifest.json').read_text()).get('scheduled_backup.py')!=expected:raise SystemExit('Installed adapter hash mismatch')
    fd,name=tempfile.mkstemp(prefix='.selfhost-backup-',dir=root/'.local')
    try:
        with os.fdopen(fd,'w') as stream:json.dump({'enabled':True},stream);stream.flush();os.fsync(stream.fileno())
        os.chmod(name,0o600);os.replace(name,root/'.local/selfhost-backup.json')
    finally:
        if Path(name).exists():Path(name).unlink()
    print(json.dumps({'selfhost_backup_enabled':True}))
PY
```

Nach freigegebener Aktivierung den normalen Systemdlauf und unveränderten Mac-Pull erneut ausführen. Dieses Dokument enthält dafür bislang keinen produktiven Selfhost-Abnahmenachweis; die ausgeführten Produktionsbelege stehen in `backup-production-evidence.json`.

Produktionsfolgepaket abgeschlossen: Hosted-Systemdlauf1 von18:26:47 bis18:55:18UTC am2026-10-03, Resultsuccess/Exit0. Archiv `dashboard-20261003T182647Z.tar.gz`,1.274.298.440Bytes,SHA256 `bf150d126a93f12556f86d432f8fc23de52f0eae1b88d83b603093cde529dec8`. CanonicalRev221/Archiv857,384 Originale473 Notizen,0 Modellaufrufe. Isolierter n8n-Restore15 Workflows6 Credentials, aktive/publizierte Workflows0, Entschlüsselung und GoogleRefreshToken belegt; kein externes Netz. Der unveränderte installierte Mac-Pull bestätigte155/155 Dateien und identischen Archivhash um18:57:33UTC; aktuelle externe Löschbarriere übernommen. Produktive n8n-/Dashboard-Container-ID, Startzeit und Image vor/nach identisch. Selfhostmarker weiterhin nicht vorhanden. Produktionszyklus1/2 erfolgreich; frühere PG17-Restorezyklen2 bleiben erhalten. Buildmanifestownership an Lead/Backend zurückgegeben; künftige fremde Runtimehashänderungen müssen den Adaptereintrag580484... erhalten. Vorbereitete Aktivierungs- und Rückkehrkommandos wurden nicht ausgeführt.
