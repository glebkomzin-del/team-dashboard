# Dauerhafter Restorevertrag für den finalen Archivpaar

Der volle Backup enthält den bereicherten `selfhost/source-fingerprint.json`.
Den unveränderten Standardrestore allein darauf anzuwenden wäre unvollständig.
Dieser Zusatz enthält deshalb den exakten einmaligen Wrapper, dessen exakte
`enriched-fingerprint.sql` und `restore_enriched.py`. Letzteres importiert nur
`runtime/scheduled_backup.py` aus dem gewählten Vollbackup, SHA954e5f163387952b6b7074e5ec3d6938cd9fbedc0473044f3fecd5d8c56d29ec.
Es verwendet dieselbe Erweiterung wie beim Backup und verlangt dieselbe SQLSHA.
Source/Human/Calls/Isolations/Deletions plus vollständige Originaldokumente und
alte Notizen werden damit in16Tabellen exakt aus demselben Dumpsnapshot verglichen.
Funktion47/49-Definitionen und ACLs sowie Auth/Vault/Rollen bleiben gebunden.

Nach finalem Backup bindet der Lead beide vollständigen Archividentitäten in
einer privaten externen Quittung, die auf Server und Mac neben BEIDEN Archiven
aufbewahrt wird. Die äußere Quittung vermeidet eine zirkuläre ArchiveSHA-Bindung:

```json
{
  "format": "dashboard-final-backup-pair-v1",
  "full_backup": {"archive": "dashboard-YYYYMMDDTHHMMSSZ.tar.gz", "bytes": 0, "sha256": "ACTUAL_FINAL_SHA"},
  "supplement": {"archive": "dashboard-recovery-supplement-v2-20261006.tar.gz", "bytes": 0, "sha256": "ACTUAL_SUPPLEMENT_SHA"}
}
```

Platzhalter sind kein gültiger Positivnachweis. Aktuelle echte Bytes/SHAs werden
erst nach dem ausgeführten finalen Lauf geschrieben. Beide Archive vollständig
prüfen und sicher in separate private Stagingordner entpacken; bestehendes
`offserver_backup.verify_bundle` für den Vollbackup nutzen. Keine Produktion
als Restoretestziel, keine Source-Supabase-Rücksetzung. Der Nginx-Symlink im
Zusatz ist absolut; beim Staging niemals verfolgen oder überLive-/etc entpacken.

Aus `supplement-v2/recovery/` zunächst den Vertrag prüfen, danach denselben
Aufruf mit `--execute-isolated-restore` für den entbehrlichen Restore ausführen:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 /PRIVATE/STAGING/SUPPLEMENT/recovery/restore_enriched.py \
  --full-backup-archive /PRIVATE/ARCHIVES/dashboard-YYYYMMDDTHHMMSSZ.tar.gz \
  --supplement-archive /PRIVATE/ARCHIVES/dashboard-recovery-supplement-v2-20261006.tar.gz \
  --paired-receipt /PRIVATE/ARCHIVES/final-backup-pair.json \
  --unpacked-full-backup /PRIVATE/STAGING/FULL
```

Die Prüfung bindet beide Archivbytes an die externeQuittung und die tatsächlichen
entpackten Runtime-/Selfhostdateien an das volle Archivmanifest. Ein fehlender/
veränderter Wrapper oder eine fehlende/veränderte SQL wird vor Runtimeimport
gesperrt. Der vorhandene Restore startet ausschließlich PostgreSQL im
`--network none`,2GiB, mit `--pull=never`, derselben gesicherten Imageidentität
und Cron deaktiviert; er entfernt nur eigene Testressourcen. Kein Gateway-,
Produktionsdatenbank-, Worker- oder Providerzugriff. Voraussetzungen sind Docker,
das gesicherte lokale PostgreSQLimage und Pythonabhängigkeiten der gesicherten
Runtime. Ein Registrypull ist kein Bestandteil dieses Ablaufs.

N8n weiterhin über den bestehenden isolierten `restore_n8n`-Ablauf aus dem
geprüften Vollbackup rekonstruieren: internesNetz, ausschließlich kopierte
Workflows/PublishedVersionen deaktivieren, Credentials/Google-Token entschlüsseln.
UI/Nginx-Wiederherstellung und Freigabegrenzen aus der v1-Übergabe gelten weiter.
Der Zusatz enthält keine neuenenv-/Credentialdateien; privateSharedNginxkonfig
bleibt ausschließlich in privaten Recoveryarchiven. Ein neuer realer Backup-
oder Datenbankrestore wurde im Vorbereitungspaket nicht gestartet.
