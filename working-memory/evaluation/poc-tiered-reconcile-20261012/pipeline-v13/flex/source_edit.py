"""Owner-authored source corrections, pinned to an archived original and job.

This module never invokes a model. Editing only stages a generation; acceptance
uses the separate immutable generation review. Links are explicit choices.
"""
from copy import deepcopy
from datetime import datetime,timezone
import json,re
from uuid import UUID

from canonical_archive import verify_document
from generation_review import logical_entries,materialize
from generation_service import stage as stage_generation
from journal_projection import prepare_source,apply_saved,digest
from journal_store import RevisionConflict
from memory import ValidationError,known_work_ids,overview

PIPELINE='owner-reviewed-source-v1'
FIELDS={'matter','matter_id','kind','title','claim','owner','commitment_strength','due_text','update_target','update','uncertainty','required_review','action_uncertainty','condition_text','work_state','evidence_ids','state_evidence_ids'}

def _job(service,identity,job_id):
    space=service.store.space();service.authorize(identity,space)
    if not isinstance(job_id,str) or not re.fullmatch('[0-9a-f]{64}',job_id):raise ValidationError('Invalid job identity')
    detail=service.store.call('job_detail',job_id=job_id)
    if not detail or detail['job']['space_id']!=space['id'] or detail['job']['id']!=job_id:raise ValidationError('Unknown source job')
    job=detail['job']
    document=verify_document(service.store.call('archive_document',document_id=job['document_id']))
    if document['source_id']!=job['source_id'] or document['event_date']!=job['event_date']:raise ValidationError('Job document mismatch')
    active=job['state'] in ('running','prepared') and job.get('lease_until') and datetime.fromisoformat(job['lease_until'].replace('Z','+00:00'))>datetime.now(timezone.utc)
    available=job['state'] not in ('applied','archived','queued') and not active
    return space,job,document,bool(available)

def _units(document):return {f'U{i:04d}':line for i,line in enumerate(document['body'].splitlines(),1) if line.strip()}

def _base(service,revision,document):
    base=logical_entries(service.store.entries(through=revision))
    previous=next((i for i,e in enumerate(base) if e['kind']=='source' and e['source']['source_id']==document['source_id']),None)
    at=previous if previous is not None else next((i for i,e in enumerate(base) if e['kind']=='source' and e['source']['event_date']>document['event_date']),len(base))
    db,_=materialize(base[:at])
    return base,previous,db

def _rows(db,where='',args=()):
    return [{**json.loads(r['data_json']),'id':r['id'],'matter_id':r['matter_id']} for r in db.execute('select * from observations '+where,args)]

def inspect(service,identity,job_id):
    space,job,document,available=_job(service,identity,job_id)
    base,previous,db=_base(service,space['revision'],document);units=_units(document)
    try:
        known=known_work_ids(db,document['event_date']);state=overview(db,document['event_date'])
        works=[{key:r.get(key) for key in ('id','title','owner','status','condition_text')} for group in ('personal','waiting_dependencies','waiting','completed') for r in state[group]]
        topics=[dict(r) for r in db.execute('select id,title from matters')]
    finally:db.close()
    full,_=materialize(base)
    try:
        old_version=base[previous]['source']['id'] if previous is not None else None
        old=_rows(full,'where source_version=?',(old_version,)) if old_version else []
        old_topic_ids={r['matter_id'] for r in old}
        old_topics=[dict(r) for r in full.execute('select id,title from matters') if r['id'] in old_topic_ids]
    finally:full.close()
    # Only the prepared result belonging to this exact document may prefill an
    # editor. Old-source text is shown separately, never silently re-attributed.
    saved=(job.get('prepared_payload') or {}).get('proposal',{}).get('observations',[])
    editable=[]
    for row in saved:
        if not isinstance(row,dict):continue
        value={k:deepcopy(row.get(k)) for k in FIELDS}
        for key,default in [('title',''),('claim',''),('matter',''),('commitment_strength','not_applicable'),('update','none'),('work_state','not_applicable'),('required_review',False)]:
            if value[key] is None:value[key]=default
        value['evidence_ids']=[key for key,line in units.items() if any(isinstance(q,str) and q.strip() and q in line for q in row.get('quotes',[]))]
        value['state_evidence_ids']=[key for key in value['evidence_ids'] if any(isinstance(q,str) and q.strip() and q in units[key] for q in row.get('state_quotes',[]))]
        if value['matter_id'] not in {t['id'] for t in topics}:value['matter_id']=None
        if value['update_target'] not in known:value['update_target']=None;value['update']='none'
        editable.append(value)
    return {'job_id':job_id,'expected_revision':space['revision'],'expected_updated_at':job['updated_at'],'can_edit':available,
            'document':{'id':document['id'],'title':document['title'],'event_date':document['event_date'],'units':units},
            'observations':editable,'previous_observations':old,'previous_topics':old_topics,'existing_work':works,'existing_topics':topics,
            'unknown_provider_outcome':any(not c['received'] for c in service.store.call('job_detail',job_id=job_id)['calls'])}

