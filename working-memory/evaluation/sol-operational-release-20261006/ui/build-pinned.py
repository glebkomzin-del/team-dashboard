from pathlib import Path
import os,subprocess
config=Path('/private/tmp/dashboard-sol-ui-20261006/.env.production.local')
env=os.environ.copy()
for line in config.read_text().splitlines():
 if '=' in line:
  key,value=line.split('=',1)
  if key.startswith('VITE_'):env[key]=value
raise SystemExit(subprocess.run(['pnpm','build'],env=env).returncode)
