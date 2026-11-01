# Backend-Deployment: belegter Cache-Rollout und geplanter Flex-Wechsel
Stand: 13.10.2026; ausschließlich lokale Recherche. Alle Befehle unten sind Plan, nicht ausgeführt; externe Ausführung benötigt ein eigenes Deploymentmandat. Keine Meetinginhalte/Secrets.
Quellenkürzel ab Repo-Root: C=`working-memory/evaluation/production-cost-20261012`; B=`working-memory/evaluation/sol-operational-release-20261006/backend` (historischer Codesnapshot, keine Live-Funktionsprüfung).
S=`B/schema`; O=`working-memory/ops`; D=`working-memory/docs`; F=`working-memory/evaluation/poc-tiered-reconcile-20261012/pipeline-v13/flex`. `S` und `F` werden durch die vorherigen Pfade expandiert.

## 1. Tatsächliche Schrittfolge vom 12.10.2026
1.1 Drei Kandidatdateien: `openai_provider.py`, `durable_calls.py`, zusätzlich `question_calls.py`; alle jeweiligen Before-/After-Hashes sind belegt. Erster Zweidateien-Kandidat wurde durch Dreidateien-Image ersetzt. Quelle: C/cache-build-v1.json:1; C/cache-build.json:1.
1.2 Kandidat gebaut, Tag `dashboard-memory:cache-explicit-20261012` auf Image `sha256:9f3d69222e0602327d73fe1665e47da05661938575b6a8204ab4cd5d468f85c2`; Buildquittung nennt `network=none`, `published=false`. Exakter Build-/Transferbefehl und Kandidat-Dockerfile fehlen lokal; eine konkrete Rekonstruktion wäre Hypothese. Quelle: C/cache-build.json:1; C/rollout_cache.py:38-42.
1.3 Nach aktuellen Backup-/Restorebelegen und exklusivem Backup-Lock: altes Image, alte Pipeline, Kandidat und Quelldeltas geprüft; drei `.py.before`, Compose und Hostmanifest gesichert. Quelle: C/rollout_cache.py:30-47.
1.4 Atomarer Hold: alte Config musste enabled sein; keine Jobs außerhalb applied/archived, keine unempfangenen Job-/Question-Calls; ausschließlich `enabled=false`. Quelle: C/rollout_cache.py:50-52.
1.5 Drei Dateien aus `.local/recovery/production-cost-20261012/cache-candidate` atomar auf flache Hostpfade kopiert, Hashes im Hostmanifest aktualisiert; Compose-Tag `combined-p4-cap-backup-20261007-61be51be` durch Cache-Tag ersetzt. Quelle: C/rollout_cache.py:55-59.
1.6 Container neu erstellt: `docker compose -f /opt/dashboard-memory-canonical-draft/compose.yaml up -d --no-deps --no-build --pull never canonical-draft`; danach /health bis HTTP200, tatsächliches Image/Pipeline und unveränderte Runtime-/Daten-/Callbindung geprüft. Quelle: C/rollout_cache.py:60-72.
1.7 Erst danach Transaktion mit `UPDATE wm_processing_config SET pipeline='<NEW>',enabled=true WHERE space_id='<SPACE>' AND pipeline='<OLD>' AND NOT enabled`; vorher positive Prüfung der pausierten alten Config. Kein Cutover-Funktionsaufruf, keine Job-Umbindung. Quelle: C/rollout_cache.py:73-75.
1.8 Erfolg 15:49:11 UTC (=17:49:11 MESZ), Automatik aktiviert; Queue weiterhin leer. Erste Ablehnung 15:45 wegen Env-Reihenfolge führte tatsächlich zur alten Pipeline/aktivierten Verarbeitung zurück. Quelle: C/cache-rollout.json:2-9; C/cache-first-refusal-rollback.json:1; C/README.md:77; C/post-rollout-data-check.json:2-16.
Alte Pipeline: `v11:compact1:gate1:gpt-6.1-sol:887ca68d3c013fe8:canonical1:42317499c5d8a62a`; neue: `v11:compact1:gate1:gpt-6.1-sol:753caadf3fb8fea4:canonical1:023a8c7cae48980c`. Quelle: C/rollout_cache.py:3.