def stage(service,identity,request):
    fields={'job_id','review_id','expected_revision','expected_updated_at','reason','observations','identity_links','topic_links'}
    if not isinstance(request,dict) or set(request)!=fields:raise ValidationError('Invalid source edit')
    review_id=str(UUID(request['review_id']))
    space,job,document,available=_job(service,identity,request['job_id'])
    expected=request['expected_revision']
    if type(expected) is not int or not 0<=expected<=space['revision']:raise RevisionConflict('Source edit base changed')
    existing=service.store.call('generation_review',review_id=review_id)
    if not existing and (not available or expected!=space['revision'] or request['expected_updated_at']!=job['updated_at']):raise RevisionConflict('Source edit job changed')
    if not isinstance(request['reason'],str) or not 1<=len(request['reason'].strip())<=3000:raise ValidationError('Review reason required')
    rows=request['observations']
    if not isinstance(rows,list) or len(rows)>150:raise ValidationError('Source edit observation limit')
    units=_units(document);proposal=[]
    for raw in rows:
        if not isinstance(raw,dict) or set(raw)!=FIELDS:raise ValidationError('Incomplete source observation')
        o=deepcopy(raw)
        for field,target in [('evidence_ids','quotes'),('state_evidence_ids','state_quotes')]:
            ids=o.pop(field)
            if not isinstance(ids,list) or len(ids)>500 or any(not isinstance(key,str) or key not in units for key in ids):raise ValidationError('Evidence must be selected from this original')
            o[target]=[units[key] for key in dict.fromkeys(ids)]
        if o['commitment_strength'] not in ('explicit','accepted_request','reported','conditional','not_applicable'):raise ValidationError('Invalid commitment strength')
        if o['update']!='none' and not o['update_target']:raise ValidationError('An update needs an explicitly selected existing task')
        if o['kind']=='commitment' and o['commitment_strength'] in ('explicit','accepted_request') and not o['owner']:raise ValidationError('A promise needs an identified person')
        proposal.append(o)
    base,previous,db=_base(service,expected,document)
    source={'id':job['id'],'source_id':document['source_id'],'content_hash':document['body_hash'],'event_date':document['event_date'],
            'title':document['title'],'transcript':document['body'],'observed_at':document['observed_at']}
    try:
        payload=prepare_source(db,source,{'observations':proposal,'coverage_notes':['Vom angemeldeten Eigentümer am archivierten Original manuell geprüft. '+request['reason']]},
            pipeline=PIPELINE,model='owner_manual_review',provenance={'mode':'owner_source_edit','owner_id':identity['id'],'review_id':review_id,
            'job_id':job['id'],'context_revision':expected,'edit_request_sha256':digest(request),'model_api_calls':0})
        apply_saved(db,source,payload)
        new=_rows(db,'where source_version=? order by rowid',(source['id'],))
    finally:db.close()
    def links(values,field):
        if not isinstance(values,list):raise ValidationError('Explicit source identity links required')
        result=[]
        for link in values:
            if not isinstance(link,dict) or set(link)!={'old_id','new_index','reason'} or type(link['new_index']) is not int or not 0<=link['new_index']<len(new):raise ValidationError('Invalid source identity selection')
            result.append({'old_id':link['old_id'],'new_id':new[link['new_index']][field],'reason':link['reason']})
        return result
    entry={'kind':'source','source':source,'payload':payload}
    return stage_generation(service,identity,{'review_id':review_id,'expected_revision':expected,'label':'Original neu prüfen: '+document['title'],
        'changes':[{'source_id':document['source_id'],'action':'replace' if previous is not None else 'add','entry':entry,'reason':request['reason']}],
        'identity_links':links(request['identity_links'],'id'),'topic_links':links(request['topic_links'],'matter_id'),'reason':request['reason'],'job_id':job['id']})
