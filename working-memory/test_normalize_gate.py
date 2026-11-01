import unittest
from processor import apply_work_gate,validate_semantics
from memory import validate,ValidationError
from test_memory import observation,proposal

class NormalizeGateTests(unittest.TestCase):
    def setUp(self):
        self.a='Oliver: Ich setze einen Termin für Montag auf.';self.b='Oliver: Ich schicke gleich die Einladung.'
        self.originals={'U1':{'text':self.a},'U2':{'text':self.b}}
    def test_same_invitation_has_one_work_identity_and_preserves_both_quotes(self):
        items=proposal(observation(owner='Oliver',due_text='Montag',quotes=[self.a]),observation(owner='Oliver',due_text='gleich',quotes=[self.b]))
        verdicts=[{'index':0,'verdict':'supported','reason':'Einladung','evidence_ids':['U1'],'duplicate_of':None,'due_role':'event_time'}, {'index':1,'verdict':'duplicate','reason':'Dieselbe Einladung','evidence_ids':['U2'],'duplicate_of':0,'due_role':'work_deadline'}]
        result=apply_work_gate(items,verdicts,self.originals)
        checked=validate(result,self.a+'\n'+self.b,set())
        self.assertEqual(sum(o['creates_work'] for o in checked),1)
        self.assertEqual(checked[0]['due_text'],'gleich')
        self.assertEqual(checked[0]['original_time_expression'],'Montag')
        self.assertEqual(checked[0]['quotes'],[self.a,self.b])
        self.assertEqual(checked[1]['duplicate_of_index'],0)
    def test_different_owners_and_conflicting_conditions_cannot_be_collapsed(self):
        verdicts=[{'index':0,'verdict':'supported','reason':'x','evidence_ids':['U1']},{'index':1,'verdict':'duplicate','duplicate_of':0,'reason':'x','evidence_ids':['U2']}]
        for first,second in [(observation(owner='A'),observation(owner='B')),(observation(condition_text='Bedingung A'),observation(condition_text='Bedingung B'))]:
            with self.assertRaises(ValidationError):apply_work_gate(proposal(first,second),verdicts,self.originals)
    def test_forward_or_cyclic_duplicate_is_rejected(self):
        verdicts=[{'index':0,'verdict':'duplicate','duplicate_of':1,'reason':'x','evidence_ids':['U1']},{'index':1,'verdict':'supported','reason':'x','evidence_ids':['U2']}]
        with self.assertRaises(ValidationError):apply_work_gate(proposal(observation(),observation()),verdicts,self.originals)

class SemanticConsistencyTests(unittest.TestCase):
    def test_explicit_promise_cannot_disappear_as_decision(self):
        item=observation(kind='decision',commitment_strength='explicit')
        with self.assertRaisesRegex(ValidationError,'Contradictory commitment'):validate_semantics(proposal(item))
        item['kind']='commitment';validate_semantics(proposal(item))
    def test_supported_gate_can_resolve_previous_doubt_with_source_evidence(self):
        text='Oliver: Ich versuche es vor dem Termin aufzubereiten.'
        item=observation(owner='Oliver',action_uncertainty='Unklar ob zugesagt',due_text=None,quotes=[text])
        verdict={'index':0,'verdict':'supported','reason':'Nur die ausdrücklich übernommene Bemühung','evidence_ids':['U1'],'action_uncertainty':None}
        checked=apply_work_gate(proposal(item),[verdict],{'U1':{'text':text}})
        self.assertTrue(validate(checked,text,set())[0]['creates_work'])
        self.assertEqual(checked['observations'][0]['prior_action_uncertainty'],'Unklar ob zugesagt')
        verdict['action_uncertainty']='Wer übernimmt bleibt unklar'
        with self.assertRaises(ValidationError):apply_work_gate(proposal(item),[verdict],{'U1':{'text':text}})

if __name__=='__main__':unittest.main()