## 2. Pipelinekennung, Jobs und Recovery
2.1 `hybrid_pipeline.version()` hasht u.a. Adapter und Budgetcode; `canonical_worker.pipeline_version(MODEL)` ergänzt einen eigenen Hash u.a. über durable_calls. Nur Adapter/Budget ändern deshalb den ersten Fingerabdruck; bei sonst identischer Basis bleibt der canonical1-Suffix gleich. Ordnername pipeline-v13 erzwingt keinen v13-Präfix. Quelle: B/hybrid_pipeline.py:27-33; B/canonical_worker.py:36-39.
2.2 Beim 12.10.-Wechsel war die Queue vollständig terminal; bestehende Jobkennungen wurden nicht verändert. Die 456 `pipeline_cutover` sind Nutzerangabe, lokal hier nicht als Gesamtzählung/12.10.-Ereignisse belegt. Quelle: C/rollout_cache.py:51,73; C/post-rollout-data-check.json:6.
2.3 Historischer auditierter Queue-Cutover: SERIALIZABLE, Space→Config→Jobs sperren, Policy/Revision/IDs/updated_at prüfen, nur queued/attempts0 ohne Calls, Lease, Prepared-Payload, Kontext-/Appliedbindung umbinden; Config und Jobs ändern und pro Job `wm_job_decisions(action='pipeline_cutover',previous_job,request,result)` schreiben. Quelle: O/cutover/retarget-unstarted-jobs.sql:11-23,67-143.
2.4 Dieses Skript ist fest an Terra, Revision134 und genau drei Jobs gebunden: NICHT unverändert für Sol/Flex verwenden. Auch neuere historische Templates enthalten feste Versionen/Unknown-Nullbedingungen; sie sind Muster, kein universeller Deployhelper. Quelle: O/cutover/retarget-unstarted-jobs.sql:25-42,62-64; working-memory/evaluation/archive-generation-reason-overlay-runtime20261005/release-guard/cutover-template.sql:14,30-40,74-98.
2.5 Worker≠Config: Claim liefert paused/pipeline_changed; Job≠Config: paused/job_policy_changed, kein automatisches Umschreiben. Unknown-Response setzt review/provider_outcome_unknown; Publish mit falscher Kennung scheitert als Invalid prepared job lease. Quelle: S/20261006103000_isolate_processing_job_failures.sql:201-233,256-269.
2.6 Transport-Recovery nur bei gleicher Worker-/Config-/Jobpipeline, aktueller Revision und nachgewiesen null Calls/vor Prepare; sonst manual_review_required. Owner-Retry/Rebase lehnt falsche Pipeline und unbekannte Ausgänge ab und verlangt ggf. explizite Generation-Review. Quelle: B/pipeline_runtime.py:30-51; S/20260906235000_working_memory_job_recovery.sql:65-84.

