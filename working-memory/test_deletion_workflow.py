from contextlib import contextmanager,nullcontext
import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch

from deletion_workflow import DeletionPending,_expected_sparse,_prepare_private_runtime,execute,rebuild_registered_caches,registered_cache_directories
from memory import connect,ValidationError
from original_deletion import prepare_redacted_entry
from test_original_deletion import fixture,PREPARED_AT

OWNER={'id':'20000000-0000-4000-8000-000000000001','role':'owner'}
DELETION='30000000-0000-4000-8000-000000000001'


class WorkflowStore:
 def __init__(self,source_id,packages,state=None,checks=None):
  self.source_id=source_id;self.packages=packages;self.state=state;self.checks=checks or {};self.calls=[]
 def space(self):return {'id':'space','owner_id':OWNER['id'],'deletion_revision':2}
 def call(self,op,**fields):
  self.calls.append((op,fields))
  if op=='source_deletion_status':
   return None if self.state is None else {'deletion_id':DELETION,'source_id':self.source_id,'state':self.state,'packages':self.packages,'checks':dict(self.checks)}
  if op=='source_deletion_check':self.checks[fields['check_scope']]=fields['receipt'];return {'saved':True}
  if op=='source_deletion_finalize':self.state='verified';return {'state':'verified'}
  if op=='source_deletion_ledger':return [{'deletion_id':DELETION,'source_id':self.source_id,'state':self.state,'ledger_revision':2}]
  raise AssertionError(op)


class Service:
 def __init__(self,store,cache):self.store=store;self.cache=Path(cache);self.private_outboxes=[];self.cleared=0
 def authorize(self,identity,space):
  if identity!=OWNER:raise PermissionError
 def exclusive_privacy_maintenance(self):return nullcontext()
 def clear_private_runtime(self):self.cleared+=1


class DeletionWorkflowTests(unittest.TestCase):
 def package(self):
  entry=fixture();return entry,prepare_redacted_entry(entry,deletion_id=DELETION,prepared_at=PREPARED_AT)
 def test_new_workflow_orders_purge_cache_barrier_and_finalize(self):
  entry,package=self.package();store=WorkflowStore(entry['source']['source_id'],[package]);service=Service(store,'/tmp/cache')
  def stage(*_args,**_kwargs):store.state='prepared';return {'packages':[package]}
  def purge(*_args,**_kwargs):store.state='purging';return {'state':'purging'}
  with patch('deletion_workflow.stage_and_plan',side_effect=stage),patch('deletion_workflow.purge',side_effect=purge),\
       patch('deletion_workflow.rebuild_registered_caches',side_effect=lambda *_a,**_k:store.checks.update(local_caches={'ok':True})),\
       patch('deletion_workflow.persist_restore_barrier',return_value={'restore_ledger_persisted':True,'retention_policy':'14-latest-plus-8-observed-weeks','minimum_deletion_revision':2}):
   result=execute(service,OWNER,{'deletion_id':DELETION,'source_id':entry['source']['source_id']})
  self.assertEqual(result['state'],'verified')
  operations=[op for op,_ in store.calls]
  self.assertLess(operations.index('source_deletion_check'),operations.index('source_deletion_finalize'))
 def test_purging_workflow_resumes_without_original_or_second_purge(self):
  entry,package=self.package();store=WorkflowStore(entry['source']['source_id'],[package],state='purging',checks={'local_caches':{'ok':True}});service=Service(store,'/tmp/cache')
  with patch('deletion_workflow.stage_and_plan') as stage,patch('deletion_workflow.purge') as purge,\
       patch('deletion_workflow.persist_restore_barrier',return_value={'restore_ledger_persisted':True,'retention_policy':'14-latest-plus-8-observed-weeks','minimum_deletion_revision':2}):
   self.assertEqual(execute(service,OWNER,{'deletion_id':DELETION,'source_id':entry['source']['source_id']})['state'],'verified')
  stage.assert_not_called();purge.assert_not_called()
 def test_archive_only_purging_workflow_resumes_with_empty_packages(self):
  store=WorkflowStore('drive:archive-only',[],state='purging',checks={'local_caches':{'ok':True}});service=Service(store,'/tmp/cache')
  with patch('deletion_workflow.stage_and_plan') as stage,patch('deletion_workflow.purge') as purge,\
       patch('deletion_workflow.persist_restore_barrier',return_value={'restore_ledger_persisted':True,'retention_policy':'14-latest-plus-8-observed-weeks','minimum_deletion_revision':2}):
   self.assertEqual(execute(service,OWNER,{'deletion_id':DELETION,'source_id':'drive:archive-only'})['state'],'verified')
  stage.assert_not_called();purge.assert_not_called()
 def test_registered_cache_invalidation_is_bounded_and_rebuild_is_evidence_only(self):
  entry,package=self.package()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);active=root/'projections';retired=root/'retired';backup=root/'backups'
   for directory in (active,active/'archive',retired,retired/'archive',backup):directory.mkdir(parents=True,exist_ok=True)
   for directory in (active,active/'archive',retired,retired/'archive'):(directory/'space-1.sqlite').write_text(entry['source']['transcript'])
   (retired/'.space-projection-interrupted.sqlite').write_text(entry['source']['transcript'])
   protected=backup/'space-1.sqlite';protected.write_text(entry['source']['transcript'])
   work=connect(':memory:');source=package['source']
   work.execute('insert into source_versions values (?,?,?,?,?,?,?)',(source['id'],source['source_id'],source['content_hash'],
    source['event_date'],0,source['title'],_expected_sparse(package)))
   archive=connect(':memory:');archive.execute('create table documents(source_id text)')
   store=WorkflowStore(entry['source']['source_id'],[package],state='purging');service=Service(store,active)
   service.exclusive_cache_maintenance=lambda:nullcontext()
   service.warm_projection=Mock()
   @contextmanager
   def projection(_identity):yield work,store.space()
   @contextmanager
   def archive_projection(_identity):yield archive,store.space()
   service.projection=projection;service.archive_projection=archive_projection
   receipt=rebuild_registered_caches(service,OWNER,deletion_id=DELETION,source_id=entry['source']['source_id'],packages=[package],configured='retired')
   self.assertEqual(receipt['files_removed'],5);self.assertTrue(protected.exists())
   self.assertFalse(any(retired.rglob('space-*.sqlite*')))
   work.close();archive.close()
 def test_cache_registry_rejects_backup_or_outside_paths(self):
  with tempfile.TemporaryDirectory() as tmp:
   service=Service(Mock(),Path(tmp)/'projections')
   with self.assertRaises(ValidationError):registered_cache_directories(service,'backups')
   with self.assertRaises(ValidationError):registered_cache_directories(service,str(Path(tmp).parent/'outside'))
 def test_private_runtime_removes_disposable_worker_and_blocks_unknown_receipt(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);cache=root/'projections';cache.mkdir();worker=cache/'worker-crashed';worker.mkdir();(worker/'scratch.sqlite').write_text('private')
   service=Service(WorkflowStore('drive:x',[]),cache)
   receipt=_prepare_private_runtime(service,configured_caches='')
   self.assertEqual(receipt['worker_sandboxes_removed'],1);self.assertFalse(worker.exists());self.assertEqual(service.cleared,1)
   outbox=cache/'response-outbox';outbox.mkdir();(outbox/'.receipt-incomplete').write_text('private')
   with self.assertRaises(DeletionPending):_prepare_private_runtime(service,configured_caches='')


if __name__=='__main__':unittest.main()
