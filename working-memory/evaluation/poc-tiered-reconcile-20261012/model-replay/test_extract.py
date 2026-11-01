import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("extract_requests.py")
SPEC = importlib.util.spec_from_file_location("extract_requests", SCRIPT)
extract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extract)


def queue_line(job_id, call_index, prompt, *, kind="call", encoded=True):
    request = {"prompt": prompt, "model": "reference-model", "metadata": {"k": [1, 2]}}
    response = {
        "content": [{"type": "text", "text": '{ "answer" : [1, 2] }'}],
        "usage": {"input_tokens": 123, "output_tokens": 45, "detail": {"cached": 6}},
        "stop_reason": "end_turn",
    }
    call = {
        "job_id": job_id,
        "call_index": call_index,
        "request_json": json.dumps(request) if encoded else request,
        "response_json": json.dumps(response) if encoded else response,
        "actual_micro_usd": 9876,
    }
    envelope = {"kind": kind, "sequence": 42, "record_json": json.dumps(call)}
    return json.dumps(envelope)


class ExtractTests(unittest.TestCase):
    def extract(self, lines, selected=None):
        output = io.StringIO()
        counts = extract.extract_lines(lines, output, selected)
        rows = [json.loads(line) for line in output.getvalue().splitlines()]
        return rows, counts

    def test_filters_kind_and_prompt_and_preserves_reference_values(self):
        lines = [
            queue_line("other", 0, "\nDatum: 2026-10-12", kind="search_document"),
            queue_line("no-match", 1, "ordinary call\nDatum: 2026-10-12"),
            queue_line("job-A", 2, "Reconcile\nBereits geöffnete Original-IDs\nDatum: 2026-10-12"),
        ]
        rows, counts = self.extract(lines)
        self.assertEqual(counts["written_calls"], 1)
        self.assertEqual(counts["matched_calls"], 1)
        self.assertEqual(rows, [{
            "job_id": "job-A",
            "call_index": 2,
            "meeting_date": "2026-10-12",
            "request_json": {
                "prompt": "Reconcile\nBereits geöffnete Original-IDs\nDatum: 2026-10-12",
                "model": "reference-model",
                "metadata": {"k": [1, 2]},
            },
            "reference_text": '{ "answer" : [1, 2] }',
            "reference_usage": {"input_tokens": 123, "output_tokens": 45, "detail": {"cached": 6}},
            "reference_micro_usd": 9876,
        }])

    def test_unknown_or_invalid_iso_dates_are_retained_as_null_and_counted(self):
        lines = [
            queue_line("missing-date", 0, "Bereits geöffnete Original-IDs"),
            queue_line("invalid-date", 1, "Bereits geöffnete Original-IDs\nDatum: 2026-02-30"),
        ]
        rows, counts = self.extract(lines)
        self.assertEqual([row["meeting_date"] for row in rows], [None, None])
        self.assertEqual(counts["unknown_dates"], 2)

    def test_recorded_failed_reference_is_retained_with_unknown_fields_counted(self):
        line = json.loads(queue_line("failed", 7, "Bereits geöffnete Original-IDs"))
        call = json.loads(line["record_json"])
        call["response_json"] = json.dumps({
            "content": [],
            "error": "provider returned no content",
            "usage": {"input_tokens": 12},
            "stop_reason": None,
            "terminal_status": "error",
            "usage_final": False,
        })
        line["record_json"] = json.dumps(call)

        rows, counts = self.extract([json.dumps(line)])
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["reference_text"])
        self.assertEqual(rows[0]["reference_usage"], {"input_tokens": 12})
        self.assertEqual(counts["unknown_references"], 1)
        self.assertEqual(counts["unknown_usage"], 0)

    def test_invalid_usage_is_retained_as_unknown(self):
        line = json.loads(queue_line("failed-usage", 8, "Bereits geöffnete Original-IDs"))
        call = json.loads(line["record_json"])
        response = json.loads(call["response_json"])
        response["usage"] = None
        call["response_json"] = json.dumps(response)
        line["record_json"] = json.dumps(call)

        rows, counts = self.extract([json.dumps(line)])
        self.assertIsNone(rows[0]["reference_usage"])
        self.assertEqual(counts["unknown_usage"], 1)

    def test_selection_uses_pair_identity_and_jsonl_or_array_indexes(self):
        rows, _ = self.extract([
            queue_line("same", 3, "Bereits geöffnete Original-IDs", encoded=False),
            queue_line("same", 4, "Bereits geöffnete Original-IDs"),
        ], {("same", 4)})
        self.assertEqual([(row["job_id"], row["call_index"]) for row in rows], [("same", 4)])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            path.write_text('{"job_id":"a","call_index":1}\n{"job_id":"b","call_index":2}\n')
            self.assertEqual(extract.load_index(path), {("a", 1), ("b", 2)})
            path.write_text('[{"job_id":"a","call_index":1}]')
            self.assertEqual(extract.load_index(path), {("a", 1)})

    def test_streams_lines_and_does_not_buffer_queue(self):
        consumed = []

        def stream():
            for index in range(3):
                consumed.append(index)
                yield queue_line("job", index, "ordinary")
                self.assertEqual(consumed[-1], index)

        rows, counts = self.extract(stream())
        self.assertEqual(rows, [])
        self.assertEqual(counts["queue_lines"], 3)
        self.assertEqual(consumed, [0, 1, 2])

    def test_rejects_duplicates_missing_index_targets_bad_identity_and_malformed_line(self):
        matching = queue_line("job", 0, "Bereits geöffnete Original-IDs")
        with self.assertRaises(extract.ExtractionError):
            self.extract([matching, matching])
        with self.assertRaises(extract.ExtractionError):
            self.extract([], {("absent", 1)})
        invalid = json.loads(matching)
        call = json.loads(invalid["record_json"])
        call["call_index"] = True
        invalid["record_json"] = json.dumps(call)
        with self.assertRaises(extract.ExtractionError):
            self.extract([json.dumps(invalid)])
        invalid_response = json.loads(matching)
        invalid_call = json.loads(invalid_response["record_json"])
        invalid_call["response_json"] = "not-json"
        invalid_response["record_json"] = json.dumps(invalid_call)
        with self.assertRaises(extract.ExtractionError):
            self.extract([json.dumps(invalid_response)])
        with self.assertRaises(extract.ExtractionError):
            self.extract(["not-json"])

    def test_atomic_output_discards_partial_rows_after_late_invalid_line(self):
        with tempfile.TemporaryDirectory(dir=extract.SCRIPT_DIR) as directory:
            output_path = Path(directory) / "result.jsonl"
            lines = [
                queue_line("job", 0, "Bereits geöffnete Original-IDs"),
                "invalid-late-line",
            ]
            with self.assertRaises(extract.ExtractionError):
                extract._atomic_output(output_path, lines, None)
            self.assertFalse(output_path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_tar_failure_never_publishes_output(self):
        class FailedTar:
            def __init__(self, stdout):
                self.stdout = stdout
                self.waited = False

            def wait(self):
                self.waited = True
                return 2

            def poll(self):
                return 2 if self.waited else None

        with tempfile.TemporaryDirectory(dir=extract.SCRIPT_DIR) as directory:
            output_name = f"{Path(directory).name}/requests.jsonl"
            output_path = Path(directory) / "requests.jsonl"
            process = FailedTar(io.StringIO(queue_line("job", 0, "Bereits geöffnete Original-IDs")))
            with mock.patch.object(extract.subprocess, "Popen", return_value=process):
                status = extract.main(["--archive", "synthetic.tar.gz", "--output", output_name])
            self.assertEqual(status, 2)
            self.assertTrue(process.waited)
            self.assertFalse(output_path.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_index_rejects_duplicates_and_invalid_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.jsonl"
            path.write_text('{"job_id":"a","call_index":1}\n{"job_id":"a","call_index":1}\n')
            with self.assertRaises(extract.ExtractionError):
                extract.load_index(path)
            path.write_text('[{"job_id":"","call_index":1}]')
            with self.assertRaises(extract.ExtractionError):
                extract.load_index(path)


if __name__ == "__main__":
    unittest.main()