## 3. Gates und nummerierte Befehlsfolge für eine neue Flex-Änderung
Historisch vorher: Offline Payload-/Identitäts-/Reuse-/Unknown-Checks in beiden Images; einmaliger genehmigter synthetischer API-Kompatibilitätstest (1.566µUSD, keine Wiederholung). Quelle: C/cache_image_check.py:5-44,46-66; C/cache-image-check-v11.stdout:1; C/cache-image-check-v2.stdout:1; C/cache-probe-once.stdout:1.
Historisch nachher: Runtime/Image/Kennung/Datenbindung, Health, anonyme Archiv-/Review-401, angemeldete UI, passende Vollsicherung/isolierter Restore. Ein regulärer großer Job NACH dem Cache-Einbau fehlte ausdrücklich; kein End-to-End-/Einsparungsnachweis. Quelle: C/rollout_cache.py:63-74; C/actual-post-cache-health.jsonl:1-5; C/final-ui-check.json:2-12; C/README.md:63,79,81.
Planungs-/Versionsreviews existieren; ASTRA-VERSION betrifft Git-Versionierung, keine Flex- oder Cache-Produktfreigabe. Quelle: C/PLAN.md:2,20; C/ASTRA-REVIEW.md:1; C/ASTRA-VERSION-REVIEW.md:3-11.
3.1 Platzhalter aus frischem freigegebenem Stand binden; keine Credentials ausgeben und keine `.env` kopieren:
```sh
ROOT='/opt/dashboard-memory-canonical-draft'; CT='dashboard-memory-canonical-draft-canonical-draft-1'; DB='<DB-CONTAINER>'
SPACE='<SPACE-UUID>'; OLD='<TATSAECHLICHE-ALTE-KENNUNG>'; OLD_IMAGE='<ALTE-IMAGE-ID>'; OLD_TAG='<ALTER-TAG>'
NEW_TAG='dashboard-memory:<NEUER-EINDEUTIGER-TAG>'; STAGE='<ISOLIERTER-BUILDKONTEXT>'; RB='<NEUER-RUECKKEHRPUNKT>'
WAS_ENABLED='<true|false>'; AUTO='<BESTEHENDES-DATUM>'; BUDGET='<BESTEHENDER-INTEGER|NULL>'
db() { docker exec -i "$DB" psql -U postgres -d postgres -X -qAt -v ON_ERROR_STOP=1 -v space_id="$SPACE" -v old="$OLD" -v new="${NEW:-}" -v was_enabled="$WAS_ENABLED" -v auto="$AUTO" -v budget="$BUDGET" "$@"; }
db -c "select pipeline,enabled,automatic_from,budget_micro_usd from wm_processing_config where space_id='$SPACE';"
docker inspect --format '{{.Image}} {{.State.Status}} {{.State.Health.Status}}' "$CT"
```
3.2 Minimal vorher: neues Image offline mit echten geänderten Modulen prüfen: Syntax/Manifest/Kennung; gleiche vollständige Inputs/Schema/Reasoning/Outputgrenzen/explicit-Cache; Flex/default/fehlender oder ungültiger Returned-Tier, Integerkosten/Cachewrites/Langkontext und volle Fallbackreserve; gespeicherte Antwort genau einmal wiederverwenden, Unknown nie senden; Request-/Tarifidentität einschließlich unverändertem Durable- und Question-Pfad belegen. Empfehlung aus C/cache_image_check.py:5-66; C/backend/durable_calls.py:47-99; F/call_budget.py:35-76.
3.3 Nur zwei geprüfte Deltas auf den aktuellen Cache-Produktionsstand legen; vollständiges Manifest erhalten und deren Hashes aktualisieren. Bekannter Root-Dockerfile kopiert nur reconcile/compact/Manifest: Hostkopie allein installiert Adapter/Budget NICHT ins Image. Overlay-Dockerfile separat im Stage bauen; bestehende Root-Datei nicht ersetzen. Serverlayout ist Nutzerangabe, kein hier ausgeführter Servercheck.
```sh
cp '<GEPRUEFTE-openai_provider.py>' '<GEPRUEFTE-call_budget.py>' "$STAGE/"
# STAGE/build-manifest.json: vollständige aktuelle Map, nur beide Quelldelta-Hashes aktualisiert.
printf 'FROM %s\nCOPY openai_provider.py call_budget.py build-manifest.json /app/\n' "$OLD_TAG" > "$STAGE/Dockerfile"
docker build --pull=false --network=none -t "$NEW_TAG" "$STAGE"
NEW_IMAGE=$(docker image inspect --format '{{.Id}}' "$NEW_TAG")
docker run --rm --network none --read-only --tmpfs /tmp:rw -v '<OFFLINE-CHECK.py>:/tmp/check.py:ro' -w /app -e PYTHONPATH=/app --entrypoint python "$NEW_TAG" -B /tmp/check.py
NEW=$(docker run --rm --network none --read-only -w /app --entrypoint python "$NEW_TAG" -B -c 'from canonical_worker import pipeline_version;from openai_provider import MODEL;print(pipeline_version(MODEL))')
```
Buildbefehle sind geplante Rekonstruktion, nicht archivierter 12.10.-Wortlaut. FROM-Tag vorher an OLD_IMAGE binden; `--network=none` allein sperrt keine Registry-Metadatenabfrage. Quelle: C/cache-build.json:1; D/NEXT-OPERATIONS.md:61.
3.4 Vor Wechsel: gültiger aktueller Vollbackup-/Restorebeleg, Backupdienst inaktiv, exklusiven `/run/lock/dashboard-job-backup.lock` für den ganzen Wechsel halten; nicht während laufender Calls neu erstellen. Quellen/Compose/Manifest im neuen RB sichern; aktive reguläre Jobs erst abschließen lassen. Quelle: C/rollout_cache.py:30-51; D/RESTORE-RUNBOOK.md:83.
3.5 Sicherer Standardweg ist eine leere nichtterminale Queue wie am 12.10.; folgender geplanter Hold ergänzt die historischen Prüfungen um Space-/Config-/Calllocks und Policy-CAS (Muster: O/cutover/retarget-unstarted-jobs.sql:67-79):
```sh
db <<'SQL'
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT 1 FROM wm_spaces WHERE id=:'space_id'::uuid FOR UPDATE;
SELECT 1 FROM wm_processing_config WHERE space_id=:'space_id'::uuid FOR UPDATE;
LOCK TABLE wm_model_calls,wm_question_calls IN SHARE MODE;
SELECT 1 / CASE WHEN EXISTS(SELECT 1 FROM wm_processing_config WHERE space_id=:'space_id'::uuid AND pipeline=:'old' AND enabled=:'was_enabled'::boolean AND automatic_from=:'auto'::date AND budget_micro_usd IS NOT DISTINCT FROM NULLIF(:'budget','NULL')::bigint) AND NOT EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=:'space_id'::uuid AND state NOT IN ('applied','archived')) AND NOT EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=:'space_id'::uuid AND received_at IS NULL) AND NOT EXISTS(SELECT 1 FROM wm_question_calls WHERE space_id=:'space_id'::uuid AND received_at IS NULL) THEN 1 ELSE 0 END;
UPDATE wm_processing_config SET enabled=false WHERE space_id=:'space_id'::uuid AND pipeline=:'old';
COMMIT;
SQL
```
Bei Abweisung nichts installieren. Wartende Jobs benötigen einen separat geprüften, frischen auditierenden Cutover nach 2.3; laufende/bezahlte/prepared/review Jobs nicht per Sammel-UPDATE umbinden. Keine historische Vorlage unverändert starten.
3.6 Unter Hold nur zwei Hostquellen, das passende Manifest und den eindeutigen Imageeintrag in Root-Compose installieren; drei Cache-Deltas bleiben durch die Basis erhalten. Geplante Befehle nach positivem Quelldelta-CAS; atomare Ersetzung wie C/rollout_cache.py:46-59 verwenden:
```sh
mkdir -m 700 "$RB"
for f in openai_provider.py call_budget.py build-manifest.json compose.yaml; do cp -p "$ROOT/$f" "$RB/$f.before"; done
for f in openai_provider.py call_budget.py build-manifest.json; do cp -p "$STAGE/$f" "$ROOT/$f.deploy-new"; mv "$ROOT/$f.deploy-new" "$ROOT/$f"; done
python3 -B - "$ROOT/compose.yaml" "$OLD_TAG" "$NEW_TAG" <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1]); s=p.read_text(); old='image: '+sys.argv[2]
assert s.count(old)==1, 'Compose-Tag drift'
t=p.with_name(p.name+'.deploy-new'); t.write_text(s.replace(old,'image: '+sys.argv[3])); t.chmod(p.stat().st_mode & 0o777); t.replace(p)
PY
# Build-Dockerfile/Quittung im RB erhalten; Root-Dockerfile reproduziert diesen Overlaybuild allein nicht.
docker compose -f "$ROOT/compose.yaml" up -d --no-deps --no-build --pull never canonical-draft
docker inspect --format '{{.Image}} {{.State.Health.Status}}' "$CT"
curl --fail --silent http://127.0.0.1:8798/health
docker exec "$CT" python -B -c 'from canonical_worker import pipeline_version;from openai_provider import MODEL;print(pipeline_version(MODEL))'
```
3.7 Minimal nachher VOR Aktivierung: reale Image-ID=NEW_IMAGE, Kennung=NEW, erwartete Runtime/Mounts/read_only, manifestgebundene Quellen und Daten-/Callbestand positiv prüfen; zusätzlich richtige öffentliche Healthroute und anonymes 401. Den geplanten Flex-Env-Delta separat binden, alle anderen Einstellungen erhalten. Quelle: C/rollout_cache.py:63-73; C/actual-post-cache-health.jsonl:1-5.
3.8 Erst nach positivem 3.7 die tatsächliche Kennung aktivieren; geplanter transaktionaler Config-CAS mit denselben Quieszenzbedingungen wie am 12.10. (C/rollout_cache.py:51,73):
```sh
db <<'SQL'
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT 1 FROM wm_spaces WHERE id=:'space_id'::uuid FOR UPDATE;
SELECT 1 FROM wm_processing_config WHERE space_id=:'space_id'::uuid FOR UPDATE;
LOCK TABLE wm_model_calls,wm_question_calls IN SHARE MODE;
SELECT 1 / CASE WHEN EXISTS(SELECT 1 FROM wm_processing_config WHERE space_id=:'space_id'::uuid AND pipeline=:'old' AND NOT enabled AND automatic_from=:'auto'::date AND budget_micro_usd IS NOT DISTINCT FROM NULLIF(:'budget','NULL')::bigint) AND NOT EXISTS(SELECT 1 FROM wm_jobs WHERE space_id=:'space_id'::uuid AND state NOT IN ('applied','archived')) AND NOT EXISTS(SELECT 1 FROM wm_model_calls WHERE space_id=:'space_id'::uuid AND received_at IS NULL) AND NOT EXISTS(SELECT 1 FROM wm_question_calls WHERE space_id=:'space_id'::uuid AND received_at IS NULL) THEN 1 ELSE 0 END;
UPDATE wm_processing_config SET pipeline=:'new',enabled=:'was_enabled'::boolean WHERE space_id=:'space_id'::uuid AND pipeline=:'old' AND NOT enabled RETURNING pipeline,enabled,automatic_from,budget_micro_usd;
COMMIT;
SQL
```
Genau eine Zeile verlangen; ursprüngliches false bleibt false. Frisch während Hold eingetroffene alte Jobs sperren diesen Standardweg; nicht bloß aktivieren. Quelle: C/rollout_cache.py:73; O/cutover/retarget-unstarted-jobs.sql:78-98.
3.9 Bei genehmigter Aktivierung ersten regulären Job anhand IDs/Kennung/attempts/Endzustand/applied_revision/gespeicherter finaler Usage/Returned-Tier/Kosten prüfen, ohne Texte auszugeben; danach Queuefortschritt beobachten. Falls kein Job kommt, End-to-End offen. Einmaliger synthetischer Test nur mit eigener vorhandener Freigabe/Budget; kein automatischer Retry. Historische Grenze: C/README.md:81; C/cache_probe_once.py:8-10,18-28.
3.10 Passende Vollsicherung nach Release und isolierten Restore/Runtimebindung prüfen; vorhandene Projektchecks und erforderliches unabhängiges Release-Gate gelten beim späteren Umsetzungsmandat. Diese Recherche führt keine davon aus. Historisches Vorbild: C/README.md:61-65; C/PLAN.md:20.

