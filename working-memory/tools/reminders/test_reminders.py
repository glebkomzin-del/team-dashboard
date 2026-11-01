"""Synthetic contract tests; no archive, network, or production access.

Question: do parser, rule gates and digest persistence honor the agreed contract?
Criterion: boundaries, unknown inputs, cooldown exceptions and pure state updates.
Scope: synthetic dictionaries and disposable files beside this test module.
Decision: passing supports local acceptance; failure identifies an open contract.
"""
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("reminders_under_test", HERE / "reminders.py")
reminders = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reminders
SPEC.loader.exec_module(reminders)
TODAY = dt.date(2026, 10, 13)


def task(**changes):
    result = dict(id="synthetic-1", title="Synthetic task", claim="Synthetic claim",
                  owner="Gleb", status="open", due_text="", due_reference_date=None,
                  condition_text="", matter="Synthetic matter", source_title="Synthetic source",
                  source_date="2026-10-13", first_changed="2026-10-13",
                  last_changed="2026-10-13")
    result.update(changes)
    return result


def ago(days):
    return (TODAY - dt.timedelta(days=days)).isoformat()


def state():
    return {"version": 1, "last_sent": {}}


class ParserTests(unittest.TestCase):
    def check(self, text, expected, status="parsed", reference=None):
        due = reminders.parse_due(text, reference_date=reference)
        self.assertEqual(due.status, status)
        self.assertEqual(due.value, dt.date.fromisoformat(expected) if expected else None)

    def test_iso_and_prefixes(self):
        for text in ("2026-10-16", "bis 2026-10-16", "am 2026-10-16", "zum 2026-10-16"):
            with self.subTest(text=text):
                self.check(text, "2026-10-16")

    def test_missing(self):
        for text in (None, "", "   "):
            with self.subTest(text=text):
                self.check(text, None, "missing")

    def test_invalid_or_ambiguous(self):
        for text in ("2026-02-30", "2026-13-01", "2026-1-2", "morgen oder Freitag",
                     "2026-10-15 / 2026-10-16", "irgendwann", "2026-10-13T10:00:00"):
            with self.subTest(text=text):
                self.check(text, None, "unclear", TODAY)

    def test_friday_uses_reference_not_wall_clock(self):
        self.check("bis Freitag", "2026-10-16", reference=TODAY)
        self.check("bis Freitag", "2026-10-16", reference="2026-10-16")
        self.check("bis Freitag", "2026-10-23", reference="2026-10-17")

    def test_friday_without_reference(self):
        self.check("bis Freitag", None, "unclear")

    def test_month_end(self):
        self.check("Ende Oktober", "2026-10-31", reference=TODAY)
        self.check("Ende Oktober", "2026-10-31", reference="2026-11-15")
        self.check("Ende Oktober 2026", "2026-10-31")
        self.check("Ende Oktober", None, "unclear")

    def test_leap_year_and_year_boundaries(self):
        self.check("Ende Februar 2024", "2024-02-29")
        self.check("Ende Februar 2025", "2025-02-28")
        self.check("29.02.2024", "2024-02-29")
        self.check("29.02.2025", None, "unclear")
        self.check("Ende Februar 0000", None, "unclear")
        self.check("morgen", None, "unclear", reference="9999-12-31")
        self.check("bis Freitag", "2027-01-01", reference="2026-12-31")

    def test_reference_and_nontext_edge_cases(self):
        self.check("morgen", None, "unclear", reference="2026-02-30")
        self.check("morgen", "2026-10-14", reference=TODAY)
        self.check("in 3 Tagen", "2026-10-16", reference=TODAY)
        self.check(123, None, "unclear")


