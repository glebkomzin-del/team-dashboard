"""Synthetic-only tests: no source meeting data and no file/network writes."""

import copy
import io
import json
import math
import sys
import unittest
from contextlib import redirect_stdout, redirect_stderr
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from selector import age_days, tokens, lexical_score, cosine, rank_candidates, select
from replay import Embeddings, PrimitiveUnpickler, metrics, used_indices, unknown_usage_indices, main


def work(alias, title="", changed="2025-01-01", **extra):
    return {"id": alias, "title": title, "claim": "", "matter": "", "owner": "",
            "status": "open", "last_changed": changed, **extra}


class SelectorTests(unittest.TestCase):
    def test_age_calendar(self):
        self.assertEqual(age_days("2026-10-12", "2026-09-21"), 21)
        self.assertEqual(age_days("2024-03-01", "2024-02-28"), 2)
        self.assertEqual(age_days(date(2026, 10, 12), datetime(2026, 10, 12)), 0)

    def test_age_invalid(self):
        for value in (None, "", "bad", "2026-02-30", 42):
            self.assertEqual(age_days("2026-10-12", value), 9999)
        self.assertEqual(age_days(None, "2026-10-12"), 9999)

    def test_age_timestamp_future(self):
        self.assertEqual(age_days("2026-10-12", "2026-10-11T23:59:59Z"), 1)
        self.assertEqual(age_days("2026-10-12", "2026-10-13"), -1)

    def test_tokens(self):
        self.assertEqual(tokens("ABC Abcd ABCDEF abcdefgh! ÄPFEL... Plan Plan"),
                         {"abcd", "abcdef", "äpfel", "plan"})
        self.assertEqual(tokens(None), set())
        self.assertEqual(tokens("a bb ccc"), set())
        self.assertEqual(tokens("STRAẞE"), {"strass"})

    def test_lexical(self):
        self.assertAlmostEqual(lexical_score({"a", "b"}, {"b", "c", "d"}), 1 / math.sqrt(6))
        self.assertEqual(lexical_score(set(), {"a"}), 0)
        self.assertEqual(lexical_score({"a"}, set()), 0)
        self.assertEqual(lexical_score({"a"}, {"a"}), 1)

    def test_cosine(self):
        self.assertAlmostEqual(cosine([1, 2], [2, 4]), 1)
        self.assertEqual(cosine([1, 0], [0, 1]), 0)
        self.assertEqual(cosine([1, 0], [-1, 0]), -1)
        self.assertEqual(cosine([0, 0], [1, 2]), 0)
        self.assertEqual(cosine([], []), 0)
        self.assertEqual(cosine(None, [1]), 0)

    def test_cosine_invalid(self):
        for a, b in (([1], [1, 2]), ([float("nan")], [1]), ([float("inf")], [1])):
            with self.assertRaises(ValueError):
                cosine(a, b)

    def test_rank_ties(self):
        self.assertEqual(rank_candidates([0.5, 1, 1, 0.5, -1]), [1, 2, 0, 3, 4])
        self.assertEqual(rank_candidates([0, 0, 0]), [0, 1, 2])
        self.assertEqual(rank_candidates([]), [])

    def test_rank_invalid(self):
        with self.assertRaises(ValueError):
            rank_candidates([float("nan")])

    def test_mini_fixture(self):
        candidates = [work("age", "fresh", "2026-10-12", status="done"),
                      work("emb", "other"), work("lex", "rocket"), work("none", "planet")]
        vectors = {"age": [-1, 0], "emb": [1, 0], "lex": [0, 1], "none": [0, -1]}
        result = select(candidates, [{"title": "rocket"}], "2026-10-12", 0, 1,
                        lambda c: vectors[c["id"]], lambda o: [1, 0])
        self.assertEqual(result["selected"], ["age", "emb", "lex"])
        self.assertEqual(result["reasons"], {"age": ["age"], "emb": ["emb"], "lex": ["lex"]})
        self.assertEqual(result["stats"]["selected"], 3)

    def test_empty_observations(self):
        r = select([work("new", changed="2026-10-12"), work("old")], [], "2026-10-12", 0, 5)
        self.assertEqual(r["selected"], ["new"])
        self.assertEqual(r["stats"]["lex_ranks"], [None, None])
        self.assertEqual(r["stats"]["emb_ranks"], [None, None])

    def test_empty_candidates(self):
        r = select([], [{"title": "rocket"}], "2026-10-12", 0, 5)
        self.assertEqual(r["selected"], [])
        self.assertEqual(r["stats"]["retained_fraction"], 0)

    def test_missing_embeddings(self):
        candidates = [work("missing", "planet"), work("lex", "rocket"), work("emb", "stars")]
        r = select(candidates, [{"title": "rocket"}], "2026-10-12", 0, 1,
                   lambda c: [1, 0] if c["id"] == "emb" else None, lambda o: [1, 0])
        self.assertEqual(r["selected"], ["lex", "emb"])
        self.assertEqual(r["stats"]["emb_ranks"], [None, None, 0])
        r = select(candidates, [{"title": "rocket"}], "2026-10-12", 0, 1,
                   lambda c: [1, 0], lambda o: None)
        self.assertEqual(r["selected"], ["lex"])
        r = select(candidates, [{"title": "rocket"}], "2026-10-12", 0, 1)
        self.assertEqual(r["selected"], ["lex"])

    def test_zero_A_k(self):
        candidates = [work("today", changed="2026-10-12"),
                      work("yesterday", "rocket", "2026-10-11"), work("unknown", changed=None)]
        r = select(candidates, [{"title": "rocket"}], "2026-10-12", 0, 0)
        self.assertEqual(r["selected"], ["today"])
        self.assertEqual(r["reasons"], {"today": ["age"]})

    def test_boundaries(self):
        candidates = [work("boundary", changed="2026-09-21"), work("outside", changed="2026-09-20")]
        self.assertEqual(select(candidates, [], "2026-10-12", 21, 0)["selected"], ["boundary"])
        r = select([work("a", "rocket"), work("b", "rocket")], [{"title": "rocket"}], "2026-10-12", 0, 1)
        self.assertEqual(r["selected"], ["a"])
        self.assertEqual(r["stats"]["lex_ranks"], [0, 1])

    def test_union_observations(self):
        r = select([work("a", "rocket"), work("b", "planet")],
                   [{"title": "rocket"}, {"title": "planet"}], "2026-10-12", 0, 1)
        self.assertEqual(r["selected"], ["a", "b"])

    def test_zero_scores_still_rank(self):
        r = select([work("a", "planet"), work("b", "stars")],
                   [{"title": "unrelated"}], "2026-10-12", 0, 1)
        self.assertEqual(r["selected"], ["a"])

    def test_all_reasons(self):
        r = select([work("a", "rocket", "2026-10-12")], [{"title": "rocket"}],
                   "2026-10-12", 0, 1, lambda c: [1], lambda o: [1])
        self.assertEqual(r["reasons"], {"a": ["age", "emb", "lex"]})

    def test_no_mutation(self):
        candidates, observations = [work("a", "rocket")], [{"title": "rocket"}]
        before = copy.deepcopy((candidates, observations))
        self.assertEqual(select(candidates, observations, "2026-10-12", 0, 1),
                         select(candidates, observations, "2026-10-12", 0, 1))
        self.assertEqual((candidates, observations), before)

    def test_invalid_parameters_ids(self):
        for A, k in ((-1, 0), (0, -1), (0.5, 1), (1, 0.5)):
            with self.assertRaises(ValueError):
                select([], [], "2026-10-12", A, k)
        with self.assertRaises(ValueError):
            select([work("a"), work("a")], [], "2026-10-12", 0, 0)


