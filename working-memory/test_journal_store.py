import io,json,unittest
from unittest.mock import patch
from urllib.error import HTTPError
from journal_store import SupabaseJournal,RevisionConflict,JournalUnavailable

class JournalTests(unittest.TestCase):
    def setUp(self):self.store=SupabaseJournal('https://fixture.supabase.co','private-fixture','10000000-0000-4000-8000-000000000001')
    def test_retry_preserves_identity_and_expected_revision(self):
        with patch('journal_store.urlopen',return_value=io.BytesIO(b'{"revision":1,"repeated":true}')) as http:
            result=self.store.append(expected_revision=0,command_id='20000000-0000-4000-8000-000000000001',kind='source',payload={})
            body=json.loads(http.call_args.args[0].data)
            self.assertEqual(body['p_expected_revision'],0)
            self.assertEqual(body['p_command_id'],'20000000-0000-4000-8000-000000000001')
            self.assertTrue(result['repeated'])
    def test_conflicts_are_distinct_without_exposing_server_body(self):
        error=HTTPError('https://fixture',500,'error',{},io.BytesIO(b'{"code":"40001","message":"PRIVATE SOURCE TEXT"}'))
        with patch('journal_store.urlopen',side_effect=error):
            with self.assertRaises(RevisionConflict) as caught:self.store.space()
            self.assertNotIn('PRIVATE',str(caught.exception))
    def test_snapshot_does_not_read_future_entries(self):
        with patch.object(self.store,'request',side_effect=[[{'revision':1}],[{'revision':2}]]) as request:
            self.assertEqual(len(self.store.entries(through=2)),2)
            self.assertIn('revision.lte.2',request.call_args.args[0])
    def test_gap_is_rejected(self):
        for rows in ([],[{'revision':2}]):
            with patch.object(self.store,'request',return_value=rows):
                with self.assertRaises(JournalUnavailable):self.store.entries(through=2)
    def test_version_id_and_destination_cannot_redirect_key(self):
        with self.assertRaises(ValueError):SupabaseJournal('https://attacker.example','key',self.store.space_id)
        with patch.object(self.store,'request') as request:
            with self.assertRaises(ValueError):self.store.source('../other')
            request.assert_not_called()

if __name__=='__main__':unittest.main()
