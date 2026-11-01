import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import make_manifest


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.manifest = {'openai_provider.py': '0' * 64, 'call_budget.py': '1' * 64,
                         'durable_calls.py': 'A' * 64, 'evaluation/schema.json': 'b' * 64}
        for name in make_manifest.TARGETS:
            (self.directory / name).write_bytes(('synthetic ' + name).encode())

    def test_only_two_entries_change(self):
        result = make_manifest.updated_manifest(self.manifest, self.directory)
        self.assertEqual(set(result), set(self.manifest))
        self.assertEqual(self.manifest['openai_provider.py'], '0' * 64)
        for name in make_manifest.TARGETS:
            self.assertEqual(result[name], hashlib.sha256((self.directory / name).read_bytes()).hexdigest())
        for name in set(result) - set(make_manifest.TARGETS):
            self.assertEqual(result[name], self.manifest[name])

    def test_duplicate_keys_rejected(self):
        with self.assertRaises(ValueError):
            json.loads('{"a":"b","a":"c"}', object_pairs_hook=make_manifest.unique_object)

    def test_missing_target_rejected(self):
        del self.manifest['openai_provider.py']
        with self.assertRaises(ValueError):
            make_manifest.updated_manifest(self.manifest, self.directory)

    def test_non_sha_or_nested_format_rejected(self):
        for value in ('not-sha', None, 123, {'hash': '0' * 64}):
            with self.subTest(kind=type(value).__name__):
                self.manifest['durable_calls.py'] = value
                with self.assertRaises(ValueError):
                    make_manifest.updated_manifest(self.manifest, self.directory)

    def test_non_mapping_or_empty_rejected(self):
        for value in ([], None, {}):
            with self.assertRaises(ValueError):
                make_manifest.updated_manifest(value, self.directory)

    def test_overlay_docker_contract(self):
        text = (Path(__file__).parent / 'overlay' / 'Dockerfile').read_text()
        self.assertIn('ARG OLD_TAG\nFROM ${OLD_TAG}\nUSER root\n', text)
        self.assertIn('COPY --chown=10001:10001 openai_provider.py call_budget.py build-manifest.json /app/', text)
        self.assertTrue(text.endswith('USER 10001:10001\n'))

    def test_overlay_matches_tested_files(self):
        root = Path(__file__).parent
        for name in make_manifest.TARGETS:
            self.assertEqual((root / name).read_bytes(), (root / 'overlay' / name).read_bytes())


if __name__ == '__main__':
    unittest.main()
