import json
from pathlib import Path
import tempfile
import unittest
from memory import connect, register, claim, apply, overview
from reproject import reproject
from test_memory import observation, proposal, TEXT


class ReprojectionTests(unittest.TestCase):
    def test_saved_gate_and_later_lifecycle_review_are_not_gated_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            db=connect(root/'source.sqlite')
            first=register(db,source_id='drive:one',event_date='2026-07-15',title='First',transcript=TEXT)
            apply(db,first,claim(db,first),proposal(observation()),model='fixture')
            original_id=overview(db)['personal'][0]['id']
            text='Jan: Ich prüfe den Zugang.\nGleb: Der Bericht ist verschickt.'
            second=register(db,source_id='drive:two',event_date='2026-07-20',title='Second',transcript=text)
            verdict={'index':0,'verdict':'supported','reason':'Explicit promise','evidence_ids':['U1']}
            new=observation(owner='Jan',due_text=None,quotes=[text.splitlines()[0]],work_gate=verdict)
            done=observation(kind='status',owner=None,due_text=None,quotes=[text.splitlines()[1]],
                             state_quotes=[text.splitlines()[1]],work_state='done',
                             update_target=original_id,update='done',resolution_basis='explicit_lifecycle_review')
            apply(db,second,claim(db,second),proposal(new,done),model='fixture')
            gate={'content':[{'type':'text','text':json.dumps({'verdicts':[verdict]})}]}
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',('saved-gate',second,1,'fixture','{}',0,'work_gate',json.dumps(gate)))
            db.close()
            result=reproject(root/'source.sqlite',root/'replayed.sqlite',guard_same_day=True)
            self.assertEqual(result['completed'],1)
            replayed=connect(root/'replayed.sqlite')
            self.assertEqual(overview(replayed)['completed'][0]['id'],original_id)
            self.assertEqual(replayed.execute('SELECT count(*) FROM observations').fetchone()[0],3)
            self.assertTrue(replayed.execute('SELECT receipt_json FROM replay_receipt').fetchone())
            replayed.close()


if __name__=='__main__':unittest.main()
