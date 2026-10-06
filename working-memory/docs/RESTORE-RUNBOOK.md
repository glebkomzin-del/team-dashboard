# Dashboard Job wiederherstellen

## Aktueller Sol-Runtime-Rückweg – 06.10.2026, 08:55 UTC

Aktuell läuft Image `sha256:349617c5502c674ed951878118b70656bf3cf5789715e3ba59fcca0e0cebb0d7`, Tag `dashboard-memory:sol-counter-fix-20261006-9a9a0b1016`, mit48gebundenen Schemaquellen und Pipeline `v11:compact1:gate1:gpt-6.1-sol:03ab172405e37721:canonical1:42317499c5d8a62a`. Der ursprüngliche n8nMain bleibt mit Versiond7211499 unverändert aktiv. Aktuelle Daten-/Queue- und tatsächliche Abnahmen stehen allein in [NEXT-OPERATIONS.md](NEXT-OPERATIONS.md).

Der letzte Zweidateienwechsel baut auf dem exakten V3Image0bc7b0e1 auf; Source-/Patch-/Build-/Installbelege liegen privat unter `/private/tmp/dashboard-sol-operational-20261006/` und `/private/tmp/dashboard-sol-root-token-fix-20261006/`, serverseitiger gebundener Einbau unter `/root/dashboard-sol-token-fix-stage-20261006/`. Der dortige physische Vorherdump327949479Bytes ist ein privater Rückkehrpunkt, kein abschließend getesteter Gesamtrestore. Datenbank, Gateway und Environment wurden durch den Counterfix nicht geändert. Die neue Migration48 liegt autoritativ im Parentprojekt unter `supabase/migrations/20261006103000_isolate_processing_job_failures.sql`, SHA958d2ace29452beb4f7de9d10c748f331d462692aa9980e8b367b0ca34fec68c.

Nach bereits erfolgter Sol-Verarbeitung keine automatische Code-/Pipeline-Rücksetzung oder Retarget über bezahlte Jobs. Aktuelle Originale, Antworten, Kosten, Humanentscheidungen und Isolationsaudits erhalten. Bei einem echten gemeinsamen Fehler nur den betroffenen Writer halten; Queue-/Source-/Lease-/Revisionsbindung vor einem neuen Wiederanlauf prüfen. Historische Isolationsaudits werden im Backup auch dann bewahrt, wenn ihre aktuellen Ausnahmebedingungen nicht mehr gelten. Ein aktueller getesteter349/Schema48-Gesamtbackup samt Mac-Kopie steht noch aus. Der erfolgreich beendete tägliche Backupzyklus06.10.01:47UTC allein bestätigt diese erst später veröffentlichte Runtime nicht. Source-Supabase bleibt geschlossen.

## Historischer Performance-Runtime-Rückweg – 05.10.2026, 22:16 UTC

Aktuell läuft Image `sha256:5d5986089ce0824b53d530fd35ffe329eada90eb075c5b217f21e3966456bb52`, Tag `dashboard-memory:work-projection-20261005-a48b8401`, mit Pipeline25995 und47Schemaquellen. Genau zwei Performancequellen wurden geändert; Semantik und DB-Verträge bleiben erhalten. Veröffentlichung und tatsächlicher Cold-Flow stehen in[NEXT-OPERATIONS.md](NEXT-OPERATIONS.md).

Die fünf ursprünglichen Dateien sind mit Hashes in `/root/dashboard-intake-transition-perf-20261005T2157/perf-five-file-before` gesichert. Ihr Image ist `sha256:8f72278bafb04e24dd04468d941dedaf0ead4d1638cebf4081edf600e185e471`, Tag `dashboard-memory:archive-generation-reason-overlay-20261005-2bfdad83-v2`. Bei Fehler zuerst aktuellen Stand und Vorherhashes prüfen. Es gibt keine automatische Rücksetzung über neue Daten, Jobs oder bezahlte Antworten. Abgeleitete SQLite-Caches sind getrennt privat gesichert.