class RuleTests(unittest.TestCase):
    def has(self, rule, expected, **changes):
        self.assertEqual(rule in reminders.rule_matches(task(**changes), TODAY, "Gleb"),
                         expected, (rule, changes))

    def test_default_config(self):
        expected = dict(soon_days=3, stalled_days=21, no_due_days=45, waiting_days=7,
                        completed_days=3, cooldown_days=3, overdue_daily_limit=5,
                        max_entries=15)
        for key, value in expected.items():
            self.assertEqual(reminders.DEFAULT_CONFIG[key], value)

    def test_overdue(self):
        for due, expected in ((ago(1), True), (ago(0), False), ("2026-10-14", False),
                              ("", False), ("unclear", False)):
            self.has("overdue", expected, due_text=due)

    def test_due_soon(self):
        for days, expected in ((-1, False), (0, True), (3, True), (4, False)):
            self.has("due_soon", expected, due_text=(TODAY + dt.timedelta(days=days)).isoformat())
        self.has("due_soon", False, due_text="unclear")
        self.has("due_soon", False)

    def test_due_reference(self):
        self.has("due_soon", True, due_text="bis Freitag", due_reference_date="2026-10-13")
        self.has("unclear_due", True, due_text="bis Freitag")

    def test_stalled_boundary_and_unknown(self):
        for days, expected in ((21, False), (22, True), (-1, False)):
            self.has("stalled", expected, last_changed=ago(days))
        for unknown in (None, "", "bad", "2026-02-30"):
            self.has("stalled", False, last_changed=unknown)

    def test_stalled_owner_or_due(self):
        self.has("stalled", False, owner="Other", last_changed=ago(22))
        self.has("stalled", True, owner="Other", due_text="unclear", last_changed=ago(22))
        for alias in ("Gleb", "Komzin, Gleb", "Gleb Komzin", "Komzin Gleb"):
            self.has("stalled", True, owner=alias, last_changed=ago(22))

    def test_no_due_boundary_and_unknown(self):
        for days, expected in ((45, False), (46, True), (-1, False)):
            self.has("no_due", expected, first_changed=ago(days))
        for unknown in (None, "", "bad", "2026-02-30"):
            self.has("no_due", False, first_changed=unknown)
        self.has("no_due", False, first_changed=ago(46), due_text="unclear")
        self.has("no_due", False, first_changed=ago(46), due_text="2026-10-20")

    def test_waiting_boundary_condition_and_unknown(self):
        for days, expected in ((7, False), (8, True), (-1, False)):
            self.has("waiting", expected, status="waiting", last_changed=ago(days))
        self.has("waiting", True, status="waiting", last_changed=ago(8), condition_text="Synthetic condition")
        self.has("waiting", False, last_changed=ago(8))
        for unknown in (None, "", "bad", "2026-02-30"):
            self.has("waiting", False, status="waiting", last_changed=unknown)

    def test_completed_boundary_and_unknown(self):
        for days, expected in ((0, True), (3, True), (4, False), (-1, False)):
            self.has("completed", expected, status="done", last_changed=ago(days))
        self.has("completed", False)
        for unknown in (None, "", "bad", "2026-02-30"):
            self.has("completed", False, status="done", last_changed=unknown)

    def test_unclear_due(self):
        self.has("unclear_due", True, due_text="when possible")
        self.has("unclear_due", False, due_text="2026-10-16")
        self.has("unclear_due", False)

    def test_nonactive_statuses_gate_all_noncompleted_rules(self):
        for status in ("done", "aborted", "unknown", ""):
            matches = reminders.rule_matches(task(status=status, due_text=ago(10),
                                                  last_changed=ago(60), first_changed=ago(60)), TODAY, "Gleb")
            self.assertEqual(matches, [])
        matches = reminders.rule_matches(task(status="done", due_text="unclear"), TODAY, "Gleb")
        self.assertEqual(matches, ["completed"])


