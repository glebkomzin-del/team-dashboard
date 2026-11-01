#!/usr/bin/env bash
# Run on the target host ONLY after Lead GO and positive Dashboard intake pause/drain.
# Preparation/preflight is read-only; deploy/cutover/rollback alter the live target.
# Live cutover requires the SHA-bound independent positive intake drain validator.
set -euo pipefail
mode=${1:-preflight}
stage=/root/dashboard-queue-deploy-stage-20261005-b3e22868
pkg=$stage/package
runtime=/opt/dashboard-memory-canonical-draft
compose=$runtime/compose.yaml
dockerfile=$runtime/Dockerfile
backup=$runtime/scheduled_backup.py
edge=/opt/dashboard-supabase-20261003/functions/working-memory-journal/handler.ts
container=dashboard-memory-canonical-draft-canonical-draft-1
db=dashboard-supabase-20261003-db-1
candidate=dashboard-memory:queue-placeholder-20261005-b3e22868
base_id=sha256:7d5e64318a66c3bf0227d694a3d15569263dc96d08b4cd0ae6d8feaeab2a9bcf
candidate_id=sha256:2c935de2b6c458810c67dbe7b10e07ec8ee06a97bbca305bc9e8582bf5e3e6cb
old_pipeline=v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:90c09c38fa788e6a
new_pipeline=v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c
space=96a2dc44-9b9e-4644-b236-c5c1956cd39d
expect_sha() { local got; got=$(sha256sum "$1" | cut -d' ' -f1); [[ "$got" == "$2" ]] || { echo "SHA mismatch: $1" >&2; exit 1; }; }
expect_image() { [[ "$(docker image inspect "$1" --format '{{.Id}}')" == "$2" ]] || { echo "Image mismatch: $1" >&2; exit 1; }; }
check_pkg() {
  expect_sha "$pkg/package-manifest.json" b3e22868171bf2eb6a25eec4f93fd40ebc31ac74742fef49738ea97e646b695e
  python3 - "$pkg" <<'PY'
import hashlib,json,sys
from pathlib import Path
p=Path(sys.argv[1]);m=json.loads((p/'package-manifest.json').read_text())
assert all(hashlib.sha256((p/name).read_bytes()).hexdigest()==digest for name,digest in m['file_sha256'].items())
assert m['candidate_pipeline']=='v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c'
PY
  expect_image "$candidate" "$candidate_id"
}
config_pipeline() {
  docker exec "$db" psql -U postgres -d postgres -AtX -v ON_ERROR_STOP=1 -c "begin read only; select pipeline from public.wm_processing_config where space_id='$space'; rollback;" | sed -n '2p'
}
preflight() {
  check_pkg
  expect_image dashboard-memory:hetzner-final-20261003 "$base_id"
  [[ "$(docker inspect "$container" --format '{{.Image}}')" == "$base_id" ]] || { echo 'Live runtime changed' >&2; exit 1; }
  expect_sha "$runtime/build-manifest.json" 8d144ca32cc35f14d64b58f0f2a1faa3530790b67305de8b8fee39ffe7f084f6
  expect_sha "$runtime/canonical_worker.py" 07d4b2720a6ab9d5b1a63c78699b0878e70e6d103c154c3a9ac84508c8c4fe8a
  expect_sha "$runtime/restore_schema.py" 11664c0219a0d9b2224fc1f213c3c3c425653ac78fac8f40b8125da9fa6d8174
  expect_sha "$compose" f3db31d6b899ad7d5fe000646bd328304dedf5fb7d5c0bd33ab7ccb3069297e5
  expect_sha "$dockerfile" 70ae3cd41777fbe4ade2495413ee303fb93b620deebae80f389686ff30138d9c
  expect_sha "$backup" 58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9
  [[ ! -e "$runtime/schema/20261005133858_archive_verified_image_placeholder_job.sql" ]] || { echo "Host schema already changed" >&2; exit 1; }
  python3 - "$runtime/schema" "$pkg/package-manifest.json" <<'PYCODE'
import hashlib,json,sys
from pathlib import Path
folder=Path(sys.argv[1]);m=json.loads(Path(sys.argv[2]).read_text())
for name,digest in m['file_sha256'].items():
    if name.startswith('schema/') and name!='schema/20261005133858_archive_verified_image_placeholder_job.sql':
        path=folder/Path(name).name
        assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==digest, name
PYCODE
  expect_sha "$edge" 35f0f8dcb96e495eff47eac670e75891570b059b0f43258d43dcdf5c899bf7e8
  [[ "$(config_pipeline)" == "$old_pipeline" ]] || { echo 'Live config changed' >&2; exit 1; }
  echo 'Pinned target preflight passed; intake drain and current inventory require independent positive receipt.'
}
require_drain() {
  local validator=/root/dashboard-intake-transition-prep-20261005.py
  local validator_sha=703e216b264e27d66cb0b144930e9883da5c4e1e3b80038813c6dc40c2a17a99
  local receipt=${DASHBOARD_INTAKE_DRAIN_RECEIPT:-}
  local run_dir verdict
  [[ "$receipt" == /* && "${receipt##*/}" == drain-receipt.json && -f "$receipt" && -n "${DASHBOARD_INTAKE_DRAIN_SHA256:-}" ]] || { echo 'Exact intake drain receipt required' >&2; exit 1; }
  run_dir=${receipt%/*}
  [[ "$run_dir" == "$(realpath "$run_dir")" && "$receipt" == "$run_dir/drain-receipt.json" ]] || { echo 'Intake receipt path changed' >&2; exit 1; }
  expect_sha "$validator" "$validator_sha"
  expect_sha "$receipt" "$DASHBOARD_INTAKE_DRAIN_SHA256"
  verdict=$(python3 "$validator" validate --run-dir "$run_dir" --receipt "$receipt") || { echo 'Live intake drain validation failed' >&2; exit 1; }
  python3 - "$verdict" "$run_dir" <<'PY'
import json,sys
value=json.loads(sys.argv[1])
if value != {'result':'DRAIN_VALID_NOW','run_dir':sys.argv[2]}:
    raise SystemExit('Unexpected intake validator result')
PY
}
case "$mode" in
  preflight) preflight ;;
  deploy)
    preflight;require_drain
    [[ ! -e "$stage/live-gateway-before.ts" && ! -e "$stage/live-build-manifest-before.json" && ! -e "$stage/live-compose-before.yaml" ]] || { echo 'Existing release attempt; reconcile it first' >&2; exit 1; }
    cp -p "$edge" "$stage/live-gateway-before.ts"
    cp -p "$runtime/build-manifest.json" "$stage/live-build-manifest-before.json"
    cp -p "$runtime/canonical_worker.py" "$stage/live-canonical-worker-before.py"
    cp -p "$runtime/restore_schema.py" "$stage/live-restore-schema-before.py"
    cp -p "$compose" "$stage/live-compose-before.yaml"
    cp -p "$dockerfile" "$stage/live-Dockerfile-before"
    cp -p "$backup" "$stage/live-scheduled-backup-before.py"
    expect_sha "$stage/live-gateway-before.ts" 35f0f8dcb96e495eff47eac670e75891570b059b0f43258d43dcdf5c899bf7e8
    expect_sha "$stage/live-build-manifest-before.json" 8d144ca32cc35f14d64b58f0f2a1faa3530790b67305de8b8fee39ffe7f084f6
    expect_sha "$stage/live-canonical-worker-before.py" 07d4b2720a6ab9d5b1a63c78699b0878e70e6d103c154c3a9ac84508c8c4fe8a
    expect_sha "$stage/live-restore-schema-before.py" 11664c0219a0d9b2224fc1f213c3c3c425653ac78fac8f40b8125da9fa6d8174
    expect_sha "$stage/live-compose-before.yaml" f3db31d6b899ad7d5fe000646bd328304dedf5fb7d5c0bd33ab7ccb3069297e5
    expect_sha "$stage/live-Dockerfile-before" 70ae3cd41777fbe4ade2495413ee303fb93b620deebae80f389686ff30138d9c
    expect_sha "$stage/live-scheduled-backup-before.py" 58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9
    expect_sha "$pkg/migration.sql" 22ac14542d1f2ec8a025e831b5f8c7f4fb23de7ea1dbf3a19a726e6ed99a5f5d
    docker exec -i "$db" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f - < "$pkg/migration.sql"
    docker exec "$db" psql -U postgres -d postgres -AtX -v ON_ERROR_STOP=1 -c "select has_function_privilege('service_role','public.wm_archive_image_placeholder_job(uuid,text,uuid,text)','EXECUTE'),has_function_privilege('anon','public.wm_archive_image_placeholder_job(uuid,text,uuid,text)','EXECUTE'),has_function_privilege('authenticated','public.wm_archive_image_placeholder_job(uuid,text,uuid,text)','EXECUTE');" | grep -qx 't|f|f'
    expect_sha "$pkg/gateway-handler.ts" 7607e565e4e92040cf2567e2775439bd5c146115b3cf125db1b3c269d9a2b52b
    cp "$pkg/gateway-handler.ts" "$edge.candidate.tmp"
    chmod 644 "$edge.candidate.tmp";mv "$edge.candidate.tmp" "$edge"
    docker restart dashboard-supabase-20261003-functions-1 >/dev/null
    for _ in $(seq 1 24);do [[ "$(docker inspect dashboard-supabase-20261003-functions-1 --format '{{.State.Health.Status}}')" == healthy ]] && break;sleep 5;done
    [[ "$(docker inspect dashboard-supabase-20261003-functions-1 --format '{{.State.Health.Status}}')" == healthy ]] || { echo "Gateway unhealthy; no worker/cutover" >&2; exit 1; }
    expect_sha "$edge" 7607e565e4e92040cf2567e2775439bd5c146115b3cf125db1b3c269d9a2b52b
    for name in canonical_worker.py restore_schema.py scheduled_backup.py Dockerfile; do
      cp "$pkg/$name" "$runtime/$name.candidate.tmp";chmod 644 "$runtime/$name.candidate.tmp";mv "$runtime/$name.candidate.tmp" "$runtime/$name"
    done
    cp "$pkg/schema/20261005133858_archive_verified_image_placeholder_job.sql" "$runtime/schema/20261005133858_archive_verified_image_placeholder_job.sql"
    chmod 644 "$runtime/schema/20261005133858_archive_verified_image_placeholder_job.sql"
    expect_sha "$runtime/canonical_worker.py" 4e5e9e28362e1a7f6a1a63311428de4e027f7e4e149d189c185e0cb725159acf
    expect_sha "$runtime/restore_schema.py" 5963514dca18c8bcf2f3fc28560063fe4030021251bc43ed44cdf376991838c1
    expect_sha "$backup" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["scheduled_backup.py"])' "$pkg/build-manifest.json")"
    expect_sha "$dockerfile" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["Dockerfile"])' "$pkg/build-manifest.json")"
    expect_sha "$runtime/schema/20261005133858_archive_verified_image_placeholder_job.sql" 22ac14542d1f2ec8a025e831b5f8c7f4fb23de7ea1dbf3a19a726e6ed99a5f5d
    cp "$pkg/build-manifest.json" "$runtime/build-manifest.candidate.tmp"
    chmod 644 "$runtime/build-manifest.candidate.tmp";mv "$runtime/build-manifest.candidate.tmp" "$runtime/build-manifest.json"
    expect_sha "$runtime/build-manifest.json" bbb1bda7b73b7dc9f885129c6fec83cdd6b23435ecf493c20dd86f39e254d85c
    python3 - "$compose" "$candidate" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1]);old='image: dashboard-memory:hetzner-final-20261003'
body=path.read_text()
assert body.count(old)==1
Path(str(path)+'.candidate.tmp').write_text(body.replace(old,'image: '+sys.argv[2]))
PY
    chmod 644 "$compose.candidate.tmp";mv "$compose.candidate.tmp" "$compose"
    docker compose --project-directory "$runtime" -f "$compose" up -d --no-build --no-deps canonical-draft
    for _ in $(seq 1 36);do
      if [[ "$(docker inspect "$container" --format '{{.Image}}')" == "$candidate_id" && "$(docker inspect "$container" --format '{{.State.Health.Status}}')" == healthy ]];then break;fi
      sleep 5
    done
    [[ "$(docker inspect "$container" --format '{{.Image}} {{.State.Health.Status}}')" == "$candidate_id healthy" ]] || { echo 'Candidate worker not healthy; no queue cutover' >&2; exit 1; }
    [[ "$(docker exec "$container" python -c 'from canonical_worker import pipeline_version;print(pipeline_version("gpt-5.6-terra"))')" == "$new_pipeline" ]] || { echo 'Candidate runtime identity mismatch' >&2; exit 1; }
    echo 'Candidate runtime healthy; queue/config unchanged. Reconfirm intake drain and inventory before cutover.' ;;
  cutover)
    check_pkg;require_drain
    [[ "$(docker inspect "$container" --format '{{.Image}} {{.State.Health.Status}}')" == "$candidate_id healthy" ]] || { echo 'Candidate worker not healthy' >&2; exit 1; }
    [[ "$(config_pipeline)" == "$old_pipeline" ]] || { echo 'Config no longer at pinned baseline' >&2; exit 1; }
    expect_sha "$pkg/cutover.sql" 294f6112501f20e0c66fd304822dd35e9ccbc6f7f3a2f18fb9f8f7fd84530f07
    docker exec -i "$db" psql -U postgres -d postgres -v ON_ERROR_STOP=1 -v space_id="$space" -v apply=true -f - < "$pkg/cutover.sql"
    [[ "$(config_pipeline)" == "$new_pipeline" ]] || { echo 'Cutover result unknown; inspect target before retry' >&2; exit 1; }
    echo 'Target cutover committed; reactivate only original Dashboard intake versions and verify actual user flow.' ;;
  rollback-before-cutover)
    check_pkg;require_drain
    [[ "$(config_pipeline)" == "$old_pipeline" ]] || { echo 'Cutover may have happened; no automatic rollback' >&2; exit 1; }
    expect_sha "$stage/live-gateway-before.ts" 35f0f8dcb96e495eff47eac670e75891570b059b0f43258d43dcdf5c899bf7e8
    expect_sha "$stage/live-build-manifest-before.json" 8d144ca32cc35f14d64b58f0f2a1faa3530790b67305de8b8fee39ffe7f084f6
    expect_sha "$stage/live-canonical-worker-before.py" 07d4b2720a6ab9d5b1a63c78699b0878e70e6d103c154c3a9ac84508c8c4fe8a
    expect_sha "$stage/live-restore-schema-before.py" 11664c0219a0d9b2224fc1f213c3c3c425653ac78fac8f40b8125da9fa6d8174
    expect_sha "$stage/live-compose-before.yaml" f3db31d6b899ad7d5fe000646bd328304dedf5fb7d5c0bd33ab7ccb3069297e5
    expect_sha "$stage/live-Dockerfile-before" 70ae3cd41777fbe4ade2495413ee303fb93b620deebae80f389686ff30138d9c
    expect_sha "$stage/live-scheduled-backup-before.py" 58048432e2efb34dc6ede449fc86fc3ce9e3ecbb7d17816d8f512de9b5cb0ea9
    cp "$stage/live-gateway-before.ts" "$edge.rollback.tmp";chmod 644 "$edge.rollback.tmp";mv "$edge.rollback.tmp" "$edge"
    docker restart dashboard-supabase-20261003-functions-1 >/dev/null
    cp "$stage/live-canonical-worker-before.py" "$runtime/canonical_worker.py.rollback.tmp";chmod 644 "$runtime/canonical_worker.py.rollback.tmp";mv "$runtime/canonical_worker.py.rollback.tmp" "$runtime/canonical_worker.py"
    cp "$stage/live-restore-schema-before.py" "$runtime/restore_schema.py.rollback.tmp";chmod 644 "$runtime/restore_schema.py.rollback.tmp";mv "$runtime/restore_schema.py.rollback.tmp" "$runtime/restore_schema.py"
    cp "$stage/live-scheduled-backup-before.py" "$backup.rollback.tmp";chmod 644 "$backup.rollback.tmp";mv "$backup.rollback.tmp" "$backup"
    cp "$stage/live-Dockerfile-before" "$dockerfile.rollback.tmp";chmod 644 "$dockerfile.rollback.tmp";mv "$dockerfile.rollback.tmp" "$dockerfile"
    rm "$runtime/schema/20261005133858_archive_verified_image_placeholder_job.sql"
    cp "$stage/live-build-manifest-before.json" "$runtime/build-manifest.rollback.tmp";chmod 644 "$runtime/build-manifest.rollback.tmp";mv "$runtime/build-manifest.rollback.tmp" "$runtime/build-manifest.json"
    cp "$stage/live-compose-before.yaml" "$compose.rollback.tmp";chmod 644 "$compose.rollback.tmp";mv "$compose.rollback.tmp" "$compose"
    docker compose --project-directory "$runtime" -f "$compose" up -d --no-build --no-deps canonical-draft
    [[ "$(docker inspect "$container" --format '{{.Image}}')" == "$base_id" ]] || { echo 'Base runtime restore unconfirmed' >&2; exit 1; }
    echo 'Pre-cutover runtime restored; verify health and original Dashboard intake activation.' ;;
  *) echo 'Usage: preflight|deploy|cutover|rollback-before-cutover' >&2;exit 2;;
esac
