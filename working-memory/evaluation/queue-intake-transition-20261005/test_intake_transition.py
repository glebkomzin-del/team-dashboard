import copy
import datetime as dt
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("intake_transition", Path(__file__).with_name("intake_transition.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture():
    now = dt.datetime.now(dt.timezone.utc)
    at = lambda seconds: (now + dt.timedelta(seconds=seconds)).isoformat()
    versions = {m.INTAKE: "original-intake", "dashboardDriveMove": "original-move", "dashboardDriveWatch": "original-watch"}
    workflows = {w: {"id": w, "active": True, "versionId": v, "activeVersionId": v, "nodes_sha256": "a" * 64} for w, v in versions.items()}
    common = {"host": "target-host", "callers": {m.INTAKE: True, "hybridIntakeValidation20260908": False},
              "workflows": workflows, "executions": [{"id": 8, "status": "running", "stoppedAt": None}],
              "backend_established_sockets": 1, "archive_jobs": {"archive": 396, "jobs": 168}}
    before = copy.deepcopy(common); before["at_utc"] = at(-30)
    paused = copy.deepcopy(common); paused["at_utc"] = at(-20)
    paused["callers"][m.INTAKE] = False
    paused["workflows"][m.INTAKE]["active"] = False
    paused["workflows"][m.INTAKE]["activeVersionId"] = None
    first = copy.deepcopy(paused); first["at_utc"] = at(-15)
    first["executions"][0].update(status="success", stoppedAt=at(-16))
    first["backend_established_sockets"] = 0
    last = copy.deepcopy(first); last["at_utc"] = at(-9)
    current = copy.deepcopy(last); current["at_utc"] = at(-1)
    receipt = {"schema": 1, "problem_id": m.PROBLEM, "decision": "POSITIVE_DRAIN", "selected": [m.INTAKE],
               "host": before["host"], "created_at_utc": at(-8), "run_dir": "/root/dashboard-intake-transition-fixture",
               "evidence_paths": {name: "/root/dashboard-intake-transition-fixture/" + name + ".json" for name in ("before", "paused", "first", "last")},
               "original_versions": versions,
               "initial_inflight_ids": [8], "archive_jobs_before": before["archive_jobs"],
               "archive_jobs_at_drain": last["archive_jobs"],
               "evidence_sha256": {name: m.sha(m.canonical(value) + b"\n") for name, value in
                                   (("before", before), ("paused", paused), ("first", first), ("last", last))}}
    return receipt, before, paused, first, last, current


class Contract(unittest.TestCase):
    def check(self, values):
        m.receipt_ok(*values)

    def test_positive_known_inflight_completed_no_new_start(self):
        self.check(fixture())

    def test_missing_unknown_or_foreign_evidence_denied(self):
        for change in (
            lambda x: x[0].pop("initial_inflight_ids"),
            lambda x: x[0].update(decision="UNKNOWN"),
            lambda x: x[0].update(selected=["dashboardDriveMove"]),
            lambda x: x[0]["evidence_sha256"].update(first="0" * 64),
            lambda x: x[5]["callers"].update({"foreign": True}),
        ):
            values = list(fixture()); change(values)
            with self.assertRaises((AssertionError, KeyError)):
                self.check(values)

    def test_stale_request_and_original_version_change_denied(self):
        for change in (
            lambda x: x[0].update(created_at_utc="2026-09-01T00:00:00+00:00"),
            lambda x: x[5]["executions"].append({"id": 9, "status": "success", "stoppedAt": "now"}),
            lambda x: x[5]["executions"][0].update(status="running", stoppedAt=None),
            lambda x: x[5]["workflows"][m.INTAKE].update(activeVersionId="foreign"),
            lambda x: x[5].update(backend_established_sockets=1),
            lambda x: x[5]["callers"].update({m.INTAKE: True}),
            lambda x: x[5]["workflows"]["dashboardDriveMove"].update(active=False),
            lambda x: x[5]["workflows"]["dashboardDriveWatch"].update(active=False),
        ):
            values = list(fixture()); change(values)
            with self.assertRaises(AssertionError):
                self.check(values)

    def test_new_start_between_pause_and_first_sample_denied(self):
        values = list(fixture())
        values[3]["executions"].append({"id": 9, "status": "success", "stoppedAt": "now"})
        values[4]["executions"].append({"id": 9, "status": "success", "stoppedAt": "now"})
        values[0]["evidence_sha256"]["first"] = m.sha(m.canonical(values[3]) + b"\n")
        values[0]["evidence_sha256"]["last"] = m.sha(m.canonical(values[4]) + b"\n")
        with self.assertRaises(AssertionError):
            self.check(values)

    def test_caller_reactivated_between_workflow_and_caller_read_denied(self):
        values = list(fixture())
        values[4]["callers"][m.INTAKE] = True
        values[0]["evidence_sha256"]["last"] = m.sha(m.canonical(values[4]) + b"\n")
        with self.assertRaises(AssertionError):
            self.check(values)


if __name__ == "__main__":
    unittest.main()
