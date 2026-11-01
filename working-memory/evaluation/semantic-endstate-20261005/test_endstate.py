"""Synthetic references for the final source gate; no real transcript is stored here."""
import copy
import tempfile
import unittest
from pathlib import Path

from future_summary import from_value
from hybrid_index import current_source_documents
from hybrid_pipeline import apply_endstate, resolve_v10
from memory import ValidationError, apply, claim, connect, overview, register, validate
from processor import apply_work_gate, units


TEXT = '\n'.join([
    'Jonas: Ich werde die PoC-Daten alle zwei Wochen prüfen.',
    'Jonas: Das war wegen der fehlenden Attribute gedacht.',
    'Jonas: Wir brauchen keine regelmäßige Prüfung; nur das Mapping einmal hochladen.',
    'Jonas: Ich lade das Mapping einmal hoch.',
    'Gleb: Ich gebe Caroline die besprochene Rückmeldung.',
])


def observation(title, claim, owner, evidence):
    return {'matter':'PoC', 'matter_id':None, 'kind':'commitment', 'title':title,
            'claim':claim, 'owner':owner, 'commitment_strength':'explicit',
            'due_text':None, 'update_target':None, 'update':'none', 'uncertainty':None,
            'required_review':False, 'evidence_ids':[evidence], 'action_uncertainty':None,
            'condition_text':None, 'work_state':'open', 'state_evidence_ids':[],
            'assignment_score':2, 'change_score':2, 'confidence_reason':'Ausdrückliche Zusage'}


def fixture():
    originals=units(TEXT)
    raw={'coverage_notes':[], 'meeting_display_title':None,
         'meeting_summary':[
             {'text':'Jonas prüft die Daten künftig alle zwei Wochen.','evidence_ids':['U0001']},
             {'text':'Jonas lädt das Mapping einmal hoch; Gleb gibt Caroline Rückmeldung.',
              'evidence_ids':['U0004','U0005']}],
         'observations':[
             observation('Regelmäßige Prüfung','Jonas prüft die Daten alle zwei Wochen.','Jonas','U0001'),
             observation('Mapping hochladen','Jonas lädt das Mapping einmal hoch.','Jonas','U0004'),
             observation('Caroline antworten','Gleb gibt Caroline Rückmeldung.','Gleb','U0005')]}
    proposal=resolve_v10(raw,originals)
    verdicts=[{'index':i,'verdict':'supported','reason':'Originalzusage','evidence_ids':['U0001','U0003'] if i==0 else [f'U000{i+3}'],
               'duplicate_of':None,'due_role':'none','action_uncertainty':None} for i in range(3)]
    verdicts[0]['verdict']='withdrawn'
    gated=apply_work_gate(proposal,verdicts,originals)
    for item in gated['observations']:
        for evidence_id in item['work_gate']['evidence_ids']:
            unit=originals[evidence_id]
            if not any(s['start']==unit['start'] for s in item['source_spans']):
                item['source_spans'].append({'start':unit['start'],'end':unit['end'],'quote':unit['text']})
    decision={'verdicts':verdicts,
              'endstate':[{'index':0,'status':'withdrawn','reason':'Dieselbe Datenprüfung wurde später ausdrücklich auf den einmaligen Upload begrenzt.',
                           'earlier_evidence_ids':['U0001'],'later_evidence_ids':['U0003'],
                           'final_claim':'Die regelmäßige PoC-Datenprüfung wurde im Meeting verworfen; es bleibt der einmalige Mapping-Upload.'},
                          *[{'index':i,'status':'unchanged','reason':'Eigenständige Zusage',
                             'earlier_evidence_ids':[],'later_evidence_ids':[],'final_claim':None} for i in (1,2)]],
              'final_summary':[{'index':0,'status':'corrected','reason':'Der spätere Endstand hebt die frühe Zusage auf.',
                                'text':'Die zunächst zugesagte regelmäßige Prüfung wurde verworfen; Jonas lädt nur das Mapping einmal hoch.',
                                'evidence_ids':['U0001','U0003','U0004']},
                               {'index':1,'status':'unchanged','reason':'Eigenständige Zusagen',
                                **raw['meeting_summary'][1]}]}
    return originals,raw,gated,decision


