"""Offline comparison; stdout contains identifiers and metrics, never model prose.

Recall passes with >=62 positives recovered when the reference denominator is
exactly 64; otherwise it requires >=97%. Thresholds apply to TOTAL. Navigation
responses (work_results=null) have N/A lifecycle recall, not perfect recall.
All attempt costs count; only the highest numbered attempt supplies decisions.
"""
import argparse
import functools
import importlib.util
import json
from pathlib import Path
import sys


@functools.lru_cache(maxsize=1)
def _common():
    path = Path(__file__).with_name("replay_common.py")
    spec = importlib.util.spec_from_file_location("replay_compare_common", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _decode(text):
    if not isinstance(text, str):
        raise ValueError("missing_text")
    value = _common().parse_json(text)
    if not isinstance(value, dict):
        raise ValueError("output_not_object")
    return value


def _key(record):
    if not isinstance(record, dict):
        raise ValueError("record_not_object")
    job, call = record.get("job_id"), record.get("call_index")
    if not isinstance(job, str) or not job or type(call) is not int or call < 0:
        raise ValueError("invalid_call_identifier")
    return job, call


def _observations(value):
    entries = value.get("observations")
    if not isinstance(entries, list):
        raise ValueError("invalid_observations")
    result = {}
    duplicates = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid_observation")
        index = entry.get("source_index")
        if type(index) is not int or index < 0:
            raise ValueError("invalid_source_index")
        if any(field not in entry for field in ("update_target", "update", "kind")):
            raise ValueError("missing_decision")
        if index in result:
            duplicates.add(index)
        result[index] = entry
    return result, duplicates


def _work(value):
    if "work_results" not in value:
        raise ValueError("missing_work_results")
    entries = value["work_results"]
    if entries is None:
        return None
    # Synthetic list fixtures use their ordinal position as work_index.
    if isinstance(entries, list):
        entries = {str(index): entry for index, entry in enumerate(entries)}
    if not isinstance(entries, dict):
        raise ValueError("invalid_work_results")
    result = {}
    for index, entry in entries.items():
        if not isinstance(index, str) or not index.isascii() or not index.isdecimal():
            raise ValueError("invalid_work_index")
        if str(int(index)) != index:
            raise ValueError("noncanonical_work_index")
        if entry == "unchanged":
            result[index] = False
        elif isinstance(entry, dict) and isinstance(entry.get("action"), str):
            result[index] = entry["action"] != "unchanged"
        else:
            raise ValueError("invalid_work_decision")
    return result


def _literal_equal(left, right):
    # Avoid Python's True == 1: decisions are literal JSON values, no alias resolution.
    return type(left) is type(right) and left == right


def _known_cost(value):
    return type(value) is int and value >= 0


def _usage_known(value):
    return (isinstance(value, dict)
            and all(type(value.get(field)) is int and value[field] >= 0
                    for field in ("input_tokens", "output_tokens")))


def _sum_known(values):
    return sum(values) if all(value is not None for value in values) else None


def compare_records(requests, results, *, min_recall=0.97,
                    min_recall_count_64=62, min_update_target=0.95,
                    schema_validator=None):
    if not (0 <= min_recall <= 1 and 0 <= min_update_target <= 1
            and type(min_recall_count_64) is int and 0 <= min_recall_count_64 <= 64):
        raise ValueError("invalid_threshold")
    if schema_validator is None:
        schema_validator = _common().schema_errors
    requests = list(requests)
    results = list(results)
    request_map, attempts = {}, {}
    global_errors = []
    for request in requests:
        try:
            key = _key(request)
        except ValueError:
            global_errors.append("invalid_request_identifier")
            continue
        if key in request_map:
            global_errors.append("duplicate_request")
        else:
            request_map[key] = request
    for result in results:
        try:
            key = _key(result)
        except ValueError:
            global_errors.append("invalid_result_identifier")
            continue
        attempts.setdefault(key, []).append(result)
    extra_calls = len(set(attempts) - set(request_map))
    if extra_calls:
        global_errors.append("extra_result_calls")
    if not request_map:
        global_errors.append("no_requests")
    rows = []
    for key, request in request_map.items():
        saved = attempts.get(key, [])
        costs = [item.get("actual_micro_usd") for item in saved]
        row = {"job_id": key[0], "call_index": key[1], "attempts": len(saved),
               "errors": [], "schema_ok": False, "output_known": False,
               "reference_known": False, "recall_hits": None, "recall_total": None,
               "update_target_matches": None, "update_matches": None,
               "kind_matches": None, "observation_total": None,
               "work_binary_matches": None, "work_total": None,
               "extra_observations": 0, "missing_observations": 0,
               "duplicate_observations": 0, "extra_work": 0, "missing_work": 0,
               "additional_positives": None,
               "actual_micro_usd": _sum_known([cost if _known_cost(cost) else None
                                                for cost in costs]) if saved else None,
               "cost_unknown_attempts": sum(not _known_cost(cost) for cost in costs),
               "usage_unknown_attempts": sum(not _usage_known(item.get("usage"))
                                             for item in saved),
               "error_attempts": sum(item.get("status") != "ok" for item in saved),
               "reference_micro_usd": request.get("reference_micro_usd")
               if _known_cost(request.get("reference_micro_usd")) else None}
        errors = row["errors"]
        reference = candidate = None
        schema = request.get("request_json", {}).get("schema") if isinstance(request.get("request_json"), dict) else None
        try:
            reference = _decode(request.get("reference_text"))
            if not isinstance(schema, dict) or schema_validator(reference, schema):
                errors.append("reference_schema_failure")
                reference = None
        except (ValueError, TypeError, RecursionError):
            errors.append("invalid_reference")
        if not saved:
            errors.append("missing_call")
        elif any(type(item.get("attempt")) is not int or item["attempt"] < 1 for item in saved):
            errors.append("invalid_attempt")
        elif len({item["attempt"] for item in saved}) != len(saved):
            errors.append("duplicate_attempt")
        else:
            final = max(saved, key=lambda item: item["attempt"])
            if final.get("status") != "ok":
                errors.append("final_attempt_error")
            elif not isinstance(final.get("response"), dict):
                errors.append("missing_response")
            elif final["response"].get("status") != "completed":
                errors.append("nonterminal_response")
            else:
                try:
                    candidate = _decode(final.get("text"))
                    if not isinstance(schema, dict) or schema_validator(candidate, schema):
                        errors.append("output_schema_failure")
                        candidate = None
                    else:
                        row["schema_ok"] = True
                except (ValueError, TypeError, RecursionError):
                    errors.append("invalid_output")
        try:
            if reference is not None:
                ref_obs, ref_duplicates = _observations(reference)
                ref_work = _work(reference)
                if ref_duplicates:
                    raise ValueError("duplicate_reference_index")
                row.update(reference_known=True, observation_total=len(ref_obs),
                           recall_total=sum(ref_work.values()) if ref_work is not None else 0,
                           work_total=len(ref_work) if ref_work is not None else 0)
        except ValueError:
            reference = None
            errors.append("invalid_reference_decisions")
        if reference is not None and candidate is not None:
            try:
                actual_obs, duplicates = _observations(candidate)
                actual_work = _work(candidate)
                extra = set(actual_obs) - set(ref_obs)
                missing = set(ref_obs) - set(actual_obs)
                row.update(output_known=True, extra_observations=len(extra),
                           missing_observations=len(missing), duplicate_observations=len(duplicates))
                if extra or missing or duplicates:
                    errors.append("observation_index_mismatch")
                for field in ("update_target", "update", "kind"):
                    row[field + "_matches"] = sum(
                        index in actual_obs and index not in duplicates
                        and _literal_equal(entry[field], actual_obs[index][field])
                        for index, entry in ref_obs.items())
                ref_slots, actual_slots = ref_work or {}, actual_work or {}
                row["extra_work"] = len(set(actual_slots) - set(ref_slots))
                row["missing_work"] = len(set(ref_slots) - set(actual_slots))
                if row["extra_work"] or row["missing_work"] or ((ref_work is None) != (actual_work is None)):
                    errors.append("work_index_mismatch")
                row["recall_hits"] = sum(positive and actual_slots.get(index) is True
                                         for index, positive in ref_slots.items())
                row["work_binary_matches"] = sum(index in actual_slots and positive == actual_slots[index]
                                                 for index, positive in ref_slots.items())
                row["additional_positives"] = sum(positive and ref_slots.get(index) is not True
                                                  for index, positive in actual_slots.items())
            except ValueError:
                row["output_known"] = False
                errors.append("invalid_output_decisions")
        if reference is None or candidate is None:
            errors.append("comparison_unknown")
        rows.append(row)
    total = {"calls": len(rows), "schema_ok": sum(row["schema_ok"] for row in rows),
             "output_known": sum(row["output_known"] for row in rows),
             "reference_known": sum(row["reference_known"] for row in rows),
             "error_calls": sum(bool(row["errors"]) for row in rows),
             "extra_result_calls": extra_calls, "errors": global_errors}
    for field in ("attempts", "extra_observations", "missing_observations",
                  "duplicate_observations", "extra_work", "missing_work",
                  "cost_unknown_attempts", "usage_unknown_attempts"):
        total[field] = sum(row[field] for row in rows)
    for field in ("recall_hits", "recall_total", "update_target_matches", "update_matches",
                  "kind_matches", "observation_total", "work_binary_matches", "work_total",
                  "additional_positives", "reference_micro_usd"):
        # Unknown empty populations contribute zero; unknown nonempty populations do not.
        denominator = "recall_total" if field == "recall_hits" else "observation_total" if field.endswith("_matches") and field != "work_binary_matches" else "work_total" if field == "work_binary_matches" else None
        total[field] = _sum_known([0 if row[field] is None and denominator and row[denominator] == 0
                                  else row[field] for row in rows])
    # Includes malformed/orphan result records, not just attempts attached to requests.
    total["actual_micro_usd"] = _sum_known([record.get("actual_micro_usd")
        if isinstance(record, dict) and _known_cost(record.get("actual_micro_usd")) else None for record in results]) if results else None
    total["cost_unknown_attempts"] = sum(not isinstance(record, dict) or not _known_cost(record.get("actual_micro_usd")) for record in results)
    total["usage_unknown_attempts"] = sum(not isinstance(record, dict) or not _usage_known(record.get("usage")) for record in results)
    total["attempts"] = len(results)
    total["error_attempts"] = sum(not isinstance(record, dict) or record.get("status") != "ok" for record in results)
    for row, population in [(row, attempts.get((row["job_id"], row["call_index"]), [])) for row in rows] + [(total, results)]:
        for field in ("input_tokens", "output_tokens"):
            row[field] = _sum_known([record["usage"][field] if isinstance(record, dict) and _usage_known(record.get("usage")) else None for record in population]) if population else None
    denominator, hits = total["recall_total"], total["recall_hits"]
    recall_ok = (denominator == 0 or (denominator is not None and hits is not None
        and (hits >= min_recall_count_64 if denominator == 64 else hits / denominator >= min_recall)))
    denominator, matches = total["observation_total"], total["update_target_matches"]
    target_ok = (denominator == 0 or (denominator is not None and matches is not None
                                    and matches / denominator >= min_update_target))
    total["recall_pass"] = recall_ok
    total["update_target_pass"] = target_ok
    passed = not global_errors and not total["error_calls"] and recall_ok and target_ok
    return {"calls": rows, "total": total, "passed": passed}


def _fraction(hits, total):
    if total == 0:
        return "N/A"
    if hits is None or total is None:
        return "UNKNOWN"
    return f"{hits}/{total} ({100 * hits / total:.2f}%)"


def print_report(report):
    print("call\tattempts\tknown\tschema\trecall\tupdate_target\tupdate\tkind\twork_binary\tindices(extra/missing/duplicate)\twork(extra/missing)\tadditional_positives\tactual_micro_usd\treference_micro_usd\tcost_delta_micro_usd\tinput_tokens\toutput_tokens\tunknown_cost/usage\terror_attempts\terrors")
    for row in [*report["calls"], report["total"]]:
        is_total = "calls" in row
        name = "TOTAL" if is_total else f"{json.dumps(row['job_id'], ensure_ascii=True)}:{row['call_index']}"
        actual, reference = row["actual_micro_usd"], row["reference_micro_usd"]
        value = lambda item: "UNKNOWN" if item is None else str(item)
        fields = [name, row["attempts"], f"{row['output_known']}/{row['calls']}" if is_total else int(row["output_known"]),
                  f"{row['schema_ok']}/{row['calls']}" if is_total else int(row["schema_ok"]),
                  _fraction(row["recall_hits"], row["recall_total"]),
                  *[_fraction(row[field + "_matches"], row["observation_total"]) for field in ("update_target", "update", "kind")],
                  _fraction(row["work_binary_matches"], row["work_total"]),
                  f"{row['extra_observations']}/{row['missing_observations']}/{row['duplicate_observations']}",
                  f"{row['extra_work']}/{row['missing_work']}", value(row["additional_positives"]),
                  value(actual), value(reference), value(actual - reference if actual is not None and reference is not None else None),
                  value(row["input_tokens"]), value(row["output_tokens"]),
                  f"{row['cost_unknown_attempts']}/{row['usage_unknown_attempts']}",
                  row["error_attempts"],
                  ",".join(row["errors"]) or (f"error_calls={row['error_calls']}" if is_total else "-")]
        print("\t".join(map(str, fields)))
    print(f"RESULT={'PASS' if report['passed'] else 'FAIL'} recall_pass={report['total']['recall_pass']} update_target_pass={report['total']['update_target_pass']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, default=Path("requests.jsonl"))
    parser.add_argument("--results", type=Path, default=Path("results.jsonl"))
    parser.add_argument("--min-recall", type=float, default=0.97)
    parser.add_argument("--min-recall-count-64", type=int, default=62)
    parser.add_argument("--min-update-target", type=float, default=0.95)
    args = parser.parse_args(argv)
    try:
        common = _common()
        report = compare_records(common.read_jsonl(args.requests), common.read_jsonl(args.results),
            min_recall=args.min_recall, min_recall_count_64=args.min_recall_count_64,
            min_update_target=args.min_update_target, schema_validator=common.schema_errors)
    except (OSError, ValueError, TypeError, RecursionError):
        print("RESULT=FAIL input_or_configuration_error", file=sys.stderr)
        return 2
    print_report(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
