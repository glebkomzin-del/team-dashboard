"""Synthetic scope regression tests; no private replay data or network."""
import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'overlay'),str(ROOT/'private/runtime')]
sys.dont_write_bytecode=True
from memory import connect,register,claim,apply,overview,ValidationError
TEXT='Gleb: Ich sende den Bericht.\nGleb: Der Stand ist aktualisiert.'
def item(**changes):
 value={'matter':'Bereich A','matter_id':None,'kind':'commitment','title':'Bericht senden','claim':'Gleb sendet den Bericht.','owner':'Gleb','commitment_strength':'explicit','due_text':None,'update_target':None,'update':'none','quotes':[TEXT.splitlines()[0]],'uncertainty':None,'action_uncertainty':None,'required_review':False}
 return {**value,**changes}
def proposal(o):return {'observations':[o],'coverage_notes':[]}
class ScopeTests(unittest.TestCase):
 def setUp(self):
  self.db=connect(':memory:')
  for i,matter in enumerate(('Bereich A','Bereich B')):
   job=register(self.db,source_id='synthetic:'+str(i),event_date='2026-07-'+str(15+i),title=matter,transcript=TEXT)
   apply(self.db,job,claim(self.db,job),proposal(item(matter=matter)),model='fixture')
  work=overview(self.db)['personal'];self.target=next(w for w in work if w['matter']=='Bereich A')['id']
  self.other=self.db.execute('SELECT id FROM matters WHERE title=?',('Bereich B',)).fetchone()[0]
  self.job=register(self.db,source_id='synthetic:update',event_date='2026-07-17',title='Update',transcript=TEXT)
  self.token=claim(self.db,self.job)
 def tearDown(self):self.db.close()
 def update(self,**changes):return item(**{'kind':'status','matter':'Bereich B','matter_id':self.other,'update_target':self.target,'update':'progress','commitment_strength':'not_applicable','quotes':[TEXT.splitlines()[1]],'work_gate':{'verdict':'supported'},**changes})
 def test_rejected_cross_scope_kept_as_knowledge_without_work_event(self):
  o=self.update(required_review=True,action_uncertainty='Bezug nicht belegt',work_gate={'verdict':'unsupported'})
  result=apply(self.db,self.job,self.token,proposal(o),model='fixture')
  row=self.db.execute('SELECT id,matter_id FROM observations WHERE job_id=?',(self.job,)).fetchone()
  self.assertEqual(row['matter_id'],self.other)
  self.assertEqual(self.db.execute('SELECT count(*) FROM work_events WHERE observation_id=?',(row['id'],)).fetchone()[0],0)
  self.assertEqual(result[0]['work_gate']['verdict'],'unsupported')
 def test_blocked_missing_matter_keeps_historical_target_scope(self):
  o=self.update(matter_id=None,required_review=True,work_gate={'verdict':'unsupported'})
  apply(self.db,self.job,self.token,proposal(o),model='fixture')
  target_scope=self.db.execute('SELECT matter_id FROM observations WHERE id=?',(self.target,)).fetchone()[0]
  self.assertEqual(self.db.execute('SELECT matter_id FROM observations WHERE job_id=?',(self.job,)).fetchone()[0],target_scope)
 def test_effective_same_scope_still_emits_work_event(self):
  target_scope=self.db.execute('SELECT matter_id FROM observations WHERE id=?',(self.target,)).fetchone()[0]
  o=self.update(matter='Bereich A',matter_id=target_scope)
  apply(self.db,self.job,self.token,proposal(o),model='fixture')
  row=self.db.execute('SELECT id FROM observations WHERE job_id=?',(self.job,)).fetchone()
  self.assertEqual(self.db.execute('SELECT count(*) FROM work_events WHERE observation_id=?',(row['id'],)).fetchone()[0],1)
 def test_effective_cross_scope_still_rejected(self):
  with self.assertRaisesRegex(ValidationError,'Work update belongs to a different matter'):
   apply(self.db,self.job,self.token,proposal(self.update()),model='fixture')
 def test_rejected_unknown_work_still_rejected(self):
  with self.assertRaisesRegex(ValidationError,'Unknown work target'):
   apply(self.db,self.job,self.token,proposal(self.update(required_review=True,update_target='unknown')),model='fixture')
 def test_rejected_invented_evidence_still_rejected(self):
  with self.assertRaisesRegex(ValidationError,'Quote not found verbatim'):
   apply(self.db,self.job,self.token,proposal(self.update(required_review=True,quotes=['Nicht im Original'])),model='fixture')
if __name__=='__main__':unittest.main()
