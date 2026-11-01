"""Synthetic archive/projection integration tests; no production data."""
import copy
from datetime import date
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import io
import unittest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("projection_reminders", HERE / "reminders.py")
r = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = r
SPEC.loader.exec_module(r)


def observation(**patch):
    result = dict(kind="commitment", title="Synthetic task", claim="Synthetic claim",
                  owner="Gleb", work_state="open", matter="Synthetic topic",
                  due_text="bis Freitag", condition_text=None, update="none",
                  update_target=None, required_review=False, action_uncertainty=None,
                  commitment_strength="explicit")
    result.update(patch)
    return result


def source(revision=1, observations=None, when="2026-10-01"):
    result = dict(kind="source", revision=revision,
                  source=dict(id=str(revision), source_id=str(revision), content_hash="synthetic",
                              event_date=when, title="Synthetic source", transcript="Synthetic content",
                              observed_at=when + "T00:00:00Z"),
                  payload=dict(pipeline="synthetic", proposal={"observations": observations or [observation()]},
                               human_guard="field-v1"))
    return result


def human(revision, action, target, patch, when="2026-10-02"):
    return dict(kind="human", revision=revision, command_id=str(revision), actor_id="synthetic",
                payload=dict(action=action, target_id=target, patch=patch, event_date=when))