Der letzte vollständig geprüfte Datenrückkehrpunkt ist `dashboard-20261005T212531Z.tar.gz`, SHA `317379754cc99ef341e0312c9cf34ca69b37b5f4d8cdeda3b1fe1a4318a2d59d`: Revision226, Archiv871,396Originale,1505Calls, isolierter Restore89Tabellen/Auth/Vault/Rollen/n8n positiv und253Dateien bytegleich auf dem Mac. Das Bundle enthält8f mit47Schemaquellen. Für die neuere5d-Codefassung zusätzlich das exakt gebundene Performance-Releasepaket verwenden. Die eigene Code-/Belegversion ist Commit79741bf82fd5f986bb88256124027c6d2bce4d55; [Versionsquittung](../evaluation/work-projection-20261005/root-live-release/own-version-receipt.json) bestätigt alle184Blob-Inhalte und erhaltene fremde Indexeinträge. Das ist eine Codeversion, kein neues5d-Vollbackup.

Beim Vollrestore Paket und Imageidentität prüfen, Writerflags schließen und den bestehenden isolierten Targetweg nutzen. Vor Öffnung `wm_generation_decide` gegen Sollhash52e und Dienstrollen-ACL sowie Originalowner, Humanentscheidungen und Callhistorie prüfen. Diese spezifische Funktionshashabfrage ist im neuen Restorebeleg nicht gesondert ausgeführt. Ein finales Backup nach produktivem Queue-Abfluss steht aus. Source-Supabase bleibt geschlossen.

## Historischer V4-Runtime-Rückweg der Queue-Reparatur – 05.10.2026

Tatsächlicher Backendwechsel 05.10., 18:50:35 UTC und Queue-Cutover 18:52:32 UTC: Das damals laufende V4-Image ist `sha256:2c935de2b6c458810c67dbe7b10e07ec8ee06a97bbca305bc9e8582bf5e3e6cb`, Compose-Tag `dashboard-memory:queue-placeholder-20261005-b3e22868`. Der normale Start verwendet die dauerhaft aktualisierte `compose.yaml`, kein privates temporäres Override. Der tatsächliche Release-/Sicherungsstand steht ausschließlich in [NEXT-OPERATIONS.md](NEXT-OPERATIONS.md).

Das geänderte bestehende Backup nimmt `Dockerfile`, `scheduled_backup.py`, 46 Schemaquellen und das tatsächlich laufende Image als `memory-image.tar` in dasselbe gehashte Bundle auf. Das durch Image-ID gespeicherte Docker-Archiv kann ohne Tag geladen werden. Deshalb nach vollständiger Bundleprüfung und `docker load -i memory-image.tar` die tatsächlich geladene Image-ID gegen die gesicherte Containeridentität prüfen und **erst dann** auf den in der gesicherten Compose-Konfiguration belegten Image-Tag setzen. Für genau dieses V4-Release sind dies die beiden obigen Werte; bei fehlender, abweichender oder unklarer Identität keinen Dienst starten. Anschließend die Runtimequellen gegen das Bundlemanifest prüfen, sämtliche Schreibflags geschlossen halten und den bestehenden isolierten Target-Restoreweg verwenden. Ein erfolgreicher `docker load` allein belegt weder den richtigen Compose-Tag noch eine Datenwiederherstellung. Vorherige Sicherungen ohne `memory-image.tar` nicht als Beleg für diese neue Fähigkeit ausgeben.

Vor dem atomaren Queue-/Configwechsel darf der gebundene Hostvertrag `rollback-before-cutover` ausschließlich die hashgeprüften ursprünglichen Gateway-/Runtime-/Dockerfile-/Compose-/Backupquellen und das ursprüngliche Image wiederherstellen. Nach dem Queuewechsel keine automatische Rücksetzung über neue Jobs, Originale oder bezahlte Antworten; zuerst nur betroffene Verarbeitung halten und den tatsächlichen Targetstand prüfen. Source-Supabase bleibt geschlossen.

## Gültiger Wiederherstellungsweg nach Hetzner-Cutover – 04.10.2026

Der aktuelle Betrieb und seine tatsächlichen Sicherungsquittungen stehen in [NEXT-OPERATIONS.md](NEXT-OPERATIONS.md). Datenbank, Auth und kanonisches Backend liegen jetzt auf Hetzner. Seit der erfolgreichen Writer-Öffnung darf das alte Source-Supabase weder als aktueller Datenstand verbunden noch durch `final_prewrite_rollback_once.py` reaktiviert werden. Die folgenden älteren Supabase-Wiederanlaufhinweise gelten ausschließlich für ihren ausdrücklich historischen Stand.

