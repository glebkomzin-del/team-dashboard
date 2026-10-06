"""Verify dashboard sessions with Supabase Auth, then authorize the configured owner."""
import hmac
import json
import urllib.error
import urllib.request
from urllib.parse import urlparse


class AuthUnavailable(RuntimeError): pass

def authenticate(header, *, service_token, supabase_url='', publishable_key='', allowed_users=()):
    if service_token and hmac.compare_digest(header.encode('utf-8'), ('Bearer ' + service_token).encode('utf-8')):
        return {'role': 'service', 'id': 'n8n'}
    if not header.startswith('Bearer ') or not 20 <= len(header) <= 8192:
        return None
    if not supabase_url or not publishable_key or not allowed_users:
        return None
    parsed = urlparse(supabase_url)
    if supabase_url not in ('https://lghwikeotbkmojyyjglz.supabase.co','https://lghwikeotbkmojyyjglz.supabase.co/','https://178-105-167-26.nip.io/supabase','https://178-105-167-26.nip.io/supabase/','http://api-gw:8000') or parsed.query or parsed.fragment or parsed.username:
        raise RuntimeError('Unexpected Supabase authentication origin')
    request = urllib.request.Request(supabase_url.rstrip('/') + '/auth/v1/user',
                                    headers={'Authorization': header, 'apikey': publishable_key})
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            user = json.loads(response.read(65536))
    except urllib.error.HTTPError as error:
        status=error.code;error.close()
        if status in (401,403):return None
        raise AuthUnavailable('Authentication service unavailable') from None
    except (urllib.error.URLError, ValueError, TimeoutError):
        raise AuthUnavailable('Authentication service unavailable') from None
    if not isinstance(user,dict):raise AuthUnavailable('Invalid authentication response')
    if user.get('id') not in allowed_users or not user.get('email_confirmed_at') or user.get('is_anonymous'):
        return None
    return {'role': 'owner', 'id': user['id']}
