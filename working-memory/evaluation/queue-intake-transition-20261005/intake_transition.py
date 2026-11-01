#!/usr/bin/env python3
"""Target-host n8n intake transition. Preparation is read-only; writes require --execute."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.request

PROBLEM = "DASHBOARD-PROD-20261005-INTAKE-TRANSITION"
INTAKE = "nzyaKxs5Om9wuPEc"
RELATED = (INTAKE, "dashboardDriveMove", "dashboardDriveWatch")
ROUTE = "/dashboard-memory/drive-sources"
KEY_FILE = Path("/opt/dashboard-supabase-20261003/n8n-pause-access-1/existing-api-key-private.json")
API = "http://127.0.0.1:5678/api/v1"
SPACE = "96a2dc44-9b9e-4644-b236-c5c1956cd39d"
REQUIRED_SCOPES = {"workflow:list", "workflow:read", "workflow:activate", "workflow:deactivate"}
TERMINAL = {"success", "error", "canceled", "crashed"}


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def save(path, value):
    path = Path(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(canonical(value) + b"\n")
        out.flush()
        os.fsync(out.fileno())


def load(path):
    return json.loads(Path(path).read_bytes())


def sql(container, user, db, query):
    cmd = ["docker", "exec", container, "psql", "-U", user, "-d", db,
           "-XqAt", "-v", "ON_ERROR_STOP=1", "-c", query]
    return subprocess.check_output(cmd, timeout=20).decode().strip()


def api(path, method="GET", data=None):
    key = load(KEY_FILE)["apiKey"]
    req = urllib.request.Request(API + path, method=method,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
        data=canonical(data) if data is not None else None)
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def workflow(workflow_id):
    value = api("/workflows/" + workflow_id)
    return {"id": value["id"], "active": value["active"],
            "activeVersionId": value.get("activeVersionId"),
            "versionId": value.get("versionId"),
            "nodes_sha256": sha(canonical(value.get("nodes")))}


def callers():
    found = {}
    cursor = None
    seen = set()
    while True:
        suffix = "/workflows?limit=250" + ("&cursor=" + cursor if cursor else "")
        page = api(suffix)
        for item in page["data"]:
            full = api("/workflows/" + item["id"])
            if ROUTE in json.dumps(full.get("nodes", []), ensure_ascii=False):
                found[item["id"]] = bool(full["active"])
        cursor = page.get("nextCursor")
        if not cursor:
            break
        if cursor in seen:
            raise ValueError("n8n pagination repeated")
        seen.add(cursor)
    return found


def scopes():
    value = sql("n8n_postgres", "n8n", "n8n",
        "SELECT json_agg(scopes)::text FROM user_api_keys")
    keys = json.loads(value)
    if not isinstance(keys, list) or len(keys) != 1:
        raise ValueError("Expected exactly one existing n8n API key")
    return set(keys[0])


def executions():
    rows = sql("n8n_postgres", "n8n", "n8n",
        "SELECT coalesce(json_agg(json_build_object('id',id,'status',status,'stoppedAt',\"stoppedAt\") ORDER BY id),'[]'::json)::text "
        "FROM execution_entity WHERE \"workflowId\"='" + INTAKE + "'")
    return json.loads(rows)


def sockets_8798():
    output = subprocess.check_output(["ss", "-Htn", "state", "established"], timeout=10).decode()
    return sum(":8798" in line for line in output.splitlines())


def archive_jobs():
    q = ("SELECT json_build_object('archive',"
         "(SELECT count(*) FROM public.wm_archive_documents WHERE space_id='" + SPACE + "'),"
         "'jobs',(SELECT count(*) FROM public.wm_jobs WHERE space_id='" + SPACE + "'))::text")
    return json.loads(sql("dashboard-supabase-20261003-db-1", "postgres", "postgres", q))


def observe():
    return {"at_utc": utcnow(), "host": socket.gethostname(),
            "workflows": {w: workflow(w) for w in RELATED},
            "callers": callers(), "executions": executions(),
            "backend_established_sockets": sockets_8798(),
            "archive_jobs": archive_jobs()}


def baseline_ok(snapshot, need_scopes=True):
    assert [w for w, active in snapshot["callers"].items() if active] == [INTAKE], "Active caller inventory changed or unknown"
    assert set(snapshot["callers"]) == {INTAKE, "hybridIntakeValidation20260908"}, "Unknown caller inventory"
    for w in RELATED:
        value = snapshot["workflows"][w]
        assert value["active"] is True, "Original workflow is not active"
        assert value["activeVersionId"] and value["activeVersionId"] == value["versionId"], "Unpublished draft/version"
    if need_scopes:
        assert REQUIRED_SCOPES <= scopes(), "Existing API key lacks lifecycle scopes"


def recent(snapshot, seconds=180):
    age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(snapshot["at_utc"])
    assert dt.timedelta(0) <= age <= dt.timedelta(seconds=seconds), "Preflight stale"


def same_versions(before, now):
    assert set(before["callers"]) == set(now["callers"]) == {INTAKE, "hybridIntakeValidation20260908"}
    assert now["callers"]["hybridIntakeValidation20260908"] is False
    for w in RELATED:
        a, b = before["workflows"][w], now["workflows"][w]
        assert a["versionId"] == b["versionId"]
        assert a["nodes_sha256"] == b["nodes_sha256"]
        if b["active"]:
            assert b["activeVersionId"] == a["activeVersionId"]
        else:
            assert b["activeVersionId"] in (None, a["activeVersionId"])


def drain_ok(before, paused, first, last):
    same_versions(before, paused)
    same_versions(before, first)
    same_versions(before, last)
    assert paused["workflows"][INTAKE]["active"] is False
    assert paused["callers"][INTAKE] is False
    assert first["workflows"][INTAKE]["active"] is False
    assert last["workflows"][INTAKE]["active"] is False
    assert first["callers"][INTAKE] is False and last["callers"][INTAKE] is False
    for w in RELATED[1:]:
        assert paused["workflows"][w]["active"] is True
        assert first["workflows"][w]["active"] is True
        assert last["workflows"][w]["active"] is True
    initial = {e["id"] for state in (before, paused) for e in state["executions"] if e["status"] not in TERMINAL}
    for current in (first, last):
        by_id = {e["id"]: e for e in current["executions"]}
        assert initial <= by_id.keys(), "Known in-flight execution disappeared"
        assert all(by_id[i]["status"] in TERMINAL and by_id[i]["stoppedAt"] for i in initial), "Known in-flight not completed"
        assert all(e["status"] in TERMINAL for e in current["executions"]), "Current execution still in flight"
        assert current["backend_established_sockets"] == 0, "Backend HTTP still established"
    paused_ids = {e["id"] for e in paused["executions"]}
    assert paused_ids == {e["id"] for e in first["executions"]} == {e["id"] for e in last["executions"]}, "New start or missing execution after pause"
    assert dt.datetime.fromisoformat(last["at_utc"]) - dt.datetime.fromisoformat(first["at_utc"]) >= dt.timedelta(seconds=5)


def receipt_ok(receipt, before, paused, first, last, current, max_age=600):
    assert receipt["schema"] == 1 and receipt["problem_id"] == PROBLEM
    assert receipt["decision"] == "POSITIVE_DRAIN" and receipt["selected"] == [INTAKE]
    assert receipt["run_dir"].startswith("/root/dashboard-intake-transition-")
    assert receipt["original_versions"] == {w: before["workflows"][w]["activeVersionId"] for w in RELATED}
    assert set(receipt["initial_inflight_ids"]) == {e["id"] for state in (before, paused) for e in state["executions"] if e["status"] not in TERMINAL}
    assert receipt["archive_jobs_before"] == before["archive_jobs"]
    assert receipt["archive_jobs_at_drain"] == last["archive_jobs"]
    for name, value in (("before", before), ("paused", paused), ("first", first), ("last", last)):
        assert receipt["evidence_paths"][name] == receipt["run_dir"] + "/" + name + ".json"
        assert receipt["evidence_sha256"][name] == sha(canonical(value) + b"\n")
    assert receipt["host"] == current["host"] == before["host"]
    times = [dt.datetime.fromisoformat(x["at_utc"]) for x in (before, paused, first, last)]
    created = dt.datetime.fromisoformat(receipt["created_at_utc"])
    assert times == sorted(times) and times[-1] <= created
    age = dt.datetime.now(dt.timezone.utc) - created
    assert dt.timedelta(0) <= age <= dt.timedelta(seconds=max_age)
    drain_ok(before, paused, first, last)
    same_versions(before, current)
    assert current["workflows"][INTAKE]["active"] is False
    assert current["callers"][INTAKE] is False
    assert all(current["workflows"][w]["active"] is True for w in RELATED[1:])
    assert all(e["status"] in TERMINAL for e in current["executions"])
    assert {e["id"] for e in current["executions"]} == {e["id"] for e in last["executions"]}
    assert current["backend_established_sockets"] == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("preflight", "preflight-ui", "pause", "capture-ui-pause", "drain", "validate", "resume", "capture-ui-resume"))
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--receipt")
    args = parser.parse_args()
    os.umask(0o077)
    raw_run = Path(args.run_dir)
    assert not raw_run.is_symlink()
    run = raw_run.resolve()
    assert run.parent == Path("/root") and run.name.startswith("dashboard-intake-transition-")
    run.mkdir(mode=0o700, exist_ok=True)
    assert not (run.stat().st_mode & 0o077), "Run directory must be private"
    if args.receipt:
        assert Path(args.receipt).resolve() == run / "drain-receipt.json"
    try:
        if args.action in ("preflight", "preflight-ui"):
            snapshot = observe()
            snapshot["scopes_ok"] = REQUIRED_SCOPES <= scopes()
            save(run / "before.json", snapshot)
            baseline_ok(snapshot, need_scopes=args.action == "preflight")
            result = "PREFLIGHT_API_PASSED" if args.action == "preflight" else "PREFLIGHT_UI_CAPTURE_READY"
        elif args.action == "capture-ui-pause":
            before = load(run / "before.json")
            baseline_ok(before, need_scopes=False)
            recent(before)
            paused = observe()
            same_versions(before, paused)
            assert paused["workflows"][INTAKE]["active"] is False
            assert all(paused["workflows"][w]["active"] for w in RELATED[1:])
            save(run / "paused.json", paused)
            result = "UI_PAUSE_OBSERVED_NEEDS_DRAIN"
        elif args.action == "pause":
            assert args.execute, "Production mutation requires --execute"
            before = load(run / "before.json")
            baseline_ok(before)
            recent(before)
            same_versions(before, observe())
            save(run / "pause-attempt.json", {"at_utc": utcnow(), "workflow": INTAKE})
            api("/workflows/" + INTAKE + "/deactivate", "POST", {})
            paused = observe()
            same_versions(before, paused)
            assert paused["workflows"][INTAKE]["active"] is False
            save(run / "paused.json", paused)
            result = "PAUSED_NEEDS_DRAIN"
        elif args.action == "drain":
            before, paused = load(run / "before.json"), load(run / "paused.json")
            first = observe()
            save(run / "first.json", first)
            time.sleep(5)
            last = observe()
            save(run / "last.json", last)
            drain_ok(before, paused, first, last)
            receipt = {"schema": 1, "problem_id": PROBLEM, "decision": "POSITIVE_DRAIN",
                       "selected": [INTAKE], "host": before["host"], "created_at_utc": utcnow(), "run_dir": str(run),
                       "original_versions": {w: before["workflows"][w]["activeVersionId"] for w in RELATED},
                       "initial_inflight_ids": sorted({e["id"] for state in (before, paused) for e in state["executions"] if e["status"] not in TERMINAL}),
                       "archive_jobs_before": before["archive_jobs"],
                       "archive_jobs_at_drain": last["archive_jobs"],
                       "evidence_paths": {name: str(run / (name + ".json")) for name in ("before", "paused", "first", "last")},
                       "evidence_sha256": {name: sha((run / (name + ".json")).read_bytes()) for name in ("before", "paused", "first", "last")}}
            save(run / "drain-receipt.json", receipt)
            result = "POSITIVE_DRAIN"
        elif args.action == "validate":
            receipt = load(args.receipt or run / "drain-receipt.json")
            assert receipt["run_dir"] == str(run)
            files = {name: load(run / (name + ".json")) for name in ("before", "paused", "first", "last")}
            receipt_ok(receipt, files["before"], files["paused"], files["first"], files["last"], observe())
            result = "DRAIN_VALID_NOW"
        elif args.action == "capture-ui-resume":
            receipt = load(args.receipt or run / "drain-receipt.json")
            assert receipt["run_dir"] == str(run)
            before = load(run / "before.json")
            evidence = {name: load(run / (name + ".json")) for name in ("before", "paused", "first", "last")}
            assert receipt["schema"] == 1 and receipt["problem_id"] == PROBLEM
            assert receipt["decision"] == "POSITIVE_DRAIN" and receipt["selected"] == [INTAKE]
            for name in evidence:
                assert receipt["evidence_paths"][name] == str(run / (name + ".json"))
                assert receipt["evidence_sha256"][name] == sha((run / (name + ".json")).read_bytes())
            drain_ok(before, evidence["paused"], evidence["first"], evidence["last"])
            restored = observe()
            same_versions(before, restored)
            assert receipt["original_versions"] == {w: before["workflows"][w]["activeVersionId"] for w in RELATED}
            assert all(restored["workflows"][w]["active"] for w in RELATED)
            save(run / "resumed.json", restored)
            result = "ORIGINAL_VERSION_RESUMED_RECONCILE_ARCHIVE_JOBS"
        else:
            assert args.execute, "Production mutation requires --execute"
            receipt = load(args.receipt or run / "drain-receipt.json")
            assert receipt["run_dir"] == str(run)
            files = {name: load(run / (name + ".json")) for name in ("before", "paused", "first", "last")}
            current = observe()
            receipt_ok(receipt, files["before"], files["paused"], files["first"], files["last"], current)
            assert REQUIRED_SCOPES <= scopes()
            save(run / "resume-attempt.json", {"at_utc": utcnow(), "workflow": INTAKE})
            api("/workflows/" + INTAKE + "/activate", "POST", {"versionId": receipt["original_versions"][INTAKE]})
            restored = observe()
            same_versions(files["before"], restored)
            assert restored["workflows"][INTAKE]["active"] is True
            save(run / "resumed.json", restored)
            result = "ORIGINAL_VERSION_RESUMED_RECONCILE_ARCHIVE_JOBS"
        print(json.dumps({"result": result, "run_dir": str(run)}))
    except Exception as exc:
        # Keep API response bodies, key material and DB output out of terminal logs.
        print(json.dumps({"result": "DENY", "reason_type": type(exc).__name__, "reason": str(exc) if isinstance(exc, AssertionError) else "Inspect private run evidence"}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