Bei einem Fehler zuerst nur die Dashboard-Verarbeitung und ihre drei n8n-Workflows pausieren; aktuelle Target-Daten, Quittungen und externe Löschbarriere erhalten. Ein Frontend-Rollback setzt die Datenbank nicht zurück. Der Rückweg führt über die letzte verifizierte **Target-Vollsicherung** unter `/var/backups/dashboard-job/` oder deren bytegleiche Mac-Kopie unter `~/Library/Application Support/Dashboard Job Backup/archives/`, mit einem neuen, leeren, zunächst isolierten PostgreSQL17-Ziel und den im Archiv festgehaltenen Imageidentitäten und Konfigurationsdateien. Niemals die gemeinsame n8n-Datenbank oder andere Projekte im laufenden Betrieb überschreiben. Das neue Wiederherstellungsziel beginnt mit `MEMORY_READ_ONLY=1` und allen vier Intake-/Automatic-/QA-/Original-Deletion-Flags auf0; die im Vollarchiv gesicherten offenen Produktivflags nicht automatisch übernehmen.

Vor Restore Paket-SHA und sämtliche Einträge über den bestehenden `offserver_backup.verify_bundle` prüfen, aktuellen externen Löschledger separat attestieren und Originale, vollständiges selbst gehostetes Datenbank-/Auth-/Vault-/Rollenabbild sowie n8n-Konfiguration zusammen erhalten. Der Selbsthosting-Anteil liegt unter `selfhost/`; die tatsächlichen isolierten Prüfquittungen heißen `selfhost/restore-check.json` und `n8n-restore-check.json`. Die frühere reine kanonische Schema-Bootstrapfolge und eine neue Owner-Anlage sind kein Ersatz für diesen vollständigen Auth-Restore. Erst nach ursprünglicher Owner-Identität, Archiv-/Original-/Summary-/Hashgleichheit und gesundem Backend den neuen Target-Endpunkt verbinden und Verarbeitung kontrolliert freigeben.

Tatsächlich geprüft sind vollständige Sicherung, isolierte PostgreSQL-/Auth-/Vault-/n8n-Wiederherstellung und unabhängige Mac-Dateiprüfung. Ein vollständiger Wiederaufbau nach physischem Serververlust wurde nicht ausgeführt. Der originale tägliche Timer und sein bereits seit19.09.2026 vorhandenes45-Minuten-Drop-in bleiben aktiv; keine neue Laufzeitgrenze wurde bei diesem Abschluss eingerichtet. Geheimnishaltige Sicherungen bleiben privat (0700/0600).

## Historische Anleitung und Nachweise ab 19.09.2026

Stand 19. September 2026. Die Wiederherstellung beginnt immer mit pausierter Verarbeitung. Ein bestehender Arbeitsbereich wird nicht überschrieben. Produktiver Wiederanlauf erfolgt erst nach Prüfung und Freigabe.

## RC2-Schema auf einem leeren Ziel aufbauen

Die historische Supabase-Migrationsfolge enthält eine dokumentierte Lücke: Nach
`20260907132739_working_memory_uncapped_processing.sql` erlaubt
`wm_reserve_call` noch höchstens 15 Aufrufe. Die folgende
`20260908163023_working_memory_hybrid_search.sql` erwartet aber bereits den
historischen Hotfix auf 31 und erweitert ihn dann auf 1023. Die alten
Migrationsdateien werden dafür nicht verändert.

RC2 besteht ausschließlich aus den kanonischen `202609*.sql`-Dateien im
Sicherungsordner `schema/`; alte Dashboard- oder Supabase-Migrationen außerhalb
dieses Pakets gehören nicht dazu. Im laufenden Paket verwendet das Skript daher
standardmäßig `/app/schema`, lokal ersatzweise `working-memory/schema/` und nur
für diesen Workspace `supabase/migrations/`.

Vor einem Datenrestore auf einem **neuen, leeren** Supabase-Postgres-Ziel den
prüfbaren RC2-Plan erzeugen und prüfen:

```sh
cd working-memory
python3 restore_schema.py --output /private/tmp/meeting-rc2-schema.sql
```

Für den kontrollierten Lauf das Skript verwenden, nicht die Plan-Datei direkt
an `psql` übergeben. Es prüft vor dem Anwenden, dass `public` keine Tabellen
enthält:

```sh
python3 restore_schema.py --database-url "$RESTORE_DATABASE_URL" --apply
```

