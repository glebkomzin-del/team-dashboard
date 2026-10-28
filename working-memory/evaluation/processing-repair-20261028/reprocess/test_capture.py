"""Offline-capture safety boundaries; no network or production state."""
import importlib.util
import json
from pathlib import Path
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('capture_worker',HERE/'capture_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)


class CaptureTests(unittest.TestCase):
    def store(self):
        return worker.ReadStore({'indexed_ids':['one'],'snapshot':{'id':'snap','document_ids':['one']},'search_results':{}})

    def test_missing_documents_are_not_claimed_present(self):
        self.assertEqual(self.store().call('search_missing',document_ids=['one','missing']),['missing'])

    def test_snapshot_is_verified_not_created(self):
        self.assertEqual(self.store().call('search_snapshot',search_snapshot_id='snap',document_ids=['one']),{'count':1})
        with self.assertRaises(worker.CacheMiss):self.store().call('search_snapshot',search_snapshot_id='other',document_ids=['one'])
        with self.assertRaises(worker.CacheMiss):self.store().call('search_snapshot',search_snapshot_id='snap',document_ids=['other'])

    def test_query_miss_and_writes_are_rejected(self):
        for op in ('search_put','reserve_call','receive_call','append','search_cached'):
            with self.assertRaises(worker.CacheMiss):self.store().call(op)
        with self.assertRaises(worker.CacheMiss):self.store().call('search_query',search_snapshot_id='snap',query_text='x',query_embedding=[1.0],kinds=['work'],match_count=20)

    def test_only_exact_cached_query_returns(self):
        data={'indexed_ids':[],'snapshot':{'id':'snap','document_ids':[]},'search_results':{}}
        fields={'search_snapshot_id':'snap','query_text':'x','query_embedding':[1.0],'kinds':['work'],'match_count':20}
        key=worker.sha(worker.encode(['x',[1.0],['work'],20]));data['search_results'][key]=[{'id':'hit'}]
        store=worker.ReadStore(data);self.assertEqual(store.call('search_query',**fields),[{'id':'hit'}])
        fields['query_embedding']=[2.0]
        with self.assertRaises(worker.CacheMiss):store.call('search_query',**fields)

    def test_unreceived_or_tampered_model_response_stops(self):
        for response,request_hash in [(None,'x'),('{}','wrong')]:
            with self.assertRaises(worker.CacheMiss):worker.ReplayAPI({'indexed_ids':[],'calls':[{'response_json':response,'request_json':'{}','request_hash':request_hash}]})

    def test_host_sql_is_read_only_and_never_search_rpc(self):
        source=(HERE/'capture_context.py').read_text()
        self.assertIn('REPEATABLE READ READ ONLY',source)
        self.assertNotIn('wm_search_query(',source)
        self.assertNotIn('wm_reserve_call(',source)
        self.assertNotIn('wm_receive_call(',source)


if __name__=='__main__':unittest.main()
