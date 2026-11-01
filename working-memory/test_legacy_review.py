import copy
import sqlite3
import unittest

from legacy_review import prepare, validate_review, canonical, digest
from memory import ValidationError


class LegacyReviewTests(unittest.TestCase):
    def setUp(self):
        self.archive = sqlite3.connect(':memory:')
        self.archive.row_factory = sqlite3.Row
        self.archive.execute('CREATE TABLE documents(id,source_id,event_date,title,body_hash,body)')
        self.text = '00:01 Gleb: Ich sende den Bericht morgen.'
        self.archive.execute('INSERT INTO documents VALUES (?,?,?,?,?,?)',
                             ('doc','drive:x','2026-06-01','Bericht',digest(self.text),self.text))
        self.item = {'id':'old-id','entity_type':'todo','status':'pending','source':'x',
                     'payload':{'meeting_date':'2026-06-01','title':'Bericht senden'}}
        self.source = prepare({'inbox_items':[self.item]},self.archive)['sources'][0]
        self.review = {'source_id':'drive:x','body_sha256':digest(self.text),
                       'reviewer':'codex_direct_review','review_notes':'Explicit promise checked in original.',
                       'coverage_notes':[], 'observations':[{
                           'kind':'commitment','matter':'Bericht','matter_id':None,'title':'Bericht senden',
                           'claim':'Gleb sendet morgen den Bericht.','owner':'Gleb','due_text':'morgen',
                           'commitment_strength':'explicit','condition_text':None,'update':'none',
                           'update_target':None,'evidence_ids':['U0001'],'state_evidence_ids':[],
                           'work_state':'open','uncertainty':None,'action_uncertainty':None,'required_review':False}],
                       'decisions':[{'legacy_id':'old-id','row_sha256':digest(canonical(self.item)),
                                     'disposition':'commitment','observation_index':0,'reason':'Explicit original promise.'}]}

    def tearDown(self):
        self.archive.close()

    def check(self, review=None):
        return validate_review(self.source,review or self.review,self.archive)

    def test_coverage_keeps_original_identity_and_exact_quotes(self):
        result=self.check()
        self.assertEqual(result['item_count'],1)
        self.assertEqual(result['observations'][0]['legacy_ids'],['old-id'])
        self.assertEqual(result['observations'][0]['quotes'],[self.text])
        self.assertEqual(result['new_work'],1)

    def test_omitted_item_cannot_pass_as_complete(self):
        self.review['decisions']=[]
        with self.assertRaises(ValidationError):self.check()

    def test_changed_item_requires_new_review(self):
        self.review['decisions'][0]['row_sha256']='changed'
        with self.assertRaises(ValidationError):self.check()

    def test_changed_source_and_multiple_versions_are_not_silently_selected(self):
        self.archive.execute('UPDATE documents SET body=?',('changed',))
        with self.assertRaises(ValidationError):self.check()
        with self.assertRaises(ValidationError):prepare({'inbox_items':[self.item]},self.archive)

    def test_unknown_quotes_and_invented_due_dates_rejected(self):
        for field,value in [('evidence_ids',['U9999']),('due_text','2026-06-02')]:
            review=copy.deepcopy(self.review);review['observations'][0][field]=value
            with self.assertRaises(ValidationError):self.check(review)

    def test_duplicate_only_cannot_create_hidden_work(self):
        self.review['decisions'][0]['disposition']='duplicate'
        with self.assertRaises(ValidationError):self.check()

    def test_later_source_progress_requires_separate_existing_identity(self):
        observation=copy.deepcopy(self.review['observations'][0])
        observation.update(kind='status',update='progress',update_target='existing-work',
                           commitment_strength='not_applicable',due_text=None)
        self.review['observations'].append(observation)
        self.review['source_updates']=[{'observation_index':1,'target_id':'existing-work',
                                       'reason':'Later original explicitly advances the reviewed promise.'}]
        result=validate_review(self.source,self.review,self.archive,{'existing-work'})
        self.assertEqual(result['new_work'],1)
        self.assertEqual(result['item_count'],1)
        self.assertEqual(result['observations'][1]['update_target'],'existing-work')
        for change in ('unknown_target','new_task','duplicate_observation','missing_reason','missing_old_item'):
            review=copy.deepcopy(self.review)
            if change=='unknown_target':review['observations'][1]['update_target']='unreviewed'
            elif change=='new_task':review['observations'][1].update(update='none',update_target=None,kind='commitment',commitment_strength='explicit')
            elif change=='duplicate_observation':review['source_updates'].append(copy.deepcopy(review['source_updates'][0]))
            elif change=='missing_reason':review['source_updates'][0]['reason']=''
            else:review['decisions']=[]
            with self.subTest(change=change),self.assertRaises(ValidationError):
                validate_review(self.source,review,self.archive,{'existing-work'})

    def test_supplemental_completion_needs_state_evidence(self):
        observation=copy.deepcopy(self.review['observations'][0])
        observation.update(kind='status',update='done',update_target='existing-work',commitment_strength='not_applicable')
        self.review['observations'].append(observation)
        self.review['source_updates']=[{'observation_index':1,'target_id':'existing-work','reason':'Review'}]
        with self.assertRaises(ValidationError):validate_review(self.source,self.review,self.archive,{'existing-work'})

    def test_composite_item_split_keeps_provenance_and_rejects_hidden_or_stale_work(self):
        self.text += '\n00:02 Thomas: Ich prüfe den Entwurf.'
        self.archive.execute('UPDATE documents SET body=?,body_hash=?',(self.text,digest(self.text)))
        self.item['payload']['title']='Bericht senden und Entwurf prüfen'
        self.source=prepare({'inbox_items':[self.item]},self.archive)['sources'][0]
        self.review['body_sha256']=digest(self.text)
        self.review['decisions'][0]['row_sha256']=digest(canonical(self.item))
        obs=copy.deepcopy(self.review['observations'][0])
        obs.update(owner='Thomas',title='Entwurf prüfen',claim='Thomas übernimmt die Prüfung.',
                   due_text=None,evidence_ids=['U0002'])
        self.review['observations'].append(obs)
        self.review['item_splits']=[{'legacy_id':'old-id','row_sha256':digest(canonical(self.item)),
            'observation_index':1,'reason':'Composite retained item contains two separately evidenced owners.'}]
        result=self.check()
        self.assertEqual(result['item_count'],1)
        self.assertEqual(result['new_work'],2)
        self.assertEqual(result['observations'][1]['legacy_ids'],['old-id'])
        self.assertEqual(result['observations'][1]['quotes'],['00:02 Thomas: Ich prüfe den Entwurf.'])
        for change in ('missing_provenance','unknown_item','changed_item','duplicate_index','duplicate_promise','blank_reason','not_work','unknown_quote','dismissed_parent'):
            review=copy.deepcopy(self.review)
            if change=='missing_provenance':review.pop('item_splits')
            elif change=='unknown_item':review['item_splits'][0]['legacy_id']='not-retained'
            elif change=='changed_item':review['item_splits'][0]['row_sha256']='stale'
            elif change=='duplicate_index':review['item_splits'][0]['observation_index']=0
            elif change=='duplicate_promise':review['observations'][1]=copy.deepcopy(review['observations'][0])
            elif change=='blank_reason':review['item_splits'][0]['reason']=' '
            elif change=='not_work':review['observations'][1].update(kind='fact',owner=None,commitment_strength='not_applicable',work_state='not_applicable')
            elif change=='unknown_quote':review['observations'][1]['evidence_ids']=['U9999']
            else:
                review['decisions'][0].update(disposition='dismiss',observation_index=None,evidence_ids=['U0001'])
            with self.subTest(change=change),self.assertRaises(ValidationError):self.check(review)

    def test_no_silent_change_to_human_approved_item(self):
        self.item['status']='approved'
        with self.assertRaises(ValidationError):prepare({'inbox_items':[self.item]},self.archive)

    def test_date_is_source_date_and_may_actions_stay_excluded(self):
        self.item['created_at']='2026-08-31'
        self.item['payload']['meeting_date']='2026-05-31'
        result=prepare({'inbox_items':[self.item]},self.archive)
        self.assertEqual(result['item_count'],0)
        self.assertEqual(result['excluded']['before_cutoff'],1)


if __name__=='__main__':unittest.main()