Der Plan fügt genau vor `20260908163023` eine operative 15→31-Bridge ein. Sie
prüft die erwartete Funktionsversion, ändert die Tabellenbeschränkung und die
Funktionsgrenze und prüft anschließend die Grenze 31. Bei einer abweichenden
historischen Funktion bricht der Plan ab. Er enthält außerdem Fragen,
Backup-Referenzen und die sequenzielle Backup-Hydration. Trotz seines früheren
CLI-Zeitnamens läuft `20260919202704_backup_page_sequential_hydration.sql`
nach `20260919214500_backup_completed_call_references.sql`, weil es dessen
Funktionspatch voraussetzt. RC2 enthält zusätzlich die geprüfte Löschfolge
`20260919200321` (Ledger), `20260919201406` (Purge), `20260919202831`
(sanitisierte Quittungen) und `20260919214722` (Fragen-Löschepoche), in dieser
expliziten Reihenfolge nach der Hydration-Abhängigkeit. RC1-Pakete bleiben unverändert und sind kein Ersatz für
diesen RC2-Bootstrap.

Das ist nur ein Schema-Bootstrap. Erst danach den bereits geprüften,
pausierten Datenrestore ausführen. Den Plan nie gegen
`dashboard-release-db-20260919` oder ein anderes bestehendes Ziel anwenden.
Das minimale `auth.users`-Fixture eines isolierten Schematests ist kein
Auth-Restore: In einem echten neuen Supabase-Projekt muss das verifizierte
Eigentümerkonto vor dem Datenrestore vorhanden sein.

## Gesicherter Umfang

Die tägliche Serversicherung liegt in `/var/backups/dashboard-job/`. Sie enthält das Supabase-Arbeitsjournal, vollständige Originale und vorhandene Notizen, persönliche Entscheidungen, vorbereitete Korrekturen, Warteschlange und Kostenbelege. Dazu kommen die versionierten SQL-Migrationen, der geprüfte Python-Laufzeitstand, Betriebsdateien sowie n8n-Datenbank, n8n-Datenverzeichnis und die für die Entschlüsselung nötige Konfiguration. Geheimnisse sind deshalb in diesen Dateien enthalten: Verzeichnisse 0700, Dateien 0600.

Die Löschbarriere liegt absichtlich außerhalb rotierender Archive: auf dem
Server in `/opt/dashboard-memory-canonical-draft/.local/cache/restore-barrier/deletions.json`
und auf dem Mac in `~/Library/Application Support/Dashboard Job Backup/restore-barrier/deletions.json`.
Jeder Backup-Lauf attestiert sie vor dem Export erneut; die Mac-Kopie akzeptiert
nur denselben oder einen höheren Löschstand. Eine Barriere aus einem alten Archiv
darf diese aktuelle externe Datei nie ersetzen.

Die Sicherungsquittung weist den attestierten Löschstand und den Zeitpunkt der
Attestierung aus; die Mac-Quittung zusätzlich den beobachteten Ledgerzeitpunkt
und `last_copied_at`. Diese Daten belegen nur den letzten erfolgreichen Abgleich.
Bei gleichzeitigem Host- und Datenbankverlust kann eine noch nicht synchronisierte
Mac-Kopie neuere Löschungen nicht beweisen. Fehlt ein nachweislich aktueller
externer Ledger, findet kein Datenrestore statt. Es gibt keinen automatischen
Fallback auf einen Ledger aus dem Archiv. Wenn die Datenbank noch erreichbar ist,
muss die Barriere vor dem Restore erneut gegen ihren aktuellen Löschstand
attestiert werden.

Die zweite Kopie liegt auf dem Mac unter `~/Library/Application Support/Dashboard Job Backup/archives/`. Der LaunchAgent `de.gleb.dashboard-job.backup-pull` prüft beim Anmelden und alle sechs Stunden. Er benötigt einen eingeschalteten und verbundenen Mac. Dies ist kein ständig erreichbarer zweiter Cloudserver und keine zusätzliche Verschlüsselung des Sicherungspakets.

Die historische geprüfte Sicherung vom 07.09. ist `dashboard-20260907T091240Z.tar.gz`, SHA-256 `fa6472473a92169d35e1db0d941f011e4d02729f04eefdbdbb2d8deccf2ed777`. Revision106, Archiv492, 194 Originale, 298 Notizen, ein vorbereiteter Korrekturvorschlag. Alle 87 Paketdateien wurden auf dem Mac unabhängig geprüft. Der Inhalt wurde außerdem in PostgreSQL17 vollständig in einer Transaktion zurückgespielt, zeilenweise mit dem erwarteten Inhalt verglichen und zurückgerollt. n8n wurde auf einem internen Docker-Netz ohne externen Zugriff wiederhergestellt; elf Workflows blieben deaktiviert, vier Zugangsdaten konnten entschlüsselt werden.

