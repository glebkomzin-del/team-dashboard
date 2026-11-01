"""Synthetic tests: thresholds/index evidence/cost coverage; failures block acceptance.

Scope is the offline comparator, including its CLI. No meeting data or providers.
"""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("replay_compare_tested", ROOT / "compare.py")
compare = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = compare
spec.loader.exec_module(compare)


def fixture(positives=1, observations=1, navigation=False):
    schema = {"type": "object", "required": ["work_results", "observations"],
        "additionalProperties": False, "$defs": {"lifecycle_result": {"anyOf": [
            {"type": "string", "enum": ["unchanged"]},
            {"type": "object", "required": ["action"], "properties": {
                "action": {"type": "string", "enum": ["update", "close"]}}, "additionalProperties": False}]}},
        "properties": {"work_results": {"anyOf": [{"type": "null"},
            {"type": "object", "additionalProperties": {"$ref": "#/$defs/lifecycle_result"}}]},
        "observations": {"type": "array", "items": {"type": "object",
            "required": ["source_index", "update_target", "update", "kind"],
            "properties": {"source_index": {"type": "integer", "minimum": 0},
                "update_target": {"type": ["string", "null"]}, "update": {"type": "boolean"},
                "kind": {"type": "string"}}, "additionalProperties": False}}}}
    output = {"work_results": None if navigation else {str(i): {"action": "update"} for i in range(positives)},
              "observations": [{"source_index": i, "update_target": None if i == 0 else "w1",
                                "update": True, "kind": "work"} for i in range(observations)]}
    request = {"job_id": "synthetic", "call_index": 0, "meeting_date": "2026-01-01",
               "request_json": {"prompt": "synthetic", "schema": schema, "model": "synthetic",
                                "max_tokens": 100, "scope": "synthetic"},
               "reference_text": json.dumps(output), "reference_usage": {"input_tokens": 10, "output_tokens": 2},
               "reference_micro_usd": 12}
    result = {"job_id": "synthetic", "call_index": 0, "attempt": 1, "status": "ok", "http_status": 200,
              "raw_response": "synthetic", "response": {"status": "completed"},
              "text": json.dumps(output), "usage": {"input_tokens": 10, "output_tokens": 2},
              "actual_micro_usd": 12, "error": None}
    return request, result, output


