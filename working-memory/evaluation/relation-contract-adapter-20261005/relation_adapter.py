"""Original-ID-only relation proposal and conservative admission for one new meeting.

The model supplies no prose. A separately verified binding is required before a
relation can affect a *new* candidate; without it the candidate remains in review.
"""
import hashlib
import json
import re

RELATIONS = {"expressly_withdrawn", "replaced", "independent", "confirmed", "unclear"}
ID_FIELDS = ("earlier_ids", "later_ids", "object_ids", "action_ids",
             "prerequisite_ids", "replacement_ids", "competing_ids")
ROW_FIELDS = {"action_id", "relation", *ID_FIELDS}
UNIT_ID = re.compile(r"U[0-9]{3,5}\Z")


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _ids(value, original, label):
    if not isinstance(value, list) or len(value) != len(set(value)) or any(
            not isinstance(item, str) or not UNIT_ID.fullmatch(item) or item not in original for item in value):
        raise ValueError(f"invalid {label} original IDs")
    return value


def _review(candidates, reason, source_hash):
    return {"status": "REVIEW_REQUIRED", "reason": reason, "source_map_sha256": source_hash,
            "actions": [{"case_id": case, "action_id": action,
                         "decision": "visible_review_no_automatic_work"}
                        for case, actions in candidates.items() for action in actions]}


def schema_for(source_map, candidates):
    """Strict transport shape. Completion and evidence semantics are checked by admit()."""
    variants = []
    for case, actions in candidates.items():
        units = sorted(source_map[case])
        id_array = {"type": "array", "uniqueItems": True,
                    "items": {"type": "string", "enum": units}}
        row_properties = {"action_id": {"type": "string", "enum": list(actions)},
                          "relation": {"type": "string", "enum": sorted(RELATIONS)}}
        row_properties.update({name: id_array for name in ID_FIELDS})
        relation_items = {"type": "object", "additionalProperties": False,
                          "required": sorted(ROW_FIELDS), "properties": row_properties}
        variants.append({"type": "object", "additionalProperties": False,
                         "required": ["case_id", "relations"],
                         "properties": {"case_id": {"const": case},
                                        "relations": {"type": "array", "minItems": len(actions),
                                                      "maxItems": len(actions), "items": relation_items}}})
    return {"type": "object", "additionalProperties": False, "required": ["cases"],
            "properties": {"cases": {"type": "array", "minItems": len(variants),
                                    "maxItems": len(variants), "items": {"oneOf": variants}}}}


def admit(value, source_map, candidates, verified_bindings=None, expected_source_map_sha256=None):
    """Never mutates historical work; returns a decision only for a new candidate."""
    source_hash = _hash(source_map)
    verified_bindings = verified_bindings or {}
    if expected_source_map_sha256 != source_hash:
        return _review(candidates, "unbound original source map", source_hash)
    try:
        if set(value) != {"cases"} or not isinstance(value["cases"], list):
            raise ValueError("invalid response envelope")
        cases = value["cases"]
        if len(cases) != len(candidates) or {c.get("case_id") for c in cases} != set(candidates):
            raise ValueError("case coverage changed")
        result = []
        for case_value in cases:
            if set(case_value) != {"case_id", "relations"}:
                raise ValueError("free case field")
            case = case_value["case_id"]
            original = source_map[case]
            rows = case_value["relations"]
            if not isinstance(rows, list) or len(rows) != len(candidates[case]) or \
                    {r.get("action_id") for r in rows} != set(candidates[case]):
                raise ValueError("action coverage changed")
            for row in rows:
                if set(row) != ROW_FIELDS or row["relation"] not in RELATIONS:
                    raise ValueError("free or invalid relation field")
                evidence = {name: _ids(row[name], original, name) for name in ID_FIELDS}
                earlier, later = evidence["earlier_ids"], evidence["later_ids"]
                if not earlier or not later or max(int(x[1:]) for x in earlier) >= min(int(x[1:]) for x in later):
                    raise ValueError("missing or reversed original chronology")
                relation = row["relation"]
                if relation in {"expressly_withdrawn", "replaced", "confirmed"}:
                    if not evidence["object_ids"] or not evidence["action_ids"] or not evidence["prerequisite_ids"]:
                        raise ValueError("positive object, action or prerequisite proof missing")
                    if not (set(evidence["object_ids"]) & set(earlier)) or not (set(evidence["object_ids"]) & set(later)):
                        raise ValueError("object proof lacks both sides")
                    if not set(evidence["action_ids"]) <= set(later):
                        raise ValueError("action proof is not later original")
                    if relation == "replaced" and not evidence["replacement_ids"]:
                        raise ValueError("replacement action proof missing")
                    if relation != "replaced" and evidence["replacement_ids"]:
                        raise ValueError("unexpected replacement")
                elif relation == "independent":
                    if not evidence["object_ids"] or not evidence["action_ids"] or evidence["replacement_ids"]:
                        raise ValueError("independent objects not positively separated")
                    if not (set(evidence["object_ids"]) & set(earlier)) or not (set(evidence["object_ids"]) & set(later)):
                        raise ValueError("independent object proof lacks both sides")
                else:
                    if not evidence["competing_ids"] or evidence["replacement_ids"]:
                        raise ValueError("ambiguity needs competing original referents")
                key = (case, row["action_id"])
                trusted = verified_bindings.get(key)
                admitted = trusted is not None and trusted == {k: row[k] for k in ROW_FIELDS if k != "action_id"}
                decision = ("exclude_new_candidate_only" if relation in {"expressly_withdrawn", "replaced"}
                            else "no_mutation_human_decision_preserved") if admitted and relation != "unclear" \
                           else "visible_review_no_automatic_work"
                result.append({"case_id": case, "action_id": row["action_id"], "relation": relation,
                               "decision": decision,
                               "evidence": {name: [{"unit_id": unit, "text": original[unit]} for unit in ids]
                                            for name, ids in evidence.items()},
                               "source_case_sha256": _hash(original)})
        return {"status": "ADMITTED_WITH_VERIFIED_BINDINGS" if all(
                    r["decision"] != "visible_review_no_automatic_work" for r in result) else "REVIEW_REQUIRED",
                "source_map_sha256": source_hash, "actions": result}
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        return _review(candidates, str(error), source_hash)
