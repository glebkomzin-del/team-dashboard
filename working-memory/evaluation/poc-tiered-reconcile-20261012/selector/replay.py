"""Offline replay. Prints counts and permitted metadata only, never input texts."""

import argparse
import json
import math
import pickle
import sys
from pathlib import Path

# -I omits the script directory. Load only this explicitly anchored sibling.
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from selector import query_text, select


class PrimitiveUnpickler(pickle.Unpickler):
    """Permit primitive containers, never imports or pickle executable objects."""

    def find_class(self, module, name):
        raise ValueError("Pickle contains a non-primitive object")

    def persistent_load(self, pid):
        raise ValueError("Pickle contains a persistent reference")


def decode_vector(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, (list, tuple)):
        raise ValueError("Invalid vector container")
    vector = tuple(float(x) for x in value)
    if not all(math.isfinite(x) for x in vector):
        raise ValueError("Invalid vector component")
    return vector


class Embeddings:
    def __init__(self, vectors):
        self.documents = [(body, {line.strip() for line in body.splitlines()[:3]}, decode_vector(value))
                          for body, value in vectors["workdocs"].items()]
        self.queries = vectors["queries"]
        self.cache = {}
        self.mapping = {"missing_work": 0, "multiple_work": 0,
                        "unresolved_multiple_work": 0, "missing_query": 0}

    def candidate(self, work):
        key = ((work.get("title") or "").strip(), (work.get("claim") or "").strip())
        if key not in self.cache:
            title, claim = key
            matches = [(body, vector) for body, title_lines, vector in self.documents
                       if title and title in title_lines]
            ambiguous = len(matches) > 1
            unresolved = False
            if ambiguous:
                claim_matches = [(body, vector) for body, vector in matches
                                 if claim[:60] and claim[:60] in body]
                if len(claim_matches) == 1:
                    matches = claim_matches
                else:
                    unresolved = True
                    matches = []
            self.cache[key] = (matches[0][1] if matches else None, ambiguous, unresolved)
        vector, ambiguous, unresolved = self.cache[key]
        self.mapping["missing_work"] += vector is None
        self.mapping["multiple_work"] += ambiguous
        self.mapping["unresolved_multiple_work"] += unresolved
        return vector

    def query(self, observation):
        text = query_text(observation)
        value = self.queries.get(json.dumps([text], ensure_ascii=False))
        if value is None:
            value = self.queries.get(json.dumps([text], ensure_ascii=True))
        self.mapping["missing_query"] += value is None
        return decode_vector(value)


def used_indices(call):
    targets = {obs.get("update_target") for obs in call["obs_out"]
               if isinstance(obs.get("update_target"), str)}
    results = call["work_results"]
    used = set()
    for i, work in enumerate(call["work"]):
        key = str(work["work_index"])
        if (key in results and results[key] != "unchanged") or work["id"] in targets:
            used.add(i)
    return used


def unknown_usage_indices(call):
    """Absent results carry no usage label unless an update target proves use."""
    utilized = used_indices(call)
    return {i for i, work in enumerate(call["work"])
            if str(work["work_index"]) not in call["work_results"] and i not in utilized}


def retained(stats, A, k):
    return {i for i, (age, emb, lex) in enumerate(zip(
        stats["ages"], stats["emb_ranks"], stats["lex_ranks"]))
        if age <= A or (emb is not None and emb < k) or (lex is not None and lex < k)}


def metrics(records, A, k):
    total = used = kept = found = unknown = unknown_kept = 0
    missed = []
    for call, stats, utilized in records:
        selected = retained(stats, A, k)
        total += len(call["work"])
        used += len(utilized)
        kept += len(selected)
        found += len(selected & utilized)
        unlabeled = set(stats.get("unknown_usage_indices", []))
        unknown += len(unlabeled)
        unknown_kept += len(selected & unlabeled)
        for i in sorted(utilized - selected):
            work = call["work"][i]
            # Exact allowlist: no title, claim, job id, body or exception text.
            missed.append({"alias": work["id"], "age_days": stats["ages"][i],
                           "status": work.get("status"), "emb_rank": stats["emb_ranks"][i],
                           "lex_rank": stats["lex_ranks"][i]})
    return {"candidates": total, "used": used, "retained": kept,
            "recall_pct": 100 * found / used if used else None,
            "retained_pct": 100 * kept / total if total else 0.0,
            "missed_used": missed, "unknown_usage": unknown, "unknown_retained": unknown_kept}


def load_calls(path):
    calls, errors, lines = [], 0, 0
    required = {"meeting_date", "job_id", "work", "obs_in", "obs_out", "work_results"}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            lines += 1
            row = json.loads(line)
            if not required <= row.keys():
                if "error" in row and "work" not in row:
                    errors += 1
                    continue
                raise ValueError("Incomplete call schema")
            calls.append(row)
    return calls, lines, errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calls", type=Path, required=True)
    parser.add_argument("--vectors", type=Path, required=True)
    parser.add_argument("--A", type=int, default=21)
    parser.add_argument("--k", type=int, default=5)
    args = parser.parse_args(argv)
    if args.A < 0 or args.k < 0:
        parser.error("A and k must be nonnegative")
    try:
        calls, lines, errors = load_calls(args.calls)
        with args.vectors.open("rb") as handle:
            vectors = PrimitiveUnpickler(handle).load()
        embeddings = Embeddings(vectors)
        records, all_records = [], []
        for call in calls:
            result = select(call["work"], call["obs_in"], call["meeting_date"], args.A, args.k,
                            embeddings.candidate, embeddings.query)
            result["stats"]["unknown_usage_indices"] = sorted(unknown_usage_indices(call))
            record = (call, result["stats"], used_indices(call))
            all_records.append(record)
            # Exact historical recall2.py cohort, disclosed beside raw totals.
            if call["work"] and call["obs_in"]:
                records.append(record)
        summary = metrics(records, args.A, args.k)
        summary.update({"input_lines": lines, "calls": len(records), "complete_calls": len(calls),
                        "error_calls": errors, "excluded_empty_calls": len(calls) - len(records),
                        "excluded_empty_candidates": sum(len(c["work"]) for c in calls
                                                         if not c["work"] or not c["obs_in"]),
                        "all_complete_metrics": metrics(all_records, args.A, args.k),
                        "A": args.A, "k": args.k, "embedding_mapping": embeddings.mapping})
        print(json.dumps(summary, ensure_ascii=True, sort_keys=True))
        print("A k retained candidates used recall_pct retained_pct missed_used")
        for A in (0, 7, 14, 21, 30, 45):
            for k in (0, 3, 5, 8, 12):
                m = metrics(records, A, k)
                recall = "n/a" if m["recall_pct"] is None else f'{m["recall_pct"]:.6f}'
                print(f'{A} {k} {m["retained"]} {m["candidates"]} {m["used"]} '
                      f'{recall} {m["retained_pct"]:.6f} {len(m["missed_used"])}')
        return 0
    except Exception:
        # Never print exception payloads: malformed data may contain meeting text.
        print("Replay failed: invalid/unreadable input or incompatible vectors.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