class ProjectionTests(unittest.TestCase):
    def test_source_creation_and_envelope(self):
        src = source()
        envelope = {"kind": "source", "sequence": 1, "record_json": json.dumps(src)}
        task = r.reconstruct_tasks([envelope])[0]
        self.assertEqual((task["status"], task["first_changed"], task["last_changed"]),
                         ("open", "2026-10-01", "2026-10-01"))
        self.assertEqual(task["due_reference_date"], "2026-10-01")
        self.assertEqual(task["source_title"], "Synthetic source")

    def test_generation_replaces_observations_not_only_task_diff(self):
        src = source()
        logical = r.expand_journal([src])
        replacement = observation(title="Changed synthetic", owner="Other", work_state="waiting")
        generation = {"kind": "generation", "revision": 2, "payload": {"entries": [
            {"ref": r._hash(logical[0]), "changes": [
                {"path": ["payload", "proposal", "observations", 0], "value": replacement}]}]}}
        before = copy.deepcopy([src, generation])
        tasks = r.reconstruct_tasks([src, generation])
        self.assertEqual((tasks[0]["title"], tasks[0]["owner"], tasks[0]["status"]),
                         ("Changed synthetic", "Other", "waiting"))
        self.assertEqual([src, generation], before)

    def test_generation_deletes_source_and_adds_new(self):
        old, new = source(), source(2)
        generation = {"kind": "generation", "revision": 3,
                      "payload": {"entries": [{"new": r._logical(new)}]}}
        tasks = r.reconstruct_tasks([old, generation])
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["source_id"], "2")

    def test_unknown_generation_reference_fails(self):
        generation = {"kind": "generation", "revision": 2,
                      "payload": {"entries": [{"ref": "unknown", "changes": []}]}}
        with self.assertRaises(ValueError):
            r.reconstruct_tasks([source(), generation])

    def test_progress_preserves_nullable_owner_deadline_condition(self):
        start = source(observations=[observation(work_state="waiting", condition_text="Synthetic dependency")])
        tid = r.reconstruct_tasks([start])[0]["id"]
        update = source(2, [observation(kind="status", owner=None, due_text=None, condition_text=None,
                                       update="progress", update_target=tid, work_state="waiting")], "2026-10-06")
        task = r.reconstruct_tasks([start, update])[0]
        self.assertEqual(task["owner"], "Gleb")
        self.assertEqual(task["due_text"], "bis Freitag")
        self.assertEqual(task["due_reference_date"], "2026-10-01")
        self.assertEqual(task["condition_text"], "Synthetic dependency")
        self.assertEqual(task["last_changed"], "2026-10-06")

    def test_lifecycle_done_reopen_condition_met(self):
        start = source(observations=[observation(work_state="waiting", condition_text="Synthetic dependency")])
        tid = r.reconstruct_tasks([start])[0]["id"]
        rows = [start]
        for revision, action, expected in [(2, "done", "done"), (3, "reopened", "waiting"), (4, "condition_met", "open")]:
            rows.append(source(revision, [observation(kind="status", update=action, update_target=tid, work_state="waiting")], f"2026-10-0{revision}"))
            task = r.reconstruct_tasks(rows)[0]
            self.assertEqual(task["status"], expected)
        self.assertIsNone(task["condition_text"])

    def test_review_uncertainty_anonymous_and_work_gate_prevent_creation(self):
        for patch in ({"required_review": True}, {"action_uncertainty": "unknown"},
                      {"owner": "Speaker 1"}, {"work_gate": {"verdict": "unsupported"}},
                      {"kind": "fact"}, {"commitment_strength": "none"}):
            with self.subTest(patch=patch):
                self.assertEqual(r.reconstruct_tasks([source(observations=[observation(**patch)])]), [])

    def test_human_approval_and_abort(self):
        start = source(observations=[observation(required_review=True)])
        oid = r._hash({})  # Identity formula is explicitly independent of field content.
        import hashlib
        job = hashlib.sha256(b"1:synthetic").hexdigest()
        oid = hashlib.sha256((job + ":observation:0").encode()).hexdigest()
        approval = human(2, "approve", oid, {})
        task = r.reconstruct_tasks([start, approval])[0]
        self.assertEqual(task["first_changed"], "2026-10-01")
        self.assertEqual(task["last_changed"], "2026-10-02")
        abort = human(3, "set_status", oid, {"status": "cancelled"}, "2026-10-03")
        self.assertEqual(r.reconstruct_tasks([start, approval, abort])[0]["status"], "aborted")

    def test_planning_and_guard_preserve_explicit_owner(self):
        create = human(1, "create_task", "manual", {"owner": "Gleb", "title": "Synthetic manual", "due_date": "2026-10-16"})
        update = source(2, [observation(update="owner_changed", update_target="manual", owner="Other")], "2026-10-03")
        task = r.reconstruct_tasks([create, update])[0]
        self.assertEqual(task["owner"], "Gleb")
        self.assertIsNone(task["due_reference_date"])
        self.assertEqual(task["due_text"], "2026-10-16")

    def test_knowledge_correction_never_creates_work(self):
        import hashlib
        start = source(observations=[observation(kind="fact", owner=None)])
        job = hashlib.sha256(b"1:synthetic").hexdigest()
        oid = hashlib.sha256((job + ":observation:0").encode()).hexdigest()
        correction = human(2, "correct_confirm", oid, {"claim": "Corrected synthetic fact"})
        self.assertEqual(r.reconstruct_tasks([start, correction]), [])

    def test_progress_preserves_human_corrected_claim(self):
        start = source()
        tid = r.reconstruct_tasks([start])[0]["id"]
        correction = human(2, "correct", tid, {"claim": "Corrected synthetic claim"})
        update = source(3, [observation(kind="status", update="progress", update_target=tid,
                                       claim="Later synthetic status", work_state="waiting")], "2026-10-03")
        item = r.reconstruct_tasks([start, correction, update])[0]
        self.assertEqual(item["claim"], "Corrected synthetic claim")
        self.assertEqual(item["status"], "waiting")
        self.assertEqual(item["last_changed"], "2026-10-03")

    def test_approved_update_uses_its_meeting_source(self):
        import hashlib
        start = source()
        tid = r.reconstruct_tasks([start])[0]["id"]
        update = source(2, [observation(kind="status", update="date_changed", update_target=tid,
                                       due_text="2026-10-16", required_review=True)], "2026-10-03")
        update["source"]["title"] = "Synthetic second source"
        job = hashlib.sha256(b"2:synthetic").hexdigest()
        oid = hashlib.sha256((job + ":observation:0").encode()).hexdigest()
        item = r.reconstruct_tasks([start, update, human(3, "approve", oid, {}, "2026-10-04")])[0]
        self.assertEqual(item["source_title"], "Synthetic second source")
        self.assertEqual(item["source_id"], "2")
        self.assertEqual(item["source_date"], "2026-10-03")
        self.assertEqual(item["last_changed"], "2026-10-04")
        self.assertEqual(item["due_reference_date"], "2026-10-03")

    def test_future_events_excluded_and_unknown_target_fails(self):
        self.assertEqual(r.reconstruct_tasks([source(when="2026-10-14")], today=date(2026, 10, 13)), [])
        with self.assertRaises(ValueError):
            r.reconstruct_tasks([source(observations=[observation(update="done", update_target="missing")])])

    def test_notes_nested_json_supported(self):
        notes = [{"note_json": json.dumps({"legacy_record": {"id": "1", "title": "Synthetic metadata"}})}]
        self.assertEqual(len(r.reconstruct_tasks([source()], notes)), 1)

    def test_archive_stream_and_cli(self):
        with tempfile.TemporaryDirectory(dir=HERE) as temp:
            folder = Path(temp)
            archive = folder / "synthetic.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                for name, data in [("canonical/journal.jsonl", json.dumps(source()) + "\n"),
                                   ("canonical/notes.jsonl", json.dumps({"note_json": "{}"}) + "\n")]:
                    raw = data.encode()
                    info = tarfile.TarInfo(name)
                    info.size = len(raw)
                    tar.addfile(info, io.BytesIO(raw))
            out = folder / "digest.md"
            command = [sys.executable, "-I", "-B", str(HERE / "reminders.py"), "--archive", str(archive),
                       "--today", "2026-10-13", "--owner", "Gleb", "--out", str(out)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            metrics = json.loads(result.stdout)
            self.assertEqual(metrics["digest_entries"], 1)
            self.assertEqual(metrics["digest_characters"], len(out.read_text()))
            self.assertNotIn("Synthetic task", result.stdout)
            self.assertFalse((folder / "canonical").exists())
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(json.loads(second.stdout)["digest_entries"], 0)


if __name__ == "__main__":
    unittest.main()
