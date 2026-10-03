"""Synthetic migration checks; no network, real credentials or application writes."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from access import authenticate
from gateway_journal import GatewayJournal


class OriginContractTests(unittest.TestCase):
    settings = dict(service_token='', publishable_key='synthetic-public', allowed_users=['owner'])

    def test_auth_prefix_and_internal_origin_preserve_owner_check(self):
        for origin in ('https://178-105-167-26.nip.io/supabase', 'http://api-gw:8000'):
            for user, expected in (({'id': 'owner', 'email_confirmed_at': 'now'}, {'id': 'owner', 'role': 'owner'}),
                                   ({'id': 'other', 'email_confirmed_at': 'now'}, None)):
                with patch('access.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(user).encode())) as send:
                    self.assertEqual(authenticate('Bearer synthetic-session', supabase_url=origin, **self.settings), expected)
                    self.assertEqual(send.call_args.args[0].full_url, origin + '/auth/v1/user')

    def test_gateway_prefix_and_payload_are_preserved(self):
        for origin in ('https://178-105-167-26.nip.io/supabase', 'http://api-gw:8000'):
            store = GatewayJournal(origin, 'synthetic-public', 'a' * 64, '96a2dc44-9b9e-4644-b236-c5c1956cd39d')
            with patch('gateway_journal.urlopen', return_value=io.BytesIO(b'{"revision":1}')) as send:
                self.assertEqual(store.call('space'), {'revision': 1})
                req = send.call_args.args[0]
                self.assertEqual(req.full_url, origin + '/functions/v1/working-memory-journal')
                self.assertEqual(json.loads(req.data), {'op': 'space', 'space_id': store.space_id})

    def test_unapproved_origins_fail_before_network(self):
        for origin in ('http://178-105-167-26.nip.io/supabase', 'https://178-105-167-26.nip.io',
                       'https://178-105-167-26.nip.io/supabase?x=1', 'http://other:8000',
                       'https://user@178-105-167-26.nip.io/supabase', 'https://178-105-167-26.nip.io/supabase/extra'):
            with patch('access.urllib.request.urlopen') as send:
                with self.assertRaises(RuntimeError):
                    authenticate('Bearer synthetic-session', supabase_url=origin, **self.settings)
                send.assert_not_called()
            with self.assertRaises(ValueError):
                GatewayJournal(origin, 'synthetic-public', 'a' * 64, '96a2dc44-9b9e-4644-b236-c5c1956cd39d')


if __name__ == '__main__':
    unittest.main()
