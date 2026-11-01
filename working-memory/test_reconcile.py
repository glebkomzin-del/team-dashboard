import unittest
from memory import ValidationError, validate
from reconcile import observations, partitions, prompt


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.work = [{'id': 'old-invitation', 'matter': 'Finance', 'owner': 'Oliver', 'status': 'open'}]
        self.text = 'Oliver: Danke, dass ihr zu dieser Abstimmung gekommen seid.'
        self.originals = {'U1': {'text': self.text}}
        self.result = {'work_id': 'old-invitation', 'action': 'done', 'title': 'Abstimmung durchgeführt',
                       'claim': 'Die konkrete Abstimmung findet statt.', 'reason': 'Gleicher Gegenstand und Beteiligte.',
                       'evidence_ids': ['U1'], 'owner': None, 'due_text': None}

    def test_existing_work_completion_keeps_identity_and_exact_evidence(self):
        result = observations(self.work, [self.result], self.originals)
        checked = validate({'observations': result, 'coverage_notes': []}, self.text, {'old-invitation'})
        self.assertEqual(checked[0]['update_target'], 'old-invitation')
        self.assertEqual(checked[0]['update'], 'done')
        self.assertFalse(checked[0]['creates_work'])
        self.assertEqual(checked[0]['state_quotes'], [self.text])

    def test_every_existing_id_must_be_accounted_for(self):
        for results in ([], [self.result, self.result], [{**self.result, 'work_id': 'other-project'}]):
            with self.assertRaisesRegex(ValidationError, 'coverage'):
                observations(self.work, results, self.originals)

    def test_absence_and_ambiguity_do_not_close_work(self):
        self.assertEqual(observations(self.work, [{**self.result, 'action': 'unchanged', 'evidence_ids': []}], self.originals), [])
        item = observations(self.work, [{**self.result, 'action': 'ambiguous'}], self.originals)[0]
        self.assertEqual(item['update'], 'none')
        self.assertTrue(item['required_review'])
        self.assertIsNotNone(item['action_uncertainty'])

    def test_unquoted_deadline_or_hidden_owner_change_is_rejected(self):
        for change in ({'action': 'date_changed', 'due_text': 'morgen'}, {'owner': 'Caroline'}, {'action': 'reopened'}):
            with self.assertRaises(ValidationError):
                observations(self.work, [{**self.result, **change}], self.originals)

    def test_lifecycle_partition_preserves_every_identity_under_budget(self):
        work=[{**self.work[0], 'id':f'work-{index}', 'original_commitment_evidence':['x'*120]} for index in range(9)]
        meeting={'title':'Prüfung','meeting_date':'2026-09-08','raw_transcript':self.text}
        batches=partitions(meeting,work,self.originals,2900)
        self.assertGreater(len(batches),1)
        self.assertEqual([item['id'] for batch in batches for item in batch],[item['id'] for item in work])
        self.assertTrue(all(len(prompt(meeting,batch,self.originals))<=2900 for batch in batches))

    def test_lifecycle_partition_also_bounds_response_cardinality(self):
        work=[{**self.work[0], 'id':f'work-{index}'} for index in range(121)]
        meeting={'title':'Prüfung','meeting_date':'2026-09-08','raw_transcript':self.text}
        batches=partitions(meeting,work,self.originals,100000,max_items=50)
        self.assertEqual([len(batch) for batch in batches],[50,50,21])
        self.assertEqual([item['id'] for batch in batches for item in batch],[item['id'] for item in work])

    def test_invalid_lifecycle_item_budget_is_rejected(self):
        meeting={'title':'Prüfung','meeting_date':'2026-09-08','raw_transcript':self.text}
        for value in (0, True, 1.5):
            with self.assertRaisesRegex(ValidationError,'item budget'):
                partitions(meeting,self.work,self.originals,100000,max_items=value)

    def test_single_oversized_identity_fails_without_truncation(self):
        work=[{**self.work[0], 'original_commitment_evidence':['x'*2000]}]
        meeting={'title':'Prüfung','meeting_date':'2026-09-08','raw_transcript':self.text}
        with self.assertRaisesRegex(ValidationError,'Single lifecycle identity'):
            partitions(meeting,work,self.originals,700)


if __name__ == '__main__':
    unittest.main()
