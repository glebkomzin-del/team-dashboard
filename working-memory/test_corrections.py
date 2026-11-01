import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from corrections import correct_proposal
from memory import apply, claim, connect, overview, register, validate, ValidationError
from processor import apply_work_gate, units
from test_memory import observation, proposal

TEXT = '10:40 Oliver: Dann würde ich mit VO sprechen.\n12:09 Oliver: Ich lade euch für Montag ein.'
RULE = {'id': 'fixture-option', 'source_sha256': hashlib.sha256(TEXT.encode()).hexdigest(),
        'anchor': TEXT.splitlines()[0], 'expected_kind': 'idea', 'authority': 'user_confirmed',
        'reason': 'Nur diskutierte Möglichkeit', 'confirmed_at': '2026-09-06',
        'protected_other_anchors': ['12:09 Oliver:']}

class CorrectionTests(unittest.TestCase):
    def candidate(self, **changes):
        return proposal(observation(owner='Oliver', quotes=[RULE['anchor']], due_text=None,
                                    work_gate={'verdict': 'supported'}, **changes))

    def test_user_correction_overrides_supported_model_and_preserves_input(self):
        original = self.candidate(); before = copy.deepcopy(original)
        corrected = correct_proposal(original, TEXT, [RULE])
        item = validate(corrected, TEXT, set())[0]
        self.assertFalse(item['creates_work']); self.assertEqual(item['kind'], 'idea')
        self.assertEqual(original, before)
        self.assertEqual(item['human_corrections'][0]['previous_kind'], 'commitment')

    def test_changed_source_or_unrelated_quote_does_not_inherit_correction(self):
        for transcript, quotes in ((TEXT + '\nCorrection', [RULE['anchor']]), (TEXT, [TEXT.splitlines()[1]])):
            p = self.candidate(); p['observations'][0]['quotes'] = quotes
            self.assertEqual(correct_proposal(p, transcript, [RULE])['observations'][0]['kind'], 'commitment')

    def test_mixed_evidence_requires_split_without_erasing_other_promise(self):
        p = self.candidate(); p['observations'][0]['quotes'] = TEXT.splitlines()
        o = validate(correct_proposal(p, TEXT, [RULE]), TEXT, set())[0]
        self.assertEqual(o['kind'], 'commitment'); self.assertTrue(o['required_review'])
        self.assertFalse(o['creates_work'])

    def test_reducer_applies_correction_even_if_caller_bypasses_processor(self):
        with tempfile.TemporaryDirectory() as folder:
            rules = Path(folder) / 'rules.json'; rules.write_text(json.dumps({'corrections': [RULE]}))
            db = connect(Path(folder) / 'db.sqlite')
            try:
                job = register(db, source_id='fixture', event_date='2026-07-15', title='Fixture', transcript=TEXT)
                with patch('corrections.RULES', rules):
                    apply(db, job, claim(db, job), self.candidate(), model='fixture')
                self.assertEqual(overview(db)['waiting'], [])
                self.assertEqual(json.loads(db.execute('SELECT proposal_json FROM runs').fetchone()[0])['observations'][0]['kind'], 'commitment')
            finally: db.close()

    def test_model_cannot_forge_user_attribution(self):
        p = self.candidate(human_corrections=[{'authority': 'user_confirmed'}])
        self.assertNotIn('human_corrections', correct_proposal(p, TEXT, [])['observations'][0])

    def test_gate_coverage_and_evidence_are_checked(self):
        with self.assertRaises(ValidationError): apply_work_gate(self.candidate(), [], units(TEXT))
        with self.assertRaises(ValidationError):
            apply_work_gate(self.candidate(), [{'index': 0, 'verdict': 'supported', 'evidence_ids': ['U9999']}], units(TEXT))

    def test_gate_rejection_blocks_work_but_keeps_knowledge(self):
        p = apply_work_gate(self.candidate(), [{'index': 0, 'verdict': 'unsupported', 'reason': 'Option', 'evidence_ids': ['U0001']}], units(TEXT))
        self.assertFalse(validate(p, TEXT, set())[0]['creates_work'])

if __name__ == '__main__': unittest.main()
