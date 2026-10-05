#!/usr/bin/env python3
"""Offline, fixed three-case acceptance against private original evidence."""
import argparse
import hashlib
import json
from pathlib import Path

from relation_adapter import ID_FIELDS, admit, schema_for, _hash

CANDIDATES = {"A": ["real_pc_check", "real_csv_upload", "real_priority_feedback"],
              "B": ["synthetic_stock_check"], "C": ["synthetic_topic_a"]}


def row(action_id, relation, earlier, later, obj, action, prerequisite=(), replacement=(), competing=()):
    return {"action_id": action_id, "relation": relation, "earlier_ids": list(earlier),
            "later_ids": list(later), "object_ids": list(obj), "action_ids": list(action),
            "prerequisite_ids": list(prerequisite), "replacement_ids": list(replacement),
            "competing_ids": list(competing)}


TYPED = {"cases": [
    {"case_id": "A", "relations": [
        row("real_pc_check", "replaced", ("U085", "U088"), ("U134",),
            ("U085", "U134"), ("U134",), ("U085",), ("U134",)),
        row("real_csv_upload", "confirmed", ("U134",), ("U161", "U164"),
            ("U134", "U164"), ("U164",), ("U161", "U164")),
        row("real_priority_feedback", "confirmed", ("U178",), ("U180", "U181"),
            ("U178", "U180"), ("U180", "U181"), ("U178",)),
    ]},
    {"case_id": "B", "relations": [
        row("synthetic_stock_check", "independent", ("U001",), ("U002",),
            ("U001", "U002"), ("U001",), ("U001",)),
    ]},
    {"case_id": "C", "relations": [
        row("synthetic_topic_a", "unclear", ("U001",), ("U003",),
            (), (), competing=("U002", "U003")),
    ]},
]}


def run(source_path, response_path, expected_path):
    response_bytes=response_path.read_bytes()
    assert hashlib.sha256(response_bytes).hexdigest()=="a33159426b1ec6324eab7821f787637df2bd4b3582b588c76a1a3a4b77b98b17"
    source=json.loads(source_path.read_text())
    expected=json.loads(expected_path.read_text())
    assert set(source)==set(CANDIDATES)
    assert expected["cases"]["A"]["real_pc_check"]=="expressly_withdrawn"
    assert expected["cases"]["A"]["real_csv_upload"]=="confirmed"
    assert expected["cases"]["A"]["real_priority_feedback"]=="confirmed"
    assert expected["cases"]["B"]["synthetic_stock_check"]=="independent"
    assert expected["cases"]["C"]["synthetic_topic_a"]=="unclear"
    schema=schema_for(source,CANDIDATES)
    assert not ({"final_statement", "quote", "owner", "condition", "summary", "tasks"}
                & set(json.dumps(schema).split('"')))
    source_hash=_hash(source)
    verified={(case["case_id"],r["action_id"]):{k:r[k] for k in ("relation",*ID_FIELDS)}
              for case in TYPED["cases"] for r in case["relations"]}
    admitted=admit(TYPED,source,CANDIDATES,verified,source_hash)
    outcomes={(x["case_id"],x["action_id"]):x["decision"] for x in admitted["actions"]}
    assert outcomes[("A","real_pc_check")] == "exclude_new_candidate_only"
    assert outcomes[("A","real_csv_upload")] == "no_mutation_human_decision_preserved"
    assert outcomes[("A","real_priority_feedback")] == "no_mutation_human_decision_preserved"
    assert outcomes[("B","synthetic_stock_check")] == "no_mutation_human_decision_preserved"
    assert outcomes[("C","synthetic_topic_a")] == "visible_review_no_automatic_work"
    assert admitted["actions"][0]["evidence"]["later_ids"][0]["text"]==source["A"]["U134"]
    assert admitted["actions"][0]["source_case_sha256"]==_hash(source["A"])
    assert all(set(x)=={"case_id", "action_id", "relation", "decision", "evidence",
                        "source_case_sha256"} for x in admitted["actions"])
    old=json.loads(response_bytes)["content"][0]["text"]
    invalid=admit(json.loads(old),source,CANDIDATES,verified,source_hash)
    assert invalid["status"]=="REVIEW_REQUIRED" and all(
        x["decision"]=="visible_review_no_automatic_work" for x in invalid["actions"])
    unbound=admit(TYPED,source,CANDIDATES,expected_source_map_sha256=source_hash)
    assert all(x["decision"]=="visible_review_no_automatic_work" for x in unbound["actions"])
    wrong_source=admit(TYPED,source,CANDIDATES,verified,"0"*64)
    assert wrong_source["status"]=="REVIEW_REQUIRED"
    missing_action=json.loads(json.dumps(TYPED));missing_action["cases"][0]["relations"].pop()
    assert admit(missing_action,source,CANDIDATES,verified,source_hash)["status"]=="REVIEW_REQUIRED"
    missing_object=json.loads(json.dumps(TYPED));missing_object["cases"][0]["relations"][0]["object_ids"]=[]
    assert admit(missing_object,source,CANDIDATES,verified,source_hash)["status"]=="REVIEW_REQUIRED"
    missing_prerequisite=json.loads(json.dumps(TYPED));missing_prerequisite["cases"][0]["relations"][0]["prerequisite_ids"]=[]
    assert admit(missing_prerequisite,source,CANDIDATES,verified,source_hash)["status"]=="REVIEW_REQUIRED"
    human_review={"upload_work_items":0,"caroline_related":2}
    before=dict(human_review)
    assert human_review==before  # The adapter receives no mutable work or history ledger.
    return {"result":"OFFLINE_TYPED_CONTRACT_PASS","source_map_sha256":source_hash,
            "schema_sha256":_hash(schema),"actual_response":"WHOLE_RESPONSE_INVALID_REVIEW",
            "typed_case_outcomes":{f"{case}/{action}":decision for (case,action),decision in outcomes.items()},
            "historical_work_mutations":0,"provider_calls":0}


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--source-map",type=Path,required=True)
    parser.add_argument("--actual-response",type=Path,required=True)
    parser.add_argument("--expected",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.source_map,args.actual_response,args.expected),sort_keys=True))
