"""Rollback only this route after explicit Lead phase; hash guard preserves later changes."""
from pathlib import Path
import hashlib,subprocess
p=Path('/etc/nginx/sites-available/alexa')
assert hashlib.sha256(p.read_bytes()).hexdigest()=='7cfba8642673162a182f67926bc26dbb0def8bdafecd7952e7ee5c524511fe51'
original=Path('/opt/dashboard-supabase-20261003/public-api-1/nginx-original.conf').read_bytes()
assert hashlib.sha256(original).hexdigest()=='bed7ff8f2bb5cb78ffddf4744c3eefb2fed28476a1d783b7b184bcae8e2ad497'
p.write_bytes(original)
subprocess.run(['nginx','-t'],check=True);subprocess.run(['systemctl','reload','nginx'],check=True)
