"""One-shot loopback redirect to original target GoTrue magiclink; no session injection."""
import argparse, os, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
parser=argparse.ArgumentParser(); parser.add_argument('--original-action-link-file',type=Path,required=True); parser.add_argument('--port',type=int,default=8944)
args=parser.parse_args()
assert args.original_action_link_file.stat().st_mode & 0o077 == 0
location=args.original_action_link_file.read_text().strip()
u=urllib.parse.urlsplit(location)
assert u.scheme=='https' and u.netloc=='178-105-167-26.nip.io' and u.path=='/supabase/auth/v1/verify' and not u.fragment
query=urllib.parse.parse_qs(u.query)
assert query.get('type')==['magiclink'] and query.get('token') and query.get('redirect_to')==['https://team-dashboard-rho.vercel.app/memory-next']
marker=args.original_action_link_file.parent/'frontend-final-owner-redirect-started'
fd=os.open(marker,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
class Handler(BaseHTTPRequestHandler):
    consumed=False
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path!='/owner-final' or Handler.consumed:
            self.send_response(404); self.end_headers(); return
        Handler.consumed=True
        self.send_response(303); self.send_header('Location',location); self.send_header('Cache-Control','no-store'); self.send_header('Referrer-Policy','no-referrer'); self.end_headers()
        print('Original action link redirected once; no token output',flush=True)
    def do_POST(self): self.send_response(405); self.end_headers()
print('Loopback original-action redirect ready',flush=True)
HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