## 4. Rückweg zum vorherigen Image und zur vorherigen Kennung
4.1 Wie 3.4/3.5 sicher halten; Rollback einer bereits arbeitenden neuen Pipeline erst nach Drain/Prüfung ihrer Jobs und Callausgänge. Image-/Configwechsel ist kein Datenrollback. Quelle: C/README.md:73-75; D/RESTORE-RUNBOOK.md:199.
4.2 Für genau den Cache-Rollout RB=`$ROOT/.local/recovery/production-cost-20261012/cache-rollout`: drei `.py.before`, `compose.yaml.before`, `build-manifest.json.before` auf passende Hostpfade zurückkopieren; für Flex dessen eigenes Zweidateien-RB verwenden. Vollmanifest nur zusammen mit passendem Quellstand; spätere fremde Deltas nicht überschreiben. Quelle: C/README.md:73-74.
```sh
docker compose -f "$ROOT/compose.yaml" up -d --no-deps --no-build --pull never canonical-draft
# Health und tatsächliche OLD_IMAGE/OLD-Kennung positiv prüfen, erst dann 3.8 mit umgekehrten Kennungen anwenden.
```
4.3 Cache-Rückziel: Image `sha256:c1e9956d5562bdc475b95f0654877bbb5a21bdd885229dbe1682ade8b37ab76e`, alte Kennung aus Abschnitt1, Compose-Tag `dashboard-memory:combined-p4-cap-backup-20261007-61be51be`. Fehlender Nachweis ⇒ paused. Neue unbezahlte Jobs nur mit eigenem auditierenden Rück-Cutover; bezahlte/Unknowns erhalten. Quelle: C/rollout_cache.py:3,44,76-89; C/README.md:73.
4.4 Falls Image fehlt: `docker load -i '<GEPRUEFTES-BUNDLE>/memory-image.tar'`, geladene ID prüfen, dann `docker tag '<BELEGTE-ID>' '<BELEGTER-ALTER-TAG>'`; vollständiger Datenrestore ausschließlich nach Restore-Runbook, kein Source-Supabase-Rollback. Quelle: D/RESTORE-RUNBOOK.md:197-199; C/README.md:75.

