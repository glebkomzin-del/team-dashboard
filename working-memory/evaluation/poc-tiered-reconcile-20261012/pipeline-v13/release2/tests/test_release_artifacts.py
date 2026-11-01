"""Manifest contract and strict-schema checks on synthetic/local release data."""
import copy
import contextlib
import hashlib
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from local_support import ROOT
from make_manifest import TARGETS,EXISTING,unique_object,updated_manifest
import compact_reconcile
import hybrid_schema

def checker():
    spec=importlib.util.spec_from_file_location('checker_for_test',ROOT/'overlay/offline_check.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class ManifestTests(unittest.TestCase):
    def manifest(self):return {name:'a'*64 for name in (*EXISTING,'unrelated.py','Dockerfile')}
    def test_only_payload_entries_updated(self):
        base=self.manifest();before=copy.deepcopy(base)
        result=updated_manifest(base,ROOT/'overlay')
        self.assertEqual(base,before)
        self.assertEqual(set(result),set(base)|set(TARGETS))
        self.assertEqual(result['unrelated.py'],base['unrelated.py'])
        self.assertEqual(result['Dockerfile'],base['Dockerfile'])
        for name in TARGETS:
            self.assertEqual(result[name],hashlib.sha256((ROOT/'overlay'/name).read_bytes()).hexdigest())
    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):unique_object([('a','b'),('a','c')])
    def test_missing_existing_module_rejected(self):
        base=self.manifest();del base[EXISTING[0]]
        with self.assertRaises(ValueError):updated_manifest(base,ROOT/'overlay')
    def test_invalid_manifest_rejected(self):
        for value in ([],{}, {'x':'invalid'}):
            with self.subTest(value_type=type(value).__name__),self.assertRaises(ValueError):updated_manifest(value,ROOT/'overlay')

class SchemaTests(unittest.TestCase):
    def walk(self,node):
        if not isinstance(node,dict):return
        if node.get('type')=='object':
            self.assertIs(node.get('additionalProperties'),False)
            self.assertEqual(set(node.get('required',[])),set(node.get('properties',{})))
        if 'enum' in node:self.assertTrue(node['enum'])
        for value in node.values():
            if isinstance(value,dict):
                self.walk(value)
                for nested in value.values():self.walk(nested)
            elif isinstance(value,list):
                for nested in value:self.walk(nested)
    def schema(self,work,observations):
        catalog=compact_reconcile.Catalog(work,{}, {})
        return hybrid_schema.delta_schema(compact_reconcile.response_schema(catalog,observations))
    def test_delta_schema_strict_with_work(self):
        self.walk(self.schema([{'id':'synthetic'}],[0]))
    def test_delta_schema_strict_empty_extraction_and_work(self):
        value=self.schema([],[]);self.walk(value)
        self.assertEqual(value['properties']['observations']['maxItems'],0)
    def test_container_payloads_match_copy(self):
        docker=(ROOT/'overlay/Dockerfile').read_text()
        self.assertIn('ARG OLD_TAG\nFROM ${OLD_TAG}',docker)
        copyline=next(line for line in docker.splitlines() if line.startswith('COPY '))
        self.assertEqual(copyline.split()[2:-1],[*TARGETS,'build-manifest.json'])
    def test_independent_identity_matches_expected(self):
        module=checker()
        expected=json.loads((ROOT/'overlay/default_contract.json').read_text())
        self.assertEqual(module.independent_version(ROOT/'overlay'),expected['pipeline_version'])
    def test_offline_checker_passes(self):
        expected=json.loads((ROOT/'overlay/default_contract.json').read_text())
        import processor
        with patch.object(processor,'PROMPT_VERSION','v11'),patch.dict('os.environ',{'DASHBOARD_DELTA_OUTPUT':'0','DASHBOARD_HOTSET_FILTER':'0','DASHBOARD_SERVICE_TIER':'default','DASHBOARD_HOTSET_AGE_DAYS':'30','DASHBOARD_HOTSET_RANK':'5'}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(checker().run_checks(ROOT/'overlay',expected),0)
    def test_offline_checker_returns_nonzero_for_wrong_identity(self):
        expected=json.loads((ROOT/'overlay/default_contract.json').read_text())
        expected['pipeline_version']='invalid'
        import processor
        with patch.object(processor,'PROMPT_VERSION','v11'),patch.dict('os.environ',{'DASHBOARD_DELTA_OUTPUT':'0','DASHBOARD_HOTSET_FILTER':'0','DASHBOARD_SERVICE_TIER':'default','DASHBOARD_HOTSET_AGE_DAYS':'30','DASHBOARD_HOTSET_RANK':'5'}),contextlib.redirect_stdout(io.StringIO()):
            self.assertNotEqual(checker().run_checks(ROOT/'overlay',expected),0)

if __name__=='__main__':unittest.main()