class EndstateTest(unittest.TestCase):
    def test_withdrawal_preserves_independent_commitments_pending_review(self):
        originals,raw,proposal,gate=fixture()
        for index in (1,2):proposal['observations'][index]['required_review']=True
        before=copy.deepcopy(proposal['observations'][1:])
        apply_endstate(proposal,raw,gate,originals)
        self.assertEqual(proposal['observations'][1:],before)
        self.assertEqual([o['creates_work'] for o in validate(proposal,TEXT,set())],[False,False,False])
        self.assertEqual([o['kind'] for o in proposal['observations']],['decision','commitment','commitment'])

    def test_withdrawal_preserves_other_work_and_corrects_archive_and_index_input(self):
        originals,raw,proposal,gate=fixture()
        final=apply_endstate(proposal,raw,gate,originals)
        self.assertEqual([o['kind'] for o in proposal['observations']],['decision','commitment','commitment'])
        self.assertEqual([o['creates_work'] for o in validate(proposal,TEXT,set())],[False,True,True])
        self.assertIn(originals['U0003']['text'],proposal['observations'][0]['quotes'])
        with tempfile.TemporaryDirectory() as folder:
            db=connect(Path(folder)/'memory.sqlite')
            try:
                job=register(db,source_id='synthetic:endstate',event_date='2026-10-05',title='PoC',transcript=TEXT)
                apply(db,job,claim(db,job),proposal,model='fixture')
                state=overview(db)
                tasks=state['personal']+state['waiting']+state['waiting_dependencies']
                self.assertEqual(len(tasks),2)
                self.assertEqual({t['owner'] for t in tasks},{'Jonas','Gleb'})
            finally:db.close()
        final_raw={**raw,'meeting_summary':final}
        note=from_value(final_raw,originals,'PoC',TEXT)
        meeting={'source_id':'synthetic:endstate','meeting_date':'2026-10-05','title':'PoC','raw_transcript':TEXT}
        indexed=' '.join(row['text'] for row in current_source_documents(meeting,final_raw) if row['kind']=='summary')
        self.assertIn('wurde verworfen',note['ai_summary'])
        self.assertIn('wurde verworfen',indexed)
        self.assertNotIn('künftig alle zwei Wochen',note['ai_summary']+indexed)

    def test_missing_invalid_or_unrelated_withdrawal_does_not_silently_remove_work(self):
        for change in ({'later_evidence_ids':[]}, {'later_evidence_ids':['U9999']},
                       {'later_evidence_ids':['U0002']}, {'earlier_evidence_ids':['U0004']}):
            originals,raw,proposal,gate=fixture()
            gate['endstate'][0].update(change)
            if change=={'later_evidence_ids':['U0002']}:
                # A same-topic prerequisite is still not a withdrawal: leave it unresolved.
                gate['endstate'][0].update(status='ambiguous',final_claim=None,
                                            reason='The missing attributes do not resolve the later work status.')
                gate['verdicts'][0]['verdict']='ambiguous'
                result=apply_endstate(proposal,raw,gate,originals)
                self.assertTrue(result)
                self.assertTrue(proposal['observations'][0]['required_review'])
                self.assertFalse(validate(proposal,TEXT,set())[0]['creates_work'])
            else:
                with self.assertRaises(ValidationError):apply_endstate(proposal,raw,gate,originals)

    def test_summary_coverage_and_ambiguity_fail_closed(self):
        for mutation in ('missing','ambiguous','changed_unchanged'):
            originals,raw,proposal,gate=fixture()
            if mutation=='missing':gate['final_summary'].pop()
            elif mutation=='ambiguous':gate['final_summary'][0]['status']='ambiguous'
            else:gate['final_summary'][1]['text']='Unbelegte Abweichung'
            with self.assertRaises(ValidationError):apply_endstate(proposal,raw,gate,originals)


if __name__=='__main__':unittest.main()
