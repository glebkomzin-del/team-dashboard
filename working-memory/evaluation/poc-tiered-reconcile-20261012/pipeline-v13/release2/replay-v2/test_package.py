"""Selected-case round trips, archive and launcher; never provider execution."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import os
import unittest

ROOT = Path(__file__).resolve().parent
def load(name):
    spec = importlib.util.spec_from_file_location('package_'+name, ROOT/(name+'.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class PackageTests(unittest.TestCase):
    def test_selected_sources_roundtrip(self):
        common, codec, compare = load('replay_common'), load('delta_codec'), load('compare_v2')
        records = list(common.read_jsonl(ROOT/'selected_requests.jsonl'))
        self.assertEqual(len(records), 8)
        for record in records:
            with self.subTest(index=record['call_index']):
                delta = codec.to_delta(record['reference_full'], record['obs_in'], record['work'])
                self.assertEqual(common.schema_errors(delta, record['request_json']['schema']), [])
                decoded = codec.from_delta(delta, record['obs_in'], record['work'])
                self.assertTrue(codec.equal(decoded, record['reference_full']))
                self.assertEqual(common.schema_errors(decoded, compare.full_schema(record['reference_schema'])), [])

    def test_bundle_execution_files_at_root(self):
        path=ROOT/'transfer/replay-v2-bundle.tar'
        self.assertTrue(path.is_file())
        self.assertLessEqual(path.stat().st_size, 5_000_000)
        expected={'replay_v2.py','replay_common.py','compare_v2.py','delta_codec.py',
                  'selected_requests.jsonl','control_metrics.json','run_on_server.sh'}
        with tarfile.open(path, 'r') as archive:
            self.assertEqual({m.name for m in archive.getmembers()}, expected)
            self.assertTrue(all(m.isfile() for m in archive.getmembers()))
            self.assertIn('cd "$(dirname "$0")"', archive.extractfile('run_on_server.sh').read().decode())

    def test_launcher_stops_before_paid_execution(self):
        result=subprocess.run(['sh', str(ROOT/'run_on_server.sh')], cwd=ROOT.parent,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2)
        row=json.loads((ROOT/'run.out').read_text())
        self.assertEqual(row['attempts'], 0)
        self.assertEqual(row['execute'], 0)
        self.assertEqual(row['candidates'], 8)
        self.assertFalse((ROOT/'replay_ledger.jsonl').exists())
        self.assertFalse(list(ROOT.glob('raw-attempt-*.sse')))

    def test_launcher_complete_mock_path(self):
        # Mock the command transport; synthetic local process only, never a provider.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            folder=Path(tmp)
            wrapper=folder/'run_on_server.sh'
            wrapper.write_bytes((ROOT/'run_on_server.sh').read_bytes())
            fake=folder/'python3'
            fake.write_text('''#!/bin/sh
case "$*" in
  "-I -B replay_v2.py --max-usd 1.30") printf '0\\n' >> phases; echo '{"attempts":0}'; exit 0 ;;
  "-I -B replay_v2.py --execute --max-usd 1.30") printf '1\\n' >> phases; echo '{"attempts":8}'; exit 0 ;;
  "-I -B compare_v2.py") printf '2\\n' >> phases; echo '{"passed":0}'; exit 1 ;;
  *) exit 9 ;;
esac
''')
            fake.chmod(0o700)
            env={'PATH':str(folder)+':/usr/bin:/bin'}
            run=subprocess.run(['sh',str(wrapper)],cwd=ROOT,env=env,capture_output=True,timeout=30)
            self.assertEqual(run.returncode,1)
            self.assertEqual((folder/'phases').read_text(),'0\n1\n2\n')
            self.assertEqual(json.loads((folder/'comparison.json').read_text()),{'passed':0})
            self.assertIn('{"passed":0}',(folder/'run.out').read_text())

    def test_comparison_cli_argument_contract(self):
        result=subprocess.run(['python3','-I','-B',str(ROOT/'compare_v2.py'),'--help'],
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0)
        self.assertIn('--results',result.stdout)

    def test_small_bad_output_cannot_hide_in_aggregate(self):
        fixture=load('test_compare_v2')
        from copy import deepcopy
        record,reservation,attempt,controls=fixture.fixtures()
        other=deepcopy(record)
        other.update(job_id='synthetic2',replay_id='synthetic2:0:delta-v2')
        record['reference_usage']['output_tokens']=1000
        attempt['usage']['output_tokens']=100
        fixture.refresh(attempt)
        second_res=deepcopy(reservation)
        second_res.update(job_id='synthetic2',replay_id='synthetic2:0:delta-v2')
        second=deepcopy(attempt)
        second.update(job_id='synthetic2',replay_id='synthetic2:0:delta-v2')
        second['usage']['output_tokens']=50
        fixture.refresh(second)
        report=fixture.compare.compare_records([record,other],[reservation,attempt,second_res,second],controls)
        self.assertLess(report['total']['output_ratio'],.4)
        self.assertEqual(report['output_pass'],0)
        self.assertEqual(report['passed'],0)

if __name__ == '__main__':
    unittest.main()