## 5. Risiken und Stop-Bedingungen
5.1 `enabled=false` ist kein Drain laufender Calls und keine Intake-Sperre. 12.10.-Hold war quieszenzgebunden; seine Prüftransaktion hatte keine expliziten Space-/Configlocks: kein allgemeiner Race-Freiheitsbeweis. Konfiguration vor gesundem Container umzuschalten bewirkt pipeline_changed/Job-Policy-Pausen; während aktiver Jobs drohen Unknowns/Publish-Ablehnungen. Quelle: C/rollout_cache.py:51,60-73; S/20261006103000_isolate_processing_job_failures.sql:209-233,265-269.
5.2 Unknown-Ausgänge/NULL-Kosten behalten volle Reserve, niemals erneut senden. Historische zwei empfangene Unknown-Zeilen sind nicht null unreceived: Rollout erhielt 631.684µUSD Reserve. Alten strikten Cutover-Unknown-Nullcheck nicht still abschwächen. Quelle: C/backend/durable_calls.py:75-99; C/post-rollout-data-check.json:10,13,15-16; oben genanntes cutover-template.sql:74-76.
5.3 Unverändertes produktives Durable protokolliert `service_tier=default` plus explicit und bindet Pipeline/Revision in den Hash; Flex-Modus ist im Entwurf env-gesteuert. Neue Pipeline trennt Versionsscopes, beweist aber keine korrekte mutable Tarifidentität: Positivnachweis aus 3.2 erforderlich; fehlender Nachweis sperrt Flex-Aktivierung unter dem Zweidateien-Scope. Quelle: C/backend/durable_calls.py:47,54-60; F/openai_provider.py:61-77,250-259.
5.4 Lokaler Flex-Entwurf wiederholt Timeout/5xx und fällt danach auf default zurück; ein Timeout beweist keinen sicher kostenfreien Ausgang. Das kann Unknown-Sperre und Reserve verletzen; keine Übernahme ohne belegte sichere Dispatch-/Abrechnungskette. Außerdem ist dessen durable_calls-Snapshot älter und ohne explicit: niemals ganzen flex-Ordner über Produktion kopieren. Quelle: F/openai_provider.py:263-287; F/durable_calls.py:54-58; C/durable_calls.py.patch:3-9.
5.5 Docker-healthy/HTTP200/UI/leere Queue ersetzen keinen realen Jobnachweis; richtige Healthpfade verwenden, Env-Reihenfolge nur nach Prüfung eindeutiger vollständiger Werte normalisieren. Außenverzeichnisse wurden nicht als unverändert nachgewiesen. Quelle: C/README.md:77,79,81; C/post-cache-live.stdout:2-4; C/actual-post-cache-health.jsonl:1-5.
