"""Preflight only: authored expected fixture, omissions and invalid citations."""
import json
import unittest
from pathlib import Path
from validate import inspect, PRIVATE

class ProbeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads((PRIVATE / 'expected-private.json').read_text())
        cls.sources = json.loads((PRIVATE / 'source-map.json').read_text())

    def fixture(self):
        specs = [
            ('A', 'real_pc_check', 'speaker A', 'regular PC France check', 'while used only for POC France', [('U085', 'solange wir das hier nur für POC Frankreich machen'), ('U088', 'alle 2 Wochen')], [('U134', 'nicht regelmäßig checken')], 'expressly_withdrawn', 'Same mapping/check topic; the speaker expressly replaces the cadence with one-time upload.', 'No recurring PC check; one-time mapping upload and notification remain.', False),
            ('A', 'real_csv_upload', 'speaker B', 'CSV upload', 'after receiving CSV', [('U134', 'einmal das Mapping hochladen')], [('U164', 'wenn ich von euch die CSV krieche')], 'confirmed', 'Later condition concerns the same upload and names the input dependency.', 'Upload can proceed when the CSV arrives.', False),
            ('A', 'real_priority_feedback', 'speaker C', 'discuss timing and report back', 'another person must prioritize the pipeline', [('U178', 'die muss dann priorisieren')], [('U180', 'gib mir bitte mal Feedback dazu'), ('U181', 'Ja.')], 'confirmed', 'The speaker confirms the request for feedback after discussing priority.', 'Priority discussion and feedback remain; date is conditional.', False),
            ('B', 'synthetic_stock_check', 'Mara', 'stock report check', '', [('U001', 'check the stock report every Friday')], [('U002', 'warehouse inventory needs no regular check')], 'independent', 'Warehouse inventory is a different object from the stock report.', 'Mara weekly stock-report check remains stated.', False),
            ('C', 'synthetic_topic_a', 'Mara', 'PC report check', '', [('U001', 'check the PC report every Friday')], [('U003', 'That need not be checked regularly')], 'unclear', 'That could refer to either the PC report or the stock report.', 'Review referent before cancelling either check.', True),
        ]
        cases = {}
        for cid, aid, owner, obj, cond, earlier, later, rel, reason, final, review in specs:
            cases.setdefault(cid, []).append({'action_id': aid, 'earlier_owner': owner, 'earlier_object': obj,
                'earlier_condition': cond, 'earlier_evidence': [{'unit_id': u, 'quote': q} for u, q in earlier],
                'later_evidence': [{'unit_id': u, 'quote': q} for u, q in later], 'relation': rel,
                'object_link_reason': reason, 'final_statement': final, 'review_required': review})
        return {'cases': [{'case_id': cid, 'relations': relations} for cid, relations in cases.items()]}

    def errors(self, fixture):
        return inspect(fixture, self.expected, self.sources)

    def test_authored_fixture(self):
        self.assertEqual([], self.errors(self.fixture()))

    def test_missing_case_and_action(self):
        fixture = self.fixture(); fixture['cases'].pop()
        self.assertIn('case omission', self.errors(fixture))
        fixture = self.fixture(); fixture['cases'][0]['relations'].pop()
        self.assertIn('A: action omission', self.errors(fixture))

    def test_unknown_and_ungrounded_unit(self):
        fixture = self.fixture(); fixture['cases'][0]['relations'][0]['later_evidence'][0]['unit_id'] = 'U999'
        self.assertTrue(any('unknown later ID' in e for e in self.errors(fixture)))
        fixture = self.fixture(); fixture['cases'][0]['relations'][0]['later_evidence'][0]['unit_id'] = 'U133'
        self.assertTrue(any('ungrounded later quote' in e for e in self.errors(fixture)))

    def test_additional_original_context_allowed(self):
        fixture = self.fixture()
        line = self.sources['A']['U128']
        fixture['cases'][0]['relations'][0]['earlier_evidence'].append({'unit_id': 'U128', 'quote': line[:32]})
        self.assertEqual([], self.errors(fixture))

    def test_required_positive_anchor_cannot_be_omitted(self):
        fixture = self.fixture()
        fixture['cases'][0]['relations'][0]['later_evidence'][0] = {'unit_id': 'U128', 'quote': self.sources['A']['U128'][:32]}
        self.assertTrue(any('missing required later unit' in e for e in self.errors(fixture)))

    def test_no_expected_relation_in_request_or_schema_labels(self):
        request = json.loads((PRIVATE / 'request.json').read_text())
        serialized = json.dumps(request, ensure_ascii=False)
        for leaked_label in ('unrelated_negation', 'ambiguous_referent', 'real_original'):
            self.assertNotIn(leaked_label, serialized)
        self.assertEqual({'A', 'B', 'C'}, {c['case_id'] for c in json.loads(request['prompt'].split('INPUT CASES AND ORIGINAL UNITS:\n', 1)[1])['cases']})
        self.assertEqual(['A', 'B', 'C'], request['schema']['properties']['cases']['items']['properties']['case_id']['enum'])

    def test_missing_positive_quote_and_wrong_outcome(self):
        fixture = self.fixture(); fixture['cases'][0]['relations'][0]['later_evidence'][0]['quote'] = ''
        self.assertTrue(any('ungrounded later quote' in e for e in self.errors(fixture)))
        fixture = self.fixture(); fixture['cases'][0]['relations'][0]['relation'] = 'confirmed'
        self.assertTrue(any('expected relation mismatch' in e for e in self.errors(fixture)))

    def test_unknown_requires_review(self):
        fixture = self.fixture(); fixture['cases'][2]['relations'][0]['review_required'] = False
        self.assertTrue(any('expected review flag mismatch' in e for e in self.errors(fixture)))

if __name__ == '__main__':
    unittest.main()
