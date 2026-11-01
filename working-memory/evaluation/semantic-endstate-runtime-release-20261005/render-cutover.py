#!/usr/bin/env python3
"""Render the reviewed cutover template from one exact, fresh inventory receipt.

Rendering is private preparation. The SQL itself defaults to ROLLBACK; only the
Lead-approved host command may pass psql -v apply=true after renewed drain.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

OLD = "v11:compact1:gate1:gpt-5.6-terra:3086726206f9074d:canonical1:7c67663689250e1c"
SPACE = "96a2dc44-9b9e-4644-b236-c5c1956cd39d"
SEMANTIC_MANIFEST_SHA = "51e47b25aaba098d4f0ae991b69879739ffe40e29a548c037571c1ad7e2a5cc5"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def render(snapshot, expected_sha, package_manifest, template, output):
    data = snapshot.read_bytes()
    if sha(data) != expected_sha:
        raise ValueError("inventory SHA mismatch")
    p = json.loads(data)
    m = json.loads(package_manifest.read_text())
    if m["semantic_manifest_sha256"] != SEMANTIC_MANIFEST_SHA:
        raise ValueError("semantic source manifest changed")
    if m.get("release_gate") != "ACCEPTED_INDEPENDENT_REVIEW_AND_LEAD_CLEAR":
        raise ValueError("semantic release gate is not accepted")
    pipeline = m["candidate_pipeline_source_calculated"]
    if not re.fullmatch(r"v11:compact1:gate1:gpt-5\.6-terra:[0-9a-f]{16}:canonical1:[0-9a-f]{16}", pipeline) or pipeline == OLD:
        raise ValueError("invalid candidate pipeline")
    if p.get("schema_version") != 1 or p.get("space_id") != SPACE or p.get("pipeline") != OLD:
        raise ValueError("wrong target or source pipeline")
    if p.get("enabled") is not False or p.get("queue_all_unstarted") is not True or p.get("running_count") != 0:
        raise ValueError("not a disabled and fully unstarted queue")
    if not p.get("owner_id") or p.get("space_state") == "retired" or not isinstance(p.get("revision"), int):
        raise ValueError("invalid space state")
    for key in ("job_hash", "call_hash"):
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
    args = parser.parse_args()
    print(json.dumps(render(args.snapshot, args.snapshot_sha256, args.package_manifest, args.template, args.out), sort_keys=True))
