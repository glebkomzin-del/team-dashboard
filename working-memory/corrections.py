"""User-confirmed source interpretations, applied after every model judgment.

Exact transcript hash and verbatim evidence scope prevent a calibration from
becoming a global linguistic rule. The input proposal is retained by the ledger.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

RULES = Path(__file__).parent / 'evaluation/source-corrections.json'

def correct_proposal(proposal, transcript, rules=None):
    result = deepcopy(proposal)
    rules = json.loads(RULES.read_text())['corrections'] if rules is None else rules
    digest = hashlib.sha256(transcript.encode()).hexdigest()
    for o in result.get('observations', []):
        # This attribution can only come from local, reviewed rules.
        o.pop('human_corrections', None)
        for rule in rules:
            if rule['authority'] != 'user_confirmed' or rule['source_sha256'] != digest:
                continue
            anchor = rule['anchor']
            if anchor not in transcript or not any(anchor in q for q in o.get('quotes', [])):
                continue
            if o.get('kind') not in ('commitment', rule['expected_kind']) and o.get('update', 'none') == 'none':
                continue
            mixed = any(a in q for a in rule.get('protected_other_anchors', []) for q in o['quotes'])
            o.setdefault('human_corrections', []).append({
                'id': rule['id'], 'authority': rule['authority'], 'reason': rule['reason'],
                'confirmed_at': rule['confirmed_at'], 'anchor': anchor,
                'previous_kind': o['kind'], 'previous_claim': o['claim'],
                'previous_update': o.get('update'), 'mixed_evidence': mixed,
            })
            if mixed:
                # Do not erase a separate promise hidden in a combined proposal.
                o['required_review'] = True
                o['action_uncertainty'] = 'Aussage enthält eine korrigierte Option/Voraussetzung und eine getrennte Zusage; vor Übernahme aufteilen.'
            else:
                o['kind'] = rule['expected_kind']
                o['claim'] = rule.get('corrected_claim', rule['reason'])
                o['title'] = rule.get('corrected_title', o['title'])
                o['commitment_strength'] = 'none'
                o['update_target'] = None
                o['update'] = 'none'
                o['work_state'] = 'not_applicable'
                o['owner'] = None
                o['required_review'] = False
                o['action_uncertainty'] = None
    return result