## 1. Paket prüfen

Die erwartete Paket-Prüfsumme gegen die Sicherungsquittung vergleichen. Vor dem Entpacken alle Dateinamen prüfen: keine absoluten Pfade, kein `..`, keine Links oder Sonderdateien. Der bestehende `offserver_backup.py` prüft bereits jede Datei anhand von `bundle-manifest.json`, einschließlich Länge und SHA-256; eine erfolgreich übertragene Datei allein ist kein Wiederherstellungsnachweis.

In ein neues privates Verzeichnis entpacken. Anschließend mit den aktuell
geprüften RC2-Werkzeugen außerhalb des Archivs arbeiten; die Runtime-Dateien im
Archiv dokumentieren nur den damaligen Stand und sind kein autoritativer Ersatz.
Die externe Löschbarriere vor dem Erzeugen des Datenrestores prüfen:

```sh
python3 /opt/dashboard-memory-canonical-draft/canonical_backup.py verify canonical
python3 /opt/dashboard-memory-canonical-draft/canonical_restore.py canonical restore-reviewed.sql \
  --restore-ledger /opt/dashboard-memory-canonical-draft/.local/cache/restore-barrier/deletions.json
```

Bei Fehlern keine Prüfsummen oder Daten zurechtändern. Das letzte gültige Paket verwenden oder die Ursache klären. Die mitgelieferte `restore-paused.sql` wurde bereits gegen dieselben Quelldateien erzeugt; ihre Prüfsumme steht in der Begleitquittung.

## 2. Supabase und Benutzerkonto

Für einen reinen Hetzner-Ausfall bleibt Supabase unverändert; dann kein Datenbank-Restore. Neue Serverkonfiguration mit dem bestehenden Projekt und Arbeitsbereich verbinden und die lokalen Caches aus Supabase neu aufbauen.

Für einen vollständigen Datenbankverlust zuerst ein sauberes Supabase-Projekt vorbereiten. Den RC2-Schemaaufbau aus `schema/` ausschließlich über das aktuelle `restore_schema.py` außerhalb des Archivs ausführen; die Dateinamenreihenfolge ist wegen der expliziten Backup-Referenzen→Hydration-Abhängigkeit nicht ausreichend. Supabase Auth muss den verifizierten Eigentümer mit derselben UUID enthalten: `4add9215-310d-49b4-801f-37f6b3b48131`. Der Restore bricht ab, wenn dieses Konto fehlt.