class DigestTests(unittest.TestCase):
    def digest(self, tasks, current_state=None, today=TODAY, config=None):
        return reminders.build_digest(tasks, today, "Gleb", current_state if current_state is not None else state(),
                                      config=reminders.DEFAULT_CONFIG if config is None else config)

    def test_empty(self):
        result = self.digest([])
        self.assertIsInstance(result.text, str)
        self.assertEqual((result.shown, result.omitted), (0, 0))
        self.assertEqual(result.state, state())

    def test_pure_inputs(self):
        tasks, current_state = [task(due_text=ago(1))], state()
        before = copy.deepcopy((tasks, current_state, reminders.DEFAULT_CONFIG))
        result = self.digest(tasks, current_state)
        self.assertEqual((tasks, current_state, reminders.DEFAULT_CONFIG), before)
        self.assertIsNot(result.state, current_state)

    def test_one_entry_all_rules_and_raw_counts(self):
        result = self.digest([task(due_text=ago(1), last_changed=ago(22))])
        self.assertEqual(result.shown, 1)
        self.assertEqual(result.counts["overdue"], 1)
        self.assertEqual(result.counts["stalled"], 1)
        self.assertEqual(result.state["last_sent"]["synthetic-1"]["overdue"], TODAY.isoformat())
        self.assertEqual(result.state["last_sent"]["synthetic-1"]["stalled"], TODAY.isoformat())
        self.assertEqual(result.text.count("Synthetic task"), 1)

    def test_same_day_no_repeat_counts_stay_raw(self):
        tasks = [task(due_text=ago(1))]
        first = self.digest(tasks)
        second = self.digest(tasks, first.state)
        self.assertEqual(second.shown, 0)
        self.assertEqual(second.counts["overdue"], 1)
        self.assertEqual(second.state, first.state)

    def test_regular_cooldown_boundary(self):
        tasks = [task(due_text="unclear")]
        first = self.digest(tasks)
        for days, shown in ((1, 0), (2, 0), (3, 1)):
            with self.subTest(days=days):
                self.assertEqual(self.digest(tasks, first.state, TODAY + dt.timedelta(days=days)).shown, shown)

    def test_daily_overdue_does_not_repeat_suppressed_reason(self):
        tasks = [task(due_text=ago(1), last_changed=ago(22))]
        first = self.digest(tasks)
        next_day = TODAY + dt.timedelta(days=1)
        second = self.digest(tasks, first.state, next_day)
        self.assertEqual(second.shown, 1)
        self.assertIn("überfällig", second.text)
        self.assertNotIn("Stillstand", second.text)
        self.assertEqual(second.state["last_sent"]["synthetic-1"]["stalled"], TODAY.isoformat())
        self.assertEqual(second.state["last_sent"]["synthetic-1"]["overdue"], next_day.isoformat())

    def test_future_report_date_not_overwritten_by_other_rule(self):
        current = {"version": 1, "last_sent": {
            "synthetic-1": {"overdue": "2026-10-20"}}}
        result = self.digest([task(due_text=ago(1), last_changed=ago(22))], current)
        self.assertEqual(result.shown, 1)
        self.assertNotIn("überfällig", result.text)
        self.assertIn("Stillstand", result.text)
        self.assertEqual(result.state["last_sent"]["synthetic-1"]["overdue"], "2026-10-20")

    def test_configurable_cooldown_and_daily_limit(self):
        config = {**reminders.DEFAULT_CONFIG, "cooldown_days": 5, "overdue_daily_limit": 0}
        tasks = [task(due_text=ago(1))]
        first = self.digest(tasks, config=config)
        self.assertEqual(self.digest(tasks, first.state, TODAY + dt.timedelta(days=3), config).shown, 0)
        self.assertEqual(self.digest(tasks, first.state, TODAY + dt.timedelta(days=5), config).shown, 1)

    def test_oldest_five_overdue_daily_rest_cooldown(self):
        tasks = [task(id=f"overdue-{i}", title=f"Synthetic overdue {i}", due_text=ago(i + 1)) for i in range(7)]
        first = self.digest(tasks)
        next_day = self.digest(tasks, first.state, TODAY + dt.timedelta(days=1))
        self.assertEqual(next_day.shown, 5)
        self.assertEqual(next_day.counts["overdue"], 7)
        for i in range(7):
            sent = next_day.state["last_sent"][f"overdue-{i}"]["overdue"]
            self.assertEqual(sent, (TODAY + dt.timedelta(days=1)).isoformat() if i >= 2 else TODAY.isoformat())
        self.assertEqual(self.digest(tasks, first.state, TODAY + dt.timedelta(days=3)).shown, 7)

    def test_cap_does_not_mark_hidden_entries(self):
        tasks = [task(id=f"cap-{i}", title=f"Synthetic cap {i}", due_text="unclear") for i in range(17)]
        result = self.digest(tasks)
        self.assertEqual((result.shown, result.omitted), (15, 2))
        self.assertEqual(result.counts["unclear_due"], 17)
        self.assertEqual(len(result.state["last_sent"]), 15)
        self.assertIn("2", result.text)
        second = self.digest(tasks, result.state)
        self.assertEqual(second.shown, 2)

    def test_priority(self):
        tasks = [task(id="completed", title="Z completed", status="done"),
                 task(id="unclear", title="Z unclear", due_text="unclear"),
                 task(id="nodue", title="Z nodue", first_changed=ago(46)),
                 task(id="stalled", title="Z stalled", last_changed=ago(22)),
                 task(id="waiting", title="Z waiting", status="waiting", last_changed=ago(8)),
                 task(id="soon", title="Z soon", due_text="2026-10-16"),
                 task(id="overdue", title="Z overdue", due_text=ago(1))]
        result = self.digest(tasks)
        titles = ["Z overdue", "Z soon", "Z waiting", "Z stalled", "Z nodue", "Z unclear", "Z completed"]
        positions = [result.text.index(title) for title in titles]
        self.assertEqual(positions, sorted(positions))

    def test_waiting_missing_condition_is_explicit(self):
        result = self.digest([task(status="waiting", last_changed=ago(8))])
        self.assertEqual(result.shown, 1)
        self.assertRegex(result.text.lower(), r"(?:bedingung.*(?:fehlt|fehlend|nicht|unbekannt)|(?:keine|fehlende).*bedingung)")


class StateTests(unittest.TestCase):
    def test_missing_state(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            self.assertEqual(reminders.load_state(Path(directory) / "missing.json"), state())

    def test_roundtrip_and_replace(self):
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "state.json"
            original = {"version": 1, "last_sent": {"synthetic-1": {"overdue": "2026-10-13"}}}
            reminders.save_state(path, original)
            self.assertEqual(reminders.load_state(path), original)
            reminders.save_state(path, state())
            self.assertEqual(reminders.load_state(path), state())
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_corrupt_state(self):
        samples = ("not json", "[]", "null", json.dumps({"version": 1, "last_sent": []}),
                   json.dumps({"version": 1, "last_sent": {"x": {"overdue": "2026-02-30"}}}))
        with tempfile.TemporaryDirectory(dir=HERE) as directory:
            path = Path(directory) / "state.json"
            for sample in samples:
                with self.subTest(sample=sample):
                    path.write_text(sample, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        reminders.load_state(path)


if __name__ == "__main__":
    unittest.main()
