"""Synthetic Google-shaped HTTP fixture, only for an isolated n8n contract test."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from urllib.parse import urlparse, parse_qs
FOLDER='1xUMHw3Z3zcvHE96mczw4e9HFZpUJyMoE'
def file(id):
    return {'id':id,'name':('2026-07-20' if id=='test-one' else '2026-07-15')+' Synthetic meeting.txt','mimeType':'text/plain' if id=='test-one' else 'application/vnd.google-apps.document','version':'2','modifiedTime':'2026-07-21T08:00:00Z','parents':[FOLDER],'trashed':False}
CALLS=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        url=urlparse(self.path);q=parse_qs(url.query);CALLS.append(url.path+(':'+q['pageToken'][0] if q.get('pageToken') else ''))
        if url.path=='/fixture-audit':result={'requests':CALLS}
        elif url.path=='/drive/v3/files':
            token=q.get('pageToken',[''])[0]
            result={'files':[file('test-one')],'nextPageToken':'page2','incompleteSearch':False} if not token else {'files':[],'nextPageToken':'page3','incompleteSearch':False} if token=='page2' else {'files':[file('test-two')],'incompleteSearch':False}
        elif url.path.startswith('/drive/v3/files/'):
            id=url.path.split('/')[4]
            if id not in ('test-one','test-two'):self.send_error(404);return
            if url.path.endswith('/export') or q.get('alt')==['media']:
                body=('00:01 '+('Gleb' if id=='test-one' else 'Oliver')+': Dies ist nur ein synthetischer Originaltest.\r\n').encode()
                self.send_response(200);self.send_header('Content-Type','text/plain; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            result=file(id)
            if os.environ.get('CHANGED')=='1':result['version']='3'
        else:self.send_error(404);return
        body=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',8792),Handler).serve_forever()
