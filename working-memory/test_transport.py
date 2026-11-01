import concurrent.futures
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server
from processor import units,resolve
from memory import connect,ValidationError

class TransportTests(unittest.TestCase):
    def setUp(self):
        self.environment=patch.dict('os.environ',{'MEMORY_AUTOMATIC_FROM_DATE':'2026-07-15','MEMORY_BUDGET_USD':'1'})
        self.environment.start();self.addCleanup(self.environment.stop)
        self.version=patch('processor.PROMPT_VERSION','v9');self.version.start();self.addCleanup(self.version.stop)
        self.gate=patch('processor.ACTION_GATE',True);self.gate.start();self.addCleanup(self.gate.stop)
        self.auto=patch('server.AUTOMATIC_ENABLED',True);self.auto.start();self.addCleanup(self.auto.stop)
        self.tmp=tempfile.TemporaryDirectory();server.DB=str(Path(self.tmp.name)/'db.sqlite');server.TOKEN='test-token-'+'x'*32
        connect(server.DB).close();self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.http.server_port)
    def tearDown(self):self.http.shutdown();self.http.server_close();self.thread.join();self.tmp.cleanup()
    def post(self,data,auth=True):
        req=urllib.request.Request(self.url+'/sources',data=json.dumps(data).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+server.TOKEN} if auth else {})})
        try:
            with urllib.request.urlopen(req) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:
            try:return e.code,json.load(e)
            finally:e.close()
    def test_unauthorized_intake_has_no_side_effect(self):
        status,_=self.post({},False);self.assertEqual(status,401)
        db=connect(server.DB);self.assertEqual(db.execute('select count(*) from jobs').fetchone()[0],0);db.close()
    def test_parallel_repeated_intake_one_durable_job(self):
        data={'source_id':'drive:test','event_date':'2026-07-15','title':'Fixture','transcript':'00:01 Gleb: Guten Morgen.'}
        with concurrent.futures.ThreadPoolExecutor(4) as pool:results=list(pool.map(lambda _:self.post(data),range(4)))
        self.assertTrue(all(status==202 for status,_ in results));self.assertEqual(len({r['job_id'] for _,r in results}),1)
        db=connect(server.DB);self.assertEqual(db.execute('select count(*) from jobs').fetchone()[0],1);db.close()
    def test_bad_payload_rejected(self):
        self.assertEqual(self.post([])[0],400);self.assertEqual(self.post({'source_id':'x'})[0],400)
    def test_historical_source_never_enters_paid_queue(self):
        self.assertEqual(self.post({'source_id':'drive:old','event_date':'2026-06-01','title':'Old source','transcript':'original'})[0],409)
        db=connect(server.DB)
        self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0);db.close()
    def test_original_offsets_survive_crlf_and_unicode(self):
        text='00:01 Gleb: Grüße.\r\n00:02 Oliver: Ja.\n';u=units(text)
        for item in u.values():self.assertEqual(text[item['start']:item['end']],item['text'])
        out=resolve({'observations':[{'evidence_ids':['U0001']}],'coverage_notes':[]},u)
        self.assertEqual(out['observations'][0]['quotes'],['00:01 Gleb: Grüße.'])
        with self.assertRaises(ValidationError):resolve({'observations':[{'evidence_ids':['U9999']}],'coverage_notes':[]},u)
    def test_bounded_backoff_retries_only_transient_failure(self):
        data={'source_id':'drive:test','event_date':'2026-07-15','title':'Fixture','transcript':'text'}
        _,result=self.post(data);job=result['job_id'];db=connect(server.DB)
        db.execute("UPDATE jobs SET status='failed',attempts=1,error='Provider HTTP 429' WHERE id=?",(job,))
        db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',('run',job,100,'fixture','{}',1,'provider_incomplete','{}'))
        server.retry_transient(db,129);self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'failed')
        server.retry_transient(db,131);self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'queued')
        db.execute("UPDATE jobs SET status='failed',attempts=3")
        server.retry_transient(db,1000);self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'failed')
        db.execute("UPDATE jobs SET attempts=1,error='Unknown matter ID'")
        server.retry_transient(db,1000);self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'failed');db.close()

if __name__=='__main__':unittest.main()