class ReplayTests(unittest.TestCase):
    def test_embedding_mapping(self):
        v = {"workdocs": {"Rocket\nClaim one": "[1,0]", "Rocket\nClaim two": [0, 1]}, "queries": {}}
        e = Embeddings(v)
        self.assertEqual(e.candidate(work("a", "Rocket", claim="Claim two")), (0, 1))
        self.assertIsNone(e.candidate(work("b", "Rocket", claim="unknown")))
        self.assertIsNone(e.candidate(work("c", "Absent")))
        self.assertIsNone(e.candidate(work("d", "Rocket", claim="")))
        self.assertIsNone(e.candidate(work("e", "Rock", claim="Claim one")))

    def test_historical_text_fields(self):
        candidates = [work("a", "planet", owner="rocket"), work("b", "rocket")]
        result = select(candidates, [{"title": "stars", "claim": "rocket"}], "2026-10-12", 0, 1)
        self.assertEqual(result["selected"], ["b"])

    def test_historical_cohort(self):
        call = {"meeting_date": "2026-10-12", "job_id": "synthetic",
                "work": [work("a", "PRIVATE", "2026-10-12", work_index="0")],
                "obs_in": [], "obs_out": [], "work_results": {"0": "unchanged"}}
        out = io.StringIO()
        with patch.object(Path, "open", side_effect=[io.StringIO(json.dumps(call)), io.BytesIO()]), \
             patch.object(PrimitiveUnpickler, "load", return_value={"workdocs": {}, "queries": {}}), \
             redirect_stdout(out):
            self.assertEqual(main(["--calls", "synthetic", "--vectors", "synthetic"]), 0)
        summary = json.loads(out.getvalue().splitlines()[0])
        self.assertEqual((summary["calls"], summary["complete_calls"], summary["candidates"]), (0, 1, 0))
        self.assertEqual(summary["excluded_empty_candidates"], 1)
        self.assertEqual(summary["all_complete_metrics"]["retained"], 1)
        self.assertNotIn("PRIVATE", out.getvalue())

    def test_query_unicode_fallback(self):
        obs = {"title": "Äpfel", "subject": "Plan", "search_keywords": ["rocket"]}
        for ascii_mode in (True, False):
            e = Embeddings({"workdocs": {}, "queries": {
                json.dumps(["Äpfel Plan rocket"], ensure_ascii=ascii_mode): "[1,2]"}})
            self.assertEqual(e.query(obs), (1, 2))
        self.assertIsNone(Embeddings({"workdocs": {}, "queries": {}}).query(obs))

    def test_used_definition(self):
        call = {"work": [work("a", work_index="0"), work("b", work_index="1"),
                         work("c", work_index="2")], "work_results": {
                             "0": "unchanged", "1": {"change": True}, "2": "unchanged"},
                "obs_out": [{"update_target": "a"}, {"update_target": "a"}]}
        self.assertEqual(used_indices(call), {0, 1})
        del call["work_results"]["2"]
        self.assertEqual(used_indices(call), {0, 1})
        self.assertEqual(unknown_usage_indices(call), {2})
        del call["work_results"]["0"]
        self.assertEqual(used_indices(call), {0, 1})
        self.assertEqual(unknown_usage_indices(call), {2})

    def test_grid_reuses_ranks(self):
        call = {"work": [work("a", "rocket"), work("b", "planet", "2026-10-12")]}
        obs = [{"title": "rocket"}]
        ranks = select(call["work"], obs, "2026-10-12", 0, 0)["stats"]
        for A in (0, 7, 14, 21, 30, 45):
            for k in (0, 3, 5, 8, 12):
                m = metrics([(call, ranks, {0})], A, k)
                direct = select(call["work"], obs, "2026-10-12", A, k)
                self.assertEqual(m["retained"], len(direct["selected"]))
        self.assertEqual(metrics([], 0, 0)["recall_pct"], None)
        missed = metrics([(call, ranks, {0})], 0, 0)["missed_used"]
        self.assertEqual(set(missed[0]), {"alias", "age_days", "status", "emb_rank", "lex_rank"})

    def test_cli_synthetic(self):
        call = {"meeting_date": "2026-10-12", "job_id": "synthetic",
                "work": [work("a", "PRIVATE_ROCKET", "2026-10-12", work_index="0")],
                "obs_in": [{"title": "PRIVATE_ROCKET"}], "obs_out": [],
                "work_results": {"0": {"changed": True}}}
        error = {"job_id": "synthetic", "error": "PRIVATE_ERROR"}
        out = io.StringIO()
        with patch.object(Path, "open", side_effect=[
                io.StringIO(json.dumps(call) + "\n" + json.dumps(error)), io.BytesIO()]), \
             patch.object(PrimitiveUnpickler, "load", return_value={"workdocs": {}, "queries": {}}), \
             redirect_stdout(out):
            self.assertEqual(main(["--calls", "synthetic", "--vectors", "synthetic", "--A", "21", "--k", "5"]), 0)
        lines = out.getvalue().splitlines()
        summary = json.loads(lines[0])
        self.assertEqual((summary["input_lines"], summary["calls"], summary["error_calls"]), (2, 1, 1))
        self.assertEqual((summary["used"], summary["recall_pct"]), (1, 100))
        self.assertEqual(len(lines), 32)
        self.assertNotIn("PRIVATE", out.getvalue())

    def test_cli_error_redaction(self):
        err = io.StringIO()
        with patch.object(Path, "open", side_effect=ValueError("PRIVATE_INPUT")), redirect_stderr(err):
            self.assertEqual(main(["--calls", "synthetic", "--vectors", "synthetic"]), 1)
        self.assertNotIn("PRIVATE_INPUT", err.getvalue())

    def test_pickle_no_code(self):
        with self.assertRaises(ValueError):
            PrimitiveUnpickler(io.BytesIO(b"cos\nsystem\n.")).load()


if __name__ == "__main__":
    unittest.main()
