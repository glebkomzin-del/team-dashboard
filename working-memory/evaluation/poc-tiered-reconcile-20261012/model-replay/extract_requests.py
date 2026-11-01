#!/usr/bin/env python3
"""Extract saved reconciliation calls from a queue archive without unpacking it."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, Iterable, TextIO


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ARCHIVE = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Dashboard Job Backup"
    / "archives"
    / "dashboard-20261012T155114Z.tar.gz"
)
PROMPT_MARKER = "Bereits geöffnete Original-IDs"
DATE_RE = re.compile(r"\nDatum: (\d{4}-\d{2}-\d{2})(?=\r?\n|$)")


class ExtractionError(Exception):
    """An input or selected call failed validation; message contains no source data."""


def _identity(value: object) -> tuple[str, int]:
    if not isinstance(value, dict):
        raise ExtractionError("invalid identity")
    job_id = value.get("job_id")
    call_index = value.get("call_index")
    if not isinstance(job_id, str) or not job_id.strip():
        raise ExtractionError("invalid identity")
    if isinstance(call_index, bool) or not isinstance(call_index, int) or call_index < 0:
        raise ExtractionError("invalid identity")
    return job_id, call_index


def load_index(path: str | Path) -> set[tuple[str, int]]:
    """Load selected calls from JSONL objects or one JSON array of objects."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise ExtractionError("invalid index") from None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            entries = [json.loads(line) for line in raw.splitlines() if line.strip()]
        except json.JSONDecodeError:
            raise ExtractionError("invalid index") from None
    else:
        entries = parsed if isinstance(parsed, list) else [parsed]

    identities: set[tuple[str, int]] = set()
    for entry in entries:
        identity = _identity(entry)
        if identity in identities:
            raise ExtractionError("duplicate index identity")
        identities.add(identity)
    return identities


def _json_value(value: object) -> object:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            raise ExtractionError("invalid call payload") from None
    return value


def _meeting_date(prompt: str) -> str | None:
    match = DATE_RE.search(prompt)
    if match is None:
        return None
    candidate = match.group(1)
    try:
        dt.date.fromisoformat(candidate)
    except ValueError:
        return None
    return candidate


def extract_lines(
    lines: Iterable[str], writer: TextIO, selected: set[tuple[str, int]] | None = None
) -> dict[str, int]:
    """Stream calls to rows; counts unknown_references and unknown_usage when unavailable."""
    counts = {"queue_lines": 0, "call_records": 0, "matched_calls": 0,
              "written_calls": 0, "unknown_dates": 0,
              "unknown_references": 0, "unknown_usage": 0}
    seen: set[tuple[str, int]] = set()
    found: set[tuple[str, int]] = set()

    for line in lines:
        counts["queue_lines"] += 1
        try:
            envelope = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            raise ExtractionError("invalid queue line") from None
        if not isinstance(envelope, dict):
            raise ExtractionError("invalid queue line")
        if envelope.get("kind") != "call":
            continue
        counts["call_records"] += 1
        call = _json_value(envelope.get("record_json"))
        if not isinstance(call, dict):
            raise ExtractionError("invalid call payload")
        request = _json_value(call.get("request_json"))
        if not isinstance(request, dict):
            raise ExtractionError("invalid call payload")
        prompt = request.get("prompt")
        if not isinstance(prompt, str) or PROMPT_MARKER not in prompt:
            continue
        counts["matched_calls"] += 1
        identity = _identity(call)
        if selected is not None and identity not in selected:
            continue
        if identity in seen:
            raise ExtractionError("duplicate selected call")
        seen.add(identity)
        found.add(identity)

        response = _json_value(call.get("response_json"))
        if not isinstance(response, dict):
            raise ExtractionError("invalid call payload")
        content = response.get("content")
        reference_text = None
        if isinstance(content, list) and content and isinstance(content[0], dict):
            candidate_text = content[0].get("text")
            if isinstance(candidate_text, str):
                reference_text = candidate_text
        if reference_text is None:
            counts["unknown_references"] += 1
        usage = response.get("usage")
        if not isinstance(usage, dict):
            usage = None
            counts["unknown_usage"] += 1

        meeting_date = _meeting_date(prompt)
        if meeting_date is None:
            counts["unknown_dates"] += 1
        row = {
            "job_id": identity[0],
            "call_index": identity[1],
            "meeting_date": meeting_date,
            "request_json": request,
            "reference_text": reference_text,
            "reference_usage": usage,
            "reference_micro_usd": call.get("actual_micro_usd"),
        }
        writer.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        counts["written_calls"] += 1

    if selected is not None and found != selected:
        raise ExtractionError("selected identity missing from queue")
    return counts


def _output_path(value: str) -> Path:
    path = (SCRIPT_DIR / value).resolve()
    try:
        path.relative_to(SCRIPT_DIR.resolve())
    except ValueError:
        raise ExtractionError("output must stay inside script directory") from None
    if path.exists():
        raise ExtractionError("output already exists")
    return path


def _atomic_output(
    path: Path,
    lines: Iterable[str],
    selected: set[tuple[str, int]] | None,
    before_publish: Callable[[], None] | None = None,
):
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=SCRIPT_DIR,
            prefix=".extract-", suffix=".tmp", delete=False,
        ) as output:
            temp_path = Path(output.name)
            counts = extract_lines(lines, output, selected)
            output.flush()
            os.fsync(output.fileno())
        if before_publish is not None:
            before_publish()
        # A hard link publishes the completed file atomically and refuses to overwrite.
        os.link(temp_path, path)
        temp_path.unlink()
        temp_path = None
        return counts
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except OSError:
                pass


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", default="requests.jsonl")
    parser.add_argument("--only-index-file", type=Path)
    parser.add_argument(
        "--queue", choices=("-",), help="read synthetic queue JSONL from stdin instead of the archive"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        output_path = _output_path(args.output)
        selected = load_index(args.only_index_file) if args.only_index_file else None
        process: subprocess.Popen[str] | None = None
        if args.queue == "-":
            lines = sys.stdin
        else:
            process = subprocess.Popen(
                ["tar", "-xzOf", str(args.archive), "canonical/queue.jsonl"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="strict",
            )
            assert process.stdout is not None
            lines = process.stdout

        def check_archive_status() -> None:
            if process is None:
                return
            assert process.stdout is not None
            process.stdout.close()
            if process.wait() != 0:
                raise ExtractionError("archive read failed")

        try:
            counts = _atomic_output(
                output_path, lines, selected,
                before_publish=check_archive_status if process is not None else None,
            )
        except (ExtractionError, UnicodeError, OSError):
            if process is not None and process.poll() is None:
                process.stdout.close()
                process.wait()
            raise
        print(json.dumps({"output": output_path.name, **counts}, separators=(",", ":")))
        return 0
    except (ExtractionError, OSError, UnicodeError) as exc:
        print(f"extract_requests: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