Das Anwendungspaket enthält keine Supabase-Passwörter, MFA-Faktoren oder bestehenden Anmeldesitzungen. Eine vollständige Supabase-Datenbanksicherung kann das Auth-Schema erhalten. Falls sie nicht verfügbar ist, kann ein berechtigter Betreiber im **neuen leeren Zielprojekt** das einzelne verifizierte Konto über `auth.admin.createUser` mit derselben expliziten `id`, seiner verifizierten E-Mail-Adresse und einem neu gesetzten Passwort wiederherstellen. Vorher prüfen, dass weder diese UUID noch dieselbe E-Mail dort einem anderen Konto gehören; niemals einen bestehenden Benutzer ersetzen. Diese Wiederherstellung darf keine alte Sitzung oder MFA-Anmeldung als fortbestehend ausgeben. Der aktuelle Supabase-Admin-API-Typ unterstützt `id`; der Auth-Server übernimmt diese UUID auch für die E-Mail-Identität. Dieser alternative Auth-Neuanlageweg wurde hier anhand des offiziellen Codes geprüft, nicht mit Glebs Produktivkonto ausgeführt. Quellen: [Supabase-Datenbanksicherungen](https://supabase.com/docs/guides/platform/backups), [AdminUserAttributes](https://github.com/supabase/supabase-js/blob/master/packages/core/auth-js/src/lib/types.ts), [Auth-Admin-Implementierung](https://github.com/supabase/auth/blob/master/internal/api/admin.go).

Dann `restore-reviewed.sql` mit `psql -v ON_ERROR_STOP=1 -f restore-reviewed.sql` gegen das geprüfte Ziel ausführen. Der erzeugte Code stellt den Bereich als `draft` und die Verarbeitung als deaktiviert wieder her. Er prüft alle zehn Anwendungstabellen mit `EXCEPT ALL` in beide Richtungen und verweigert das Überschreiben eines vorhandenen Bereichs. Journal-IDs, persönliche Entscheidungen, Quelltexte und bereits bezahlte Antworten bleiben erhalten.

Vor dem ersten Dienststart die archivierten Providerquittungen mit dem aktuellen Werkzeug außerhalb des Archivs übernehmen und ausschließlich über das bereits eingerichtete, eng begrenzte Gateway persistieren: `python3 /opt/dashboard-memory-canonical-draft/restore_outboxes.py /pfad/zum/entpackten/paket`. Das Werkzeug prüft den Paket- und Quittungsmanifest, die darin deklarierten `response-outbox`- und `question-outbox`-Dateien sowie Dateiname, Identität, Scope und Antwort-Hash. Ein leerer Ordner darf im Tar fehlen, aber nur bei explizit leerem Quittungsmanifest. Es führt keine Modellanfrage aus. Bei einer fehlenden oder widersprüchlichen Quittung bricht es ab; erst nach einer bestätigten `receive`-Operation wird die Arbeitskopie der Quittung entfernt. Danach bleiben Verarbeitung und Intake bis zur normalen Abnahme deaktiviert.

Der Edge-Gateway und dessen eng begrenztes Dienst-Token werden separat eingerichtet. Projektadresse, öffentlicher Schlüssel und erlaubte Eigentümer-ID müssen zu diesem Ziel gehören. Supabase-Auth-Site-URL und Redirects für die veröffentlichte App neu prüfen. Ein Test muss Anmeldung, Lesen des Archivs, Quellenbeleg und eine ausdrücklich als Test gekennzeichnete eigene Entscheidung umfassen.

## 3. n8n und Verarbeitungsserver

n8n und PostgreSQL zunächst in ein internes Testnetz ohne externe Verbindung wiederherstellen. `n8n.dump` mit `pg_restore --no-owner --no-privileges --exit-on-error` einspielen. Ausschließlich in der restaurierten Kopie alle Workflows deaktivieren, `activeVersionId` leeren und `workflow_published_version` leeren. `active=false` allein reicht bei dieser n8n-Version nicht aus. Mit dem gesicherten `N8N_ENCRYPTION_KEY` eine CLI-Entschlüsselungsprüfung durchführen; Geheimnisse nicht protokollieren.

Die produktiv laufenden Picnic-/Alexa-Komponenten dürfen bei einem Dashboard-Restore weder überschrieben noch neu gestartet werden. Auf einem vorhandenen gemeinsamen n8n-Server nur die Dashboard-Workflows und benötigten Zugangsdaten gezielt übernehmen. Ein vollständiger n8n-Datenbank-Restore ist ausschließlich für einen vollständigen Serververlust bzw. eine leere Testumgebung vorgesehen.

Den Verarbeitungsdienst aus dem gesicherten Dockerfile aufbauen. Er läuft als Benutzer10001 mit schreibgeschütztem Root-Dateisystem; nur der Cache darf geschrieben werden. Vor dem Start alle Dateien gegen `build-manifest.json` prüfen. Seit dem abschließenden Sicherungstest umfasst diese Liste auch `canonical_backup.py`, `canonical_restore.py` und `scheduled_backup.py`, damit veraltete Sicherungshelfer nicht unbemerkt zurückbleiben.

`MEMORY_AUTOMATIC_ENABLED=0` und `MEMORY_INTAKE_ENABLED=0` beibehalten. `/health` muss erreichbar sein; Archiv, Arbeitsstand und Korrekturendpunkte müssen ohne Benutzeranmeldung 401 liefern. Den Journal- und Archivcache frisch aus dem restaurierten Supabase aufbauen und mit der Quittung vergleichen. Unbekannte Kostenreservierungen bleiben belastet; ein Neustart ist keine Erlaubnis für neue Modellaufrufe.

## 4. Oberfläche und Wiederanlauf

Die geprüfte Vercel-Vorschau vom Abschluss dieser Runde ist `dpl_yAYP51FEt2oapq6cPHsg4DSLxfRa`. Die öffentlichen Dateien mit Prüfsummen stehen in `evaluation/source-order-deployment-result.json`; ein vollständiges lokales Dateipaket liegt unter `.local/final-frontend-files.json`. Die produktive Umschaltung ist damit noch nicht erfolgt. Bei geändertem Supabase-Projekt die öffentliche Projektkonfiguration neu bauen und die API-Weiterleitung auf den geprüften Server setzen.

Vor Freigabe: echten Kontozugriff prüfen, ein Original mit vorhandener Zusammenfassung öffnen, den historischen Wissensstand prüfen, den vorbereiteten Korrekturvorschlag einschließlich Identitäten vergleichen, Google Drive erneut autorisieren, Enddatum der manuellen Altbestandsgrenze und dauerhaftes API-Budget prüfen. Erst dann neuen n8n-Import und Verarbeitung aktivieren. Make sowie alte Trigger/Crons dürfen nicht parallel wieder anlaufen.

## Grenzen und Rückweg

Die alten Supabase-Tabellen, 3.197 Transkriptchunks und 71 verbliebenen Embeddings bleiben bei der Migration unverändert in Supabase. Sie sind **nicht** Teil dieses kanonischen Anwendungsexports. Das neue Archiv und der neue Arbeitsstand lassen sich ohne sie wiederherstellen. Wer zusätzlich den vollständigen alten Datenbankzustand einschließlich Vektoren und Auth benötigt, braucht eine separate vollständige Supabase-Datenbanksicherung; ein solcher Komplett-Restore wurde hier nicht behauptet. Supabase Storage enthält laut letzter Prüfung keine Objekte.

Bei einem Fehler nach Umschaltung zuerst neuen Intake und Worker pausieren. Die letzte gültige neue Journalrevision und ihre Quittungen behalten; keine pauschale Rücksetzung, keine erneute Modellverarbeitung. Ein UI-Rollback allein darf keinen alten Import wieder aktivieren. Alte und neue Schreibpfade nur nach einem explizit geprüften Rückweg wechseln.

## Zusätzliches Release- und Rückwegpaket

`cutover-release-20260907.tar.gz` enthält 15 Dateien: die geprüften öffentlichen Frontenddateien, bisherige neun Edge-Funktionen, Trigger-/Berechtigungs-/Cron-Inventar, vorbereiteten Abschaltcode, dessen lokalen Test und die bisherige gemeinsame Nginx-Site. SHA-256: `cdd09d25c150e47faa8cf9a4c1d628295d10e2f2a0cea91e01aa092cc2860127`. Unabhängige Kopien auf dem Server in `/var/backups/dashboard-job/` und im Mac-Sicherungsordner wurden bytegenau geprüft. Das Paket ist privat; alte Funktionsdefinitionen und Konfiguration können Zugangsdaten enthalten.

`restore-legacy-grants-and-triggers.sql` ist ausschließlich ein bewusst auszuführender Rückweg nach Pausieren der neuen Verarbeitung. Es stellt die vorherigen Rechte und Triggerzustände wieder her und aktiviert dadurch auch alte Automatik. Nicht bei einem reinen Frontend-Rollback ausführen. Die gemeinsame Nginx-Site enthält weitere Anwendungen; sie darf auf einem bestehenden Server nicht pauschal überschrieben werden. TLS-Zertifikate sind kein Bestandteil dieses Zusatzpakets.

### Laufzeitgrenze des täglichen Backups

Nach Wiederherstellung `ops/dashboard-job-backup.service` mit `TimeoutStartSec=45min` installieren. Die aktuelle Installation verwendet dafür `/etc/systemd/system/dashboard-job-backup.service.d/runtime-limit.conf`. Der vollständige Export des Suchbestands braucht mehrere Minuten; die frühere 15-Minuten-Grenze war bei großen Sicherungen zu knapp. Die verlängerte Grenze ändert weder Aufbewahrung noch den täglichen Termin.

## Letzter echter Wiederherstellungsnachweis

Sicherung `dashboard-20260919T223616Z.tar.gz` (1.322.488.810 Bytes, SHA256 `41a301cbbc411c68966e71f722a4106889788cfb08ef5890e001ebbe127cd403`) vollständig in eine frische PostgreSQL16/pgvector-Testdatenbank eingespielt. Netzwerk isoliert, Automatik nach Restore ausgeschaltet, null Modellaufrufe. Journal134/Archiv705, 318 Originalversionen, sechs Fragen/51 Chat-Aufrufbelege, Recoverykosten313940µUSD stimmen. Mac-Kopie unabhängig geprüft (141 Dateien). Das künstliche 512-MB-Containerlimit reichte für den Restore nicht; mit 1GB erfolgreich. Dies validiert die kanonischen App-Daten und den separat getesteten n8n-Restore, nicht sämtliche Legacy-Supabase-Tabellen oder den vollständigen Supabase-Auth-Dienst.

Nach diesem RC3-Sicherungsstand wurde RC4 mit zwei zusätzlichen Migrationen produktiv gesetzt. Das getestete 35-Migrations-Schemaset und der vollständige Quellcode liegen zusätzlich auf dem Mac unter `~/Library/Application Support/Dashboard Job Backup/releases/rc4-runtime.tgz` (SHA256 `0c27c3b4a6e289a1d7c83a342b11e46c0b6dc5e8f16b6e1e9c85d31fdb800fe8`). Bei Nutzung der genannten Vollsicherung RC4 vor Freigabe der Verarbeitung anwenden. Nicht automatisch den Worker einschalten; erst Restore und aktuelle externe Löschsperre verifizieren.


## Resize-Sicherung 03.10.2026

Vor dem freigegebenen CAX11→CAX21-Resize wurde eine aktuelle externe Sicherung direkt über Strict-Host-Key-SSH auf den privaten Mac gestreamt. Zeitpunkt und Hashes: `../evaluation/rescale-safety-20261003.json`; vollständige private Nachweise in `~/Library/Application Support/Dashboard Job Backup/rescale-20261003/validation.json`. Kein bestehendes Backup gelöscht; keine Dienste gestoppt oder verändert. Ein vollständiger Backup-/Validierungszyklus erfolgreich; fehlender optionaler Legacy-SQLitepfad wurde anhand des realen kanonischen Betriebs geklärt.

`host-runtime.tar.gz` enthält `/opt/dashboard-memory-canonical-draft` einschließlich `.local`, `/opt/n8n`, das vollständige n8n-Datenvolume, Picnic-Laufzeit, Nginx/Zertifikate/Systemd/Cron. Das private `host-file-manifest.json` belegt 4052 Datei-/Symlink-Einträge. `services-after.json` enthält die tatsächliche Dockerkonfiguration einschließlich n8n-Verschlüsselungsschlüssel; nicht veröffentlichen. `local-images.tar.gz` enthält die lokal gebauten Dashboard- und Picnic-Images. Deren Dockerarchiv, Konfiguration und Layer wurden gelesen; ein Docker-Image-Load oder vollständiger App-Start wurde lokal nicht ausgeführt.

`n8n.dump` wurde tatsächlich mit PostgreSQL17.10 in eine entbehrliche lokale Datenbank eingespielt (`pg_restore --no-owner --no-privileges --exit-on-error`). TCP war deaktiviert, Zugang nur über privaten Unix-Socket. 86 Tabellen, 15 Workflows und sechs Zugangsdaten; kein Workflowstart, keine Credential-Entschlüsselungs-CLI. Die Testinstanz wurde gestoppt und ausschließlich selbst angelegte temporäre Restoredateien gelöscht. Ein Hostverlust-Restore verwendet die gesicherte PostgreSQL16-Imageidentität und den bestehenden isolierten n8n-Restoreablauf dieses Runbooks vor einer Freigabe.

Sieben aktive SQLite-Projektionen aus `projections-rc1-20260919` wurden per SQLite-Onlinebackup von readonly Quellen konsistent gesichert (`sqlite-online.tar.gz`). Jede Datei wurde lokal entpackt, `integrity_check` und sämtliche Tabellenzahlen mit dem Onlinebackupmanifest verglichen. Beim Hostverlust diese konsistenten Dateien über die entsprechenden Rohkopien des Hostarchivs legen; keine alten WAL/SHM-Dateien darüber übernehmen. `MEMORY_DB=.../service.sqlite` ist im kanonischen Dienst ein verbliebener Legacy-Konfigurationswert, die Datei existiert nicht. Vier aktuelle Outbox-/Löschbarrier-Dateien sind vor Sicherung, im Hostarchiv und nach Sicherung hashidentisch.

Grenze: Das gestreamte Hostarchiv ist kein atomarer Gesamtsnapshot. Aktive SQLite-Dateien sind separat konsistent; Supabase bleibt beim Resize unabhängig und wird mit diesem Paket nicht gesichert oder migriert. Die vier Container behielten Identität, Image, Konfiguration, Mounts und Startzeit; Dashboard/PostgreSQL waren weiter healthy. Sichere Abschaltung und kontrollierter Neustart gehören dem Lead. Diese Nachweise ersetzen weder einen vollständigen Supabase-Dump noch eine vollständige Nutzerfluss-Abnahme nach Migration.
