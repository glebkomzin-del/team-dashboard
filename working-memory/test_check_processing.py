import unittest

from check_processing import ERROR, MISMATCH, diagnose


class Store:
    def __init__(self, configured_pipeline):
        self.configured_pipeline = configured_pipeline
        self.calls = []

    def space(self):
        self.calls.append(('space', {}))
        return {'id': 'secret-space', 'owner_id': 'secret-owner', 'label': 'secret-label',
                'state': 'active', 'revision': 19, 'archive_revision': 81}

    def call(self, operation, **fields):
        self.calls.append((operation, fields))
        if operation != 'processing_status':
            raise AssertionError(operation)
        return {'config': {'enabled': True, 'automatic_from': '2026-09-10',
                           'pipeline': self.configured_pipeline, 'secret': 'hidden'},
                'pending_count': 4, 'archived_count': 70,
                'jobs': [{'title': 'private meeting'}], 'token': 'hidden'}


class ProcessingPreflightTest(unittest.TestCase):
    def test_matching_pipeline_is_ready_and_uses_read_calls_only(self):
        pipeline = 'v11:compact1:gate1:gpt-5.6-terra:aaaa:canonical1:bbbb'
        store = Store(pipeline)
        result, exit_code = diagnose(store, pipeline)
        self.assertEqual(exit_code, 0)
        self.assertTrue(result['ok'])
        self.assertEqual(result['status'], 'ready')
        self.assertEqual(store.calls, [('space', {}), ('processing_status', {})])

    def test_mismatch_is_nonzero_and_diagnostic_is_redacted(self):
        configured = 'v11:compact1:gate1:gpt-5.6-terra:25495068bcd57832:canonical1:4b4bf0c190a6a2c3'
        runtime = 'v11:compact1:gate1:gpt-5.6-terra:4da0ae459ab7417a:canonical1:4b4bf0c190a6a2c3'
        store = Store(configured)
        result, exit_code = diagnose(store, runtime)
        self.assertEqual(exit_code, MISMATCH)
        self.assertEqual(result['status'], 'pipeline_mismatch')
        self.assertEqual(result['processing']['configured_pipeline'], configured)
        self.assertEqual(result['processing']['runtime_pipeline'], runtime)
        rendered = repr(result)
        for private in ('secret-space', 'secret-owner', 'secret-label', 'private meeting', 'hidden'):
            self.assertNotIn(private, rendered)

    def test_missing_configuration_is_an_error(self):
        store = Store(None)
        result, exit_code = diagnose(store, 'v11:compact1:gate1:gpt-5.6-terra:new:canonical1:new')
        self.assertEqual(exit_code, ERROR)
        self.assertEqual(result['status'], 'configuration_missing')


if __name__ == '__main__':
    unittest.main()
