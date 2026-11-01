"""Synthetic structural checks; no input records or credentials are used."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('structure_common', Path(__file__).with_name('replay_common.py'))
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)


class SchemaStructureTests(unittest.TestCase):
    def test_valid_and_invalid_answer(self):
        schema = {'type': 'object', 'properties': {'7': {'enum': ['unchanged']}},
                  'required': ['7'], 'additionalProperties': False}
        self.assertTrue(common.validate_schema_structure(schema))
        self.assertEqual(common.schema_errors({'7': 'unchanged'}, schema), [])
        self.assertTrue(common.schema_errors({}, schema))

    def test_empty_enum_and_missing_reference_rejected(self):
        for schema in ({'enum': []}, {'$ref': '#/$defs/missing'}, {'$ref': 'https://invalid.example/schema'}):
            with self.assertRaises(ValueError):
                common.validate_schema_structure(schema)

    def test_malformed_required_and_unsupported_keyword(self):
        for schema in ({'required': ['7', '7']}, {'required': '7'}, {'unknownKeyword': True}, {'type': 'unknown'}):
            with self.assertRaises(ValueError):
                common.validate_schema_structure(schema)

    def test_local_reference_and_literal_bool(self):
        schema = {'$defs': {'flag': {'enum': [True]}}, '$ref': '#/$defs/flag'}
        self.assertTrue(common.validate_schema_structure(schema))
        self.assertEqual(common.schema_errors(True, schema), [])
        self.assertTrue(common.schema_errors(1, schema))


if __name__ == '__main__':
    unittest.main()
