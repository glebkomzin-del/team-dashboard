"""Short HTTP polling boundary around the durable original-deletion ledger."""
from dataclasses import dataclass,field
import hashlib,json,threading,time

from journal_store import RevisionConflict
from memory import ValidationError


class DeletionCapacity(RuntimeError):pass


def _fingerprint(value):
    try:body=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    except (TypeError,ValueError):raise ValidationError('Invalid deletion request') from None
    return hashlib.sha256(body.encode()).hexdigest()


@dataclass
class _Job:
    fingerprint:str
    started_at:float=field(default_factory=time.monotonic)
    done:bool=False
    result:dict|None=None
    error:Exception|None=None
    event:threading.Event=field(default_factory=threading.Event)


class DeletionJobs:
    def __init__(self,*,retention_seconds=3600,max_jobs=1):
        self.retention_seconds=retention_seconds;self.max_jobs=max_jobs
        self.lock=threading.Lock();self.jobs={}

    def submit(self,executor,service,identity,request,*,wait_seconds=0):
        if not isinstance(wait_seconds,(int,float)) or isinstance(wait_seconds,bool) or not 0<=wait_seconds<=25:
            raise ValueError('Invalid deletion wait')
        if not isinstance(identity,dict) or not isinstance(identity.get('id'),str) or not isinstance(request,dict) \
          or not isinstance(request.get('deletion_id'),str):
            raise ValidationError('Invalid deletion request')
        key=(identity['id'],request['deletion_id']);fingerprint=_fingerprint(request);now=time.monotonic()
        with self.lock:
            self.jobs={job_key:job for job_key,job in self.jobs.items()
                       if not job.done or now-job.started_at<self.retention_seconds}
            job=self.jobs.get(key)
            if job:
                if job.fingerprint!=fingerprint:raise RevisionConflict('Deletion identity changed')
                if job.done:return self._take(key,job)
                launch=False
            else:
                if sum(not value.done for value in self.jobs.values())>=self.max_jobs:
                    raise DeletionCapacity('Deletion worker capacity reached')
                job=_Job(fingerprint);self.jobs[key]=job;launch=True
        if launch:
            copied_identity=dict(identity);copied_request=json.loads(json.dumps(request,ensure_ascii=False))
            threading.Thread(target=self._run,args=(executor,service,copied_identity,copied_request,key,job),
                daemon=True,name='memory-deletion-'+request['deletion_id'][:8]).start()
        if wait_seconds and job.event.wait(wait_seconds):
            with self.lock:return self._take(key,job)
        return {'state':'processing','deletion_id':request['deletion_id']}

    def _take(self,key,job):
        if self.jobs.get(key) is job:del self.jobs[key]
        if job.error:raise job.error
        return job.result

    def _run(self,executor,service,identity,request,key,job):
        try:result=executor(service,identity,request);error=None
        except Exception as caught:result=None;error=caught
        with self.lock:
            if self.jobs.get(key) is job:
                job.result=result;job.error=error;job.done=True;job.event.set()


__all__=['DeletionJobs','DeletionCapacity']
