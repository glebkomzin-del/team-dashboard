#!/usr/bin/env python3
"""Render the reviewed cutover template from one exact, fresh inventory receipt.

Rendering is private preparation. The SQL itself defaults to ROLLBACK; only the
Lead-approved host command may pass psql -v apply=true after renewed drain.
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OLD = "v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c"
SPACE = "96a2dc44-9b9e-4644-b236-c5c1956cd39d"
PACKAGE_MANIFEST_SHA = "086d32d4a65e43234cf4170cb885a1240d9b24b6386de1d66670a317f2e5d022"
CANDIDATE_IMAGE = "sha256:423501711e73203b9ea85f554f9e68f647796e53c89157eb5237fd704e7cb2a2"
DRAIN_VALIDATOR = Path("/root/dashboard-intake-transition-prep-20261005.py")
DRAIN_VALIDATOR_SHA = "703e216b264e27d66cb0b144930e9883da5c4e1e3b80038813c6dc40c2a17a99"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require_drain(receipt, expected_sha):
    if not receipt.is_absolute() or receipt.name != "drain-receipt.json" or receipt != receipt.resolve():
        raise ValueError("exact absolute intake drain receipt required")
    if sha(receipt.read_bytes()) != expected_sha or sha(DRAIN_VALIDATOR.read_bytes()) != DRAIN_VALIDATOR_SHA:
        raise ValueError("intake drain receipt or validator SHA mismatch")
    verdict = subprocess.run([sys.executable, str(DRAIN_VALIDATOR), "validate", "--run-dir", str(receipt.parent),
                              "--receipt", str(receipt)], capture_output=True, text=True, check=True)
    if json.loads(verdict.stdout) != {"result": "DRAIN_VALID_NOW", "run_dir": str(receipt.parent)}:
        raise ValueError("live intake drain is not positive")


def require_release(receipt, expected_sha, inventory_sha, drain_sha, pipeline, revision):
    if not receipt.is_absolute() or sha(receipt.read_bytes()) != expected_sha:
        raise ValueError("exact release receipt required")
    value = json.loads(receipt.read_text())
    expected = {"result": "RELEASE_ACCEPTED", "package_manifest_sha256": PACKAGE_MANIFEST_SHA,
                "candidate_image_id": CANDIDATE_IMAGE, "candidate_pipeline": pipeline,
                "inventory_sha256": inventory_sha, "drain_receipt_sha256": drain_sha,
                "space_revision": revision,
                "lead_clear": True}
    if value != expected:
        raise ValueError("release receipt does not bind this image, inventory and drain")


def require_deployed_image(pipeline):
    tag = "dashboard-memory:archive-generation-overlay-20261005-5c4c18b8"
    container = "dashboard-memory-canonical-draft-canonical-draft-1"
    image = subprocess.check_output(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True).strip()
    running = subprocess.check_output(["docker", "inspect", container, "--format",
                                       "{{.Image}} {{.State.Health.Status}}"], text=True).strip()
    actual = subprocess.check_output(["docker", "exec", container, "python3", "-c",
                                      'from canonical_worker import pipeline_version;print(pipeline_version("gpt-5.6-terra"))'], text=True).strip()
    if image != CANDIDATE_IMAGE or running != CANDIDATE_IMAGE + " healthy" or actual != pipeline:
        raise ValueError("candidate worker is not healthy at the exact image and pipeline")


def render(snapshot, expected_sha, package_manifest, template, output, release_receipt, release_sha, drain_receipt, drain_sha):
    data = snapshot.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError("inventory SHA mismatch")
    p = json.loads(data)
    if sha(package_manifest.read_bytes()) != PACKAGE_MANIFEST_SHA:
        raise ValueError("overlay package manifest changed")
    m = json.loads(package_manifest.read_text())
    if m.get("production_release_gate") != "DENY_pending_root_receipt_and_fresh_main_pause_drain_inventory":
        raise ValueError("overlay package release policy changed")
    if m.get("candidate_image_id") != CANDIDATE_IMAGE or m.get("candidate_pipeline_runtime") != m.get("candidate_pipeline_source"):
        raise ValueError("candidate image or runtime identity changed")
    pipeline = m["candidate_pipeline_runtime"]
    require_release(release_receipt, release_sha, expected_sha, drain_sha, pipeline, p["revision"])
    require_drain(drain_receipt, drain_sha)
    require_deployed_image(pipeline)
    if not re.fullmatch(r"v11:compact1:gate1:gpt-5\.6-terra:[0-9a-f]{16}:canonical1:[0-9a-f]{16}", pipeline) or pipeline == OLD:
        raise ValueError("invalid candidate pipeline")
    if p.get("schema_version") != 1 or p.get("space_id") != SPACE or p.get("pipeline") != OLD:
        raise ValueError("wrong target or source pipeline")
    if p.get("enabled") is not False or p.get("queue_all_unstarted") is not True or p.get("running_count") != 0:
        raise ValueError("not a disabled and fully unstarted queue")
    if not p.get("owner_id") or p.get("space_state") == "retired" or not isinstance(p.get("revision"), int):
        raise ValueError("invalid space state")
    for key in ("job_hash", "nonqueued_job_hash", "call_hash"):
        if not re.fullmatch(r"[0-9a-f]{64}", p.get(key, "")):
            raise ValueError(f"missing {key}")
    if not isinstance(p.get("job_count"), int) or p["job_count"] < 1 or not isinstance(p.get("call_count"), int) or p["call_count"] < 0:
        raise ValueError("invalid history counts")
    rows = p.get("queued")
    if not isinstance(rows, list) or not rows or len(rows) > p["job_count"]:
        raise ValueError("empty or impossible inventory")
    ids = []
    for row in rows:
        if set(row) != {"id", "updated_at"} or not re.fullmatch(r"[0-9a-f]{64}", row["id"]):
            raise ValueError("invalid queued row")
        datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00"))
        ids.append(row["id"])
    if ids != sorted(set(ids)):
        raise ValueError("queued IDs must be unique and sorted")
    captured = datetime.fromisoformat(p["captured_at"].replace("Z", "+00:00"))
    if captured.tzinfo is None or not 0 <= (datetime.now(timezone.utc) - captured).total_seconds() <= 300:
        raise ValueError("inventory is stale or future-dated")
    sql = template.read_text()
    if sql.count("__SNAPSHOT_HEX__") != 1 or sql.count("__NEW_PIPELINE__") != 1:
        raise ValueError("cutover template placeholders changed")
    sql = sql.replace("__SNAPSHOT_HEX__", data.hex()).replace("__NEW_PIPELINE__", pipeline)
    if output.exists():
        raise ValueError("output exists; reconcile the prior attempt")
    output.write_text(sql)
    output.chmod(0o600)
    return {"result": "CUTOVER_SQL_RENDERED_ONLY", "inventory_sha256": expected_sha,
            "sql_sha256": sha(output.read_bytes()), "queued_jobs": len(rows), "pipeline": pipeline}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--package-manifest", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--release-receipt", type=Path, required=True)
    parser.add_argument("--release-receipt-sha256", required=True)
    parser.add_argument("--drain-receipt", type=Path, required=True)
    parser.add_argument("--drain-receipt-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.snapshot, args.snapshot_sha256, args.package_manifest, args.template, args.out,
                            args.release_receipt, args.release_receipt_sha256, args.drain_receipt,
                            args.drain_receipt_sha256), sort_keys=True))