class CompareTests(unittest.TestCase):
    def report(self, request, result):
        return compare.compare_records([request], result if isinstance(result, list) else [result])

    def test_exact_production_mapping_and_nullable_alias(self):
        request, result, _ = fixture()
        report = self.report(request, result)
        self.assertTrue(report["passed"])
        self.assertEqual(report["total"]["recall_hits"], 1)
        self.assertEqual(report["total"]["update_target_matches"], 1)

    def test_62_of_64_passes_but_61_fails(self):
        request, result, output = fixture(64)
        for recovered, expected in [(62, True), (61, False)]:
            candidate = copy.deepcopy(output)
            for i in range(recovered, 64):
                candidate["work_results"][str(i)] = "unchanged"
            result["text"] = json.dumps(candidate)
            self.assertEqual(self.report(request, result)["passed"], expected)

    def test_non64_denominator_requires_ratio(self):
        request, result, output = fixture(65)
        for recovered, expected in [(63, False), (64, True)]:
            candidate = copy.deepcopy(output)
            for i in range(recovered, 65):
                candidate["work_results"][str(i)] = "unchanged"
            result["text"] = json.dumps(candidate)
            self.assertEqual(self.report(request, result)["passed"], expected)

    def test_update_target_threshold_and_literal_alias(self):
        request, result, output = fixture(observations=20)
        output["observations"][0]["update_target"] = "w1"
        result["text"] = json.dumps(output)
        self.assertTrue(self.report(request, result)["passed"])
        output["observations"][1]["update_target"] = "other_alias"
        result["text"] = json.dumps(output)
        self.assertFalse(self.report(request, result)["passed"])

    def test_update_and_kind_metrics(self):
        request, result, output = fixture()
        output["observations"][0].update(update=False, kind="knowledge")
        result["text"] = json.dumps(output)
        report = self.report(request, result)
        self.assertTrue(report["passed"])
        self.assertEqual(report["total"]["update_matches"], 0)
        self.assertEqual(report["total"]["kind_matches"], 0)

    def test_missing_extra_duplicate_observations_fail(self):
        request, result, output = fixture()
        for entries, counter in [([], "missing_observations"),
                ([*output["observations"], {**output["observations"][0], "source_index": 1}], "extra_observations"),
                (output["observations"] * 2, "duplicate_observations")]:
            result["text"] = json.dumps({**output, "observations": entries})
            report = self.report(request, result)
            self.assertFalse(report["passed"])
            self.assertEqual(report["total"][counter], 1)
            if counter == "duplicate_observations":
                self.assertEqual(report["total"]["update_target_matches"], 0)

    def test_missing_extra_work_fail_even_if_recall_could_pass(self):
        request, result, output = fixture()
        for work, counter in [({}, "missing_work"),
                ({**output["work_results"], "1": "unchanged"}, "extra_work")]:
            result["text"] = json.dumps({**output, "work_results": work})
            report = self.report(request, result)
            self.assertFalse(report["passed"])
            self.assertEqual(report["total"][counter], 1)

    def test_binary_unchanged_and_additional_positives(self):
        request, result, output = fixture()
        request["reference_text"] = json.dumps({**output, "work_results": {"0": "unchanged"}})
        report = self.report(request, result)
        self.assertTrue(report["passed"])
        self.assertEqual(report["total"]["additional_positives"], 1)
        self.assertEqual(report["total"]["work_binary_matches"], 0)

    def test_navigation_has_no_recall_but_schema_required(self):
        request, result, output = fixture(navigation=True)
        report = self.report(request, result)
        self.assertTrue(report["passed"])
        self.assertEqual(compare._fraction(report["total"]["recall_hits"], report["total"]["recall_total"]), "N/A")
        del output["work_results"]
        result["text"] = json.dumps(output)
        self.assertFalse(self.report(request, result)["passed"])

    def test_synthetic_list_form(self):
        request, result, output = fixture()
        request["request_json"]["schema"]["properties"]["work_results"] = {"type": "array", "items": {"$ref": "#/$defs/lifecycle_result"}}
        output["work_results"] = [{"action": "update"}]
        request["reference_text"] = result["text"] = json.dumps(output)
        self.assertTrue(self.report(request, result)["passed"])

    def test_final_attempt_only_and_all_costs(self):
        request, first, output = fixture()
        first.update(status="transport_error", text=None, actual_micro_usd=3)
        last = {**first, "attempt": 2, "status": "ok", "text": json.dumps(output), "actual_micro_usd": 12}
        report = self.report(request, [last, first])
        self.assertTrue(report["passed"])
        self.assertEqual(report["total"]["actual_micro_usd"], 15)
        self.assertEqual(report["total"]["error_attempts"], 1)
        last["status"] = "http_error"
        self.assertFalse(self.report(request, [first, last])["passed"])

    def test_unknown_cost_usage_never_zero(self):
        request, result, _ = fixture()
        failed = {**result, "status": "transport_error", "actual_micro_usd": None, "usage": {}}
        result["attempt"] = 2
        report = self.report(request, [failed, result])
        self.assertTrue(report["passed"])
        self.assertIsNone(report["total"]["actual_micro_usd"])
        self.assertIsNone(report["total"]["input_tokens"])
        self.assertEqual(report["total"]["cost_unknown_attempts"], 1)
        self.assertEqual(report["total"]["usage_unknown_attempts"], 1)

    def test_missing_unknown_invalid_outputs_do_not_become_perfect_agreement(self):
        request, result, _ = fixture()
        for mutation in [{"status": "content_error"}, {"text": None},
                         {"text": "not-json"}, {"response": None},
                         {"response": {"status": "incomplete"}}, {"response": {}},
                         {"text": '{"work_results":{},"work_results":{},"observations":[]}'},
                         {"text": '{"work_results":{},"observations":[],"x":NaN}'}]:
            report = self.report(request, {**result, **mutation})
            self.assertFalse(report["passed"])
            self.assertIsNone(report["total"]["update_target_matches"])
            self.assertEqual(report["total"]["output_known"], 0)
        self.assertFalse(self.report(request, [])["passed"])

    def test_unsupported_schema_fails_closed(self):
        request, result, _ = fixture()
        request["request_json"]["schema"]["unevaluatedProperties"] = False
        self.assertFalse(self.report(request, result)["passed"])

    def test_duplicate_attempt_request_and_orphan_fail(self):
        request, result, _ = fixture()
        self.assertFalse(self.report(request, [result, result])["passed"])
        self.assertFalse(compare.compare_records([request, request], [result])["passed"])
        orphan = {**result, "job_id": "orphan", "actual_micro_usd": 5}
        report = self.report(request, [result, orphan])
        self.assertFalse(report["passed"])
        self.assertEqual(report["total"]["actual_micro_usd"], 17)

    def test_cli_table_is_metadata_only_and_status_is_nonzero(self):
        request, result, _ = fixture()
        secret = "PRIVATE_MEETING_PROSE"
        request["request_json"]["prompt"] = secret
        result["raw_response"] = secret
        with tempfile.TemporaryDirectory(dir=ROOT, prefix="compare-synthetic-") as directory:
            request_path, result_path = Path(directory) / "requests.jsonl", Path(directory) / "results.jsonl"
            request_path.write_text(json.dumps(request) + "\n", encoding="utf-8")
            result_path.write_text(json.dumps(result) + "\n", encoding="utf-8")
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                code = compare.main(["--requests", str(request_path), "--results", str(result_path)])
            self.assertEqual(code, 0)
            self.assertIn("TOTAL", stream.getvalue())
            self.assertNotIn(secret, stream.getvalue())
            result_path.write_text("", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(compare.main(["--requests", str(request_path), "--results", str(result_path)]), 1)


if __name__ == "__main__":
    unittest.main()
