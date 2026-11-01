import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from access import authenticate,AuthUnavailable


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.settings = dict(service_token='internal-test-token', supabase_url='https://lghwikeotbkmojyyjglz.supabase.co', publishable_key='public-test-key', allowed_users=['owner'])
        self.header = 'Bearer synthetic-owner-session'

    def response(self, user): return io.BytesIO(json.dumps(user).encode())

    def test_service_and_owner_are_distinct(self):
        with patch('access.urllib.request.urlopen', return_value=self.response({'id': 'owner', 'email_confirmed_at': '2026-01-01'})) as request:
            self.assertEqual(authenticate('Bearer internal-test-token', **self.settings)['role'], 'service')
            request.assert_not_called()
            self.assertEqual(authenticate(self.header, **self.settings), {'id': 'owner', 'role': 'owner'})
            self.assertEqual(request.call_args.args[0].full_url, self.settings['supabase_url'] + '/auth/v1/user')

    def test_other_accounts_and_user_editable_metadata_do_not_authorize(self):
        for user in [{'id': 'other', 'email_confirmed_at': 'now', 'user_metadata': {'role': 'owner'}}, {'id': 'owner'}, {'id': 'owner', 'email_confirmed_at': 'now', 'is_anonymous': True}]:
            with patch('access.urllib.request.urlopen', return_value=self.response(user)):
                self.assertIsNone(authenticate(self.header, **self.settings))

    def test_provider_outage_is_distinct_from_expired_login(self):
        with patch('access.urllib.request.urlopen', side_effect=HTTPError('https://test', 503, 'Unavailable', {}, None)):
            with self.assertRaises(AuthUnavailable):authenticate(self.header, **self.settings)
        with patch('access.urllib.request.urlopen', return_value=self.response([])):
            with self.assertRaises(AuthUnavailable):authenticate(self.header, **self.settings)
        self.assertIsNone(authenticate('Nicht gültig', **self.settings))

    def test_expired_or_missing_sessions_are_rejected(self):
        with patch('access.urllib.request.urlopen', side_effect=HTTPError('https://test', 401, 'Unauthorized', {}, None)):
            self.assertIsNone(authenticate(self.header, **self.settings))
        self.assertIsNone(authenticate('', **self.settings))
        with self.assertRaises(RuntimeError):
            authenticate(self.header, **{**self.settings, 'supabase_url': 'https://other.example'})


if __name__ == '__main__': unittest.main()
