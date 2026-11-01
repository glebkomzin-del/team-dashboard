"""Offline metadata diagnostics and real worker isolation-branch checks."""
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import canonical_worker as cw
from durable_calls import OutcomeUnknown
from memory import ValidationError
from journal_store import JournalUnavailable


class DiagnosticTests(unittest.TestCase):
    def test_exact_json_metadata_and_control_removal(self):
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            cw.job_failed_diagnostic('abcdefgh1234','validation_failed',ValidationError('Invalid\n coverage\x00: SECRET'))
        lines=output.getvalue().splitlines()
        self.assertEqual(len(lines),1)
        self.assertEqual(json.loads(lines[0]),{'event':'job_failed','job':'abcdefgh',
            'reason':'validation_failed','error_type':'ValidationError','stage':None,'message':'Invalid coverage'})
        self.assertNotIn('SECRET',output.getvalue())

    def test_all_quote_boundaries(self):
        for delimiter in ('"',"'",'“','”','‘','’','«','»',':'):
            with self.subTest(delimiter=delimiter):
                output=io.StringIO()
                with contextlib.redirect_stderr(output):
                    cw.job_failed_diagnostic('id','validation_failed',ValidationError('Bad value '+delimiter+'SECRET'))
                self.assertEqual(json.loads(output.getvalue())['message'],'Bad value ')

    def test_message_limit(self):
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            cw.job_failed_diagnostic('id','validation_failed',ValidationError('a'*400))
        self.assertEqual(len(json.loads(output.getvalue())['message']),240)

    def test_last_traceback_function_is_stage(self):
        def failing_stage(): raise ValidationError('Invalid coverage')
        try: failing_stage()
        except ValidationError as error:
            output=io.StringIO()
            with contextlib.redirect_stderr(output):cw.job_failed_diagnostic('id','validation_failed',error)
        self.assertEqual(json.loads(output.getvalue())['stage'],'failing_stage')

    def test_unprintable_exception_cannot_change_result(self):
        class Unprintable(ValidationError):
            def __str__(self):raise RuntimeError('unprintable')
        output=io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertIsNone(cw.job_failed_diagnostic('id','validation_failed',Unprintable()))
        self.assertEqual(json.loads(output.getvalue())['message'],'')

    def test_stderr_failure_cannot_change_result(self):
        with patch.object(cw.sys,'stderr') as stderr:
            stderr.write.side_effect=OSError('closed')
            self.assertIsNone(cw.job_failed_diagnostic('id','validation_failed',ValidationError('Bad')))


class IsolationBranchTests(unittest.TestCase):
    def run_failure(self,error,isolated=True,isolation_error=None,early=False):
        calls=[]
        job={'id':'abcdefgh1234','state':'running','lease_token':'lease','pipeline':'pipeline',
             'document_id':'document','source_id':'source','expected_revision':0}
        document={'source_id':'source','body_hash':'hash','event_date':'2026-10-13',
                  'observed_at':'2026-10-13','title':'synthetic','body':'synthetic fixture','id':'document'}
        store=Mock(space_id='space')
        def call(operation,**kw):
            calls.append((operation,kw))
            if operation=='claim_job':return job
            if operation=='archive_document':return {'space_id':'space'}
            if operation=='processing_status':return {'config':{'enabled':not early,'automatic_from':'2026-10-01'}}
            if operation=='job_detail':return {'calls':[]}
            if operation=='isolate_failed_job':
                if isolation_error:raise isolation_error
                return {'isolated':isolated}
            if operation=='pause_job':return {'paused':True}
            raise AssertionError(operation)
        store.call.side_effect=call
        store.space.return_value={'owner_id':'owner'}
        service=Mock(store=store,cache=Mock())
        archive=Mock()
        archive.execute.return_value.fetchone.return_value=(0,'main','/unused/archive.sqlite')
        service.archive_projection.return_value=contextlib.nullcontext((archive,None))
        worker=object.__new__(cw.CanonicalWorker)
        worker.service=service;worker.store=store;worker.model='synthetic';worker.pipeline='pipeline'
        worker.outbox=Path('/unused');worker.api=Mock();worker.schema={};worker.token_counter=None
        output=io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(cw,'drain_outbox'))
            stack.enter_context(patch.object(cw,'uuid4',return_value='lease'))
            stack.enter_context(patch.object(cw,'verify_document',return_value=document))
            stack.enter_context(patch.object(cw,'fingerprint',return_value=job['id']))
            stack.enter_context(patch.object(cw,'rebuild'))
            stack.enter_context(patch.object(cw,'open_readonly',return_value=Mock()))
            stack.enter_context(patch.object(cw,'connect',return_value=Mock()))
            stack.enter_context(patch.object(cw,'DurableCalls',return_value=Mock()))
            stack.enter_context(patch.object(cw.tempfile,'TemporaryDirectory',return_value=contextlib.nullcontext('/unused')))
            stack.enter_context(patch('sqlite3.connect',return_value=Mock()))
            stack.enter_context(patch.object(cw.processor,'process',side_effect=error))
            stack.enter_context(contextlib.redirect_stderr(output))
            result=worker._step()
        return result,output.getvalue(),calls

    def test_confirmed_validation_failure_one_line(self):
        result,output,calls=self.run_failure(ValidationError('Coverage invalid: SECRET'))
        self.assertEqual(result,{'state':'review','reason':'validation_failed','job_id':'abcdefgh1234','technical_isolation':True})
        self.assertEqual(len(output.splitlines()),1)
        self.assertEqual(json.loads(output)['message'],'Coverage invalid')
        self.assertEqual(json.loads(output)['reason'],'validation_failed')
        self.assertEqual([op for op,_ in calls].count('isolate_failed_job'),1)
        self.assertNotIn('pause_job',[op for op,_ in calls])

    def test_confirmed_outcome_unknown_one_line(self):
        result,output,_=self.run_failure(OutcomeUnknown('Unknown outcome'))
        self.assertEqual(result['state'],'review')
        self.assertEqual(json.loads(output)['reason'],'provider_outcome_unknown')

    def test_unconfirmed_isolation_stays_paused_without_line(self):
        result,output,calls=self.run_failure(ValidationError('Invalid'),isolated=False)
        self.assertEqual(result['state'],'paused')
        self.assertEqual(output,'')
        self.assertIn('pause_job',[op for op,_ in calls])

    def test_isolation_storage_failure_no_line(self):
        result,output,_=self.run_failure(ValidationError('Invalid'),isolation_error=JournalUnavailable('Unavailable'))
        self.assertEqual(result['reason'],'isolation_unconfirmed')
        self.assertEqual(output,'')

    def test_failure_before_processing_no_line(self):
        result,output,calls=self.run_failure(ValidationError('Unused'),early=True)
        self.assertEqual(result['state'],'paused')
        self.assertEqual(output,'')
        self.assertNotIn('isolate_failed_job',[op for op,_ in calls])

    def test_other_exception_preserves_propagation(self):
        with self.assertRaisesRegex(RuntimeError,'Synthetic failure'):
            self.run_failure(RuntimeError('Synthetic failure'))


if __name__=='__main__':unittest.main()
