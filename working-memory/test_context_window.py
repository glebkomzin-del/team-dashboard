import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import test_archive_index
import archive_index
import processor
from context_window import RETRIEVAL_BUDGET_CHARS, RETRIEVAL_HARD_LIMIT_CHARS, retrieval
from memory import connect, register, claim, apply
from test_memory import observation, proposal

class ContextWindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=connect(self.root/'memory.sqlite')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_all_work_identities_survive_knowledge_selection(self):
        text='Gleb: Ich sende den Bericht morgen.'
        job=register(self.db,source_id='fixture',event_date='2026-07-15',title='Fixture',transcript=text)
        apply(self.db,job,claim(self.db,job),proposal(*(observation(title=f'Ergebnis {i}',quotes=[text]) for i in range(85))),model='fixture')
        selected=retrieval(self.db,{'title':'Andere Themen','raw_transcript':'PowerBI Finanzierung','meeting_date':'2026-07-16'})
        self.assertEqual(len(selected['work']),85);self.assertEqual(len({r['id'] for r in selected['work']}),85)
        self.assertEqual(selected['retrieval']['history_observations_selected'],0)
        self.assertEqual(selected['retrieval']['history_observations_total'],85)
        previous=retrieval(self.db,{'title':'Bericht','raw_transcript':text,'meeting_date':'2026-07-14'})
        self.assertEqual(previous['work'],[])
    def test_archive_excludes_same_day_future_and_later_known_revisions(self):
        fixture=test_archive_index.ArchiveIndexTests();fixture.root=self.root
        archive=archive_index.connect(self.root/'archive.sqlite')
        archive_index.ingest_archive(archive,fixture.archive('initial',[('drive:a','2026-07-14','Finance','Umrechnungskurse früher'),('drive:b','2026-07-15','Finance','Umrechnungskurse gleichentags'),('drive:c','2026-07-20','Finance','Umrechnungskurse später')],'2026-07-21T12:00:00Z'))
        archive_index.ingest_archive(archive,fixture.archive('changed',[('drive:a','2026-07-14','Finance','Umrechnungskurse spätere Änderung')],'2026-07-23T12:00:00Z'));archive.close()
        result=retrieval(self.db,{'title':'Finance','raw_transcript':'Umrechnungskurse','meeting_date':'2026-07-15','observed_at':'2026-07-22T00:00:00Z'},self.root/'archive.sqlite')
        self.assertEqual([r['text'] for r in result['prior_original_passages']],['Umrechnungskurse früher'])
    def test_long_current_original_is_complete(self):
        transcript='Gleb: '+('Vollständiger Originaltext. '*9000)+'\r\nSchluss: Letzte Zusage.'
        meeting={'title':'Langes Meeting','raw_transcript':transcript,'meeting_date':'2026-07-15'}
        with patch.multiple(processor,PROMPT_VERSION='v5',MAX_PROMPT_CHARS=600000):
            prompt, units=processor.build_prompt(meeting,self.db)
        self.assertIn('Letzte Zusage.',prompt)
        self.assertEqual(sum(v['end']-v['start'] for v in units.values()),len(transcript)-2)
        self.assertGreater(len(prompt),140000)

    def test_retrieval_budget_reserves_prompt_space(self):
        self.assertEqual(RETRIEVAL_BUDGET_CHARS, 450000)
        self.assertLess(RETRIEVAL_BUDGET_CHARS, RETRIEVAL_HARD_LIMIT_CHARS)
        self.assertLessEqual(RETRIEVAL_HARD_LIMIT_CHARS + 140000, 600000)

if __name__=='__main__':unittest.main()
