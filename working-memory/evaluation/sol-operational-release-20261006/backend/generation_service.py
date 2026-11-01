"""Durable generation previews and owner decisions; saved evidence only."""
from copy import deepcopy
from contextlib import nullcontext
from functools import wraps
import json,re
from uuid import UUID

from generation_review import logical_entries,compile_generation,verify_generation,expand_generation,materialize
from journal_projection import digest
from journal_store import RevisionConflict
from memory import ValidationError


def make_plan(base,changes,identity_links,topic_links,source_order_review=None):
    if not isinstance(changes,list) or (not changes and source_order_review is None):raise ValidationError('Explicit source changes required')
    plan=deepcopy(base);reviews={};seen=set()
    for change in changes:
        if not isinstance(change,dict) or set(change)!={'source_id','action','entry','reason'} or change['action'] not in ('add','replace','remove'):
            raise ValidationError('Invalid source replacement')
        key=change['source_id']
        if key in seen or not isinstance(change['reason'],str) or not 1<=len(change['reason'].strip())<=3000:raise ValidationError('Duplicate source change or missing reason')
        seen.add(key);reviews[key]=change['reason']
        index=next((n for n,e in enumerate(plan) if e['kind']=='source' and e['source']['source_id']==key),None)
        if change['action']=='remove':
            if index is None or change['entry'] is not None:raise ValidationError('Invalid source removal')
            plan.pop(index);continue
        entry=change['entry']
        if not isinstance(entry,dict) or entry.get('kind')!='source' or entry.get('source',{}).get('source_id')!=key:raise ValidationError('Replacement source identity mismatch')
        if change['action']=='replace':
            if index is None:raise ValidationError('Replacement source is absent')
            plan[index]=deepcopy(entry)
        else:
            if index is not None:raise ValidationError('Added source already exists')
            index=next((n for n,e in enumerate(plan) if e['kind']=='source' and e['source']['event_date']>entry['source']['event_date']),len(plan))
            plan.insert(index,deepcopy(entry))
    def links(values):
        if not isinstance(values,list):raise ValidationError('Explicit identity links required')
        result={};destinations=set()
        for value in values:
            if not isinstance(value,dict) or set(value)!={'old_id','new_id','reason'} or not isinstance(value['reason'],str) or not 1<=len(value['reason'].strip())<=1000:
                raise ValidationError('Invalid identity link')
            if value['old_id'] in result or value['new_id'] in destinations:raise ValidationError('Identity links must be one-to-one')
            result[value['old_id']]=value['new_id'];destinations.add(value['new_id'])
        return result
    work=links(identity_links);topics=links(topic_links)
    for entry in plan:
        if entry['kind']=='human':
            target=entry['payload']['target_id'];entry['payload']['target_id']=work.get(target,target)
            continue
        before=digest(entry)
        for observation in entry['payload']['proposal']['observations']:
            if observation.get('update_target') in work:observation['update_target']=work[observation['update_target']]
            if observation.get('matter_id') in topics:observation['matter_id']=topics[observation['matter_id']]
        for link in entry['payload'].get('matter_links',[]):
            for field in ('from_id','to_id'):
                if link[field] in topics:link[field]=topics[link[field]]
        if digest(entry)!=before:
            key=entry['source']['source_id']
            explanation='Explizite vorgeschlagene Identitätsverknüpfungen auf vorhandene Folgebezüge angewandt.'
            topic_reasons=' '.join(link['old_id']+' → '+link['new_id']+': '+link['reason'] for link in topic_links)
            reviews[key]=(reviews.get(key,'')+' '+explanation+' '+topic_reasons).strip()
            if len(reviews[key])>4000:raise ValidationError('Source linkage review is too long; split the proposal')
    if source_order_review is not None:
        if not isinstance(source_order_review,dict) or set(source_order_review)!={'before','after','reason'}:
            raise ValidationError('Invalid explicit source-order review')
        retained={e['source']['source_id'] for e in base if e['kind']=='source'}&{e['source']['source_id'] for e in plan if e['kind']=='source'}
        order=source_order_review['after']
        if not isinstance(order,list) or any(not isinstance(k,str) for k in order) or len(order)!=len(retained) or set(order)!=retained:
            raise ValidationError('Source-order review must include each retained source exactly once')
        entries={e['source']['source_id']:e for e in plan if e['kind']=='source'}
        ordered=iter(order)
        plan=[entries[next(ordered)] if e['kind']=='source' and e['source']['source_id'] in retained else e for e in plan]
    return plan,reviews


def _scope(service,identity,*,staging=False):
    space=service.store.space()
    if not (staging and identity.get('role')=='service'):service.authorize(identity,space)
    return space


def _base(service,space):
    if hasattr(service,'generation_base'):return service.generation_base(space)
    return logical_entries(service.store.entries(through=space['revision']))


def _generation_operation(function):
    @wraps(function)
    def guarded(service,*args,**kwargs):
        with service.generation_reader() if hasattr(service,'generation_reader') else nullcontext():
            return function(service,*args,**kwargs)
    return guarded


@_generation_operation
def stage(service,identity,request):
    keys={'review_id','expected_revision','label','changes','identity_links','topic_links','reason','job_id'}
    if not isinstance(request,dict) or set(request) not in (keys,keys|{'source_order_review'}):raise ValidationError('Invalid generation staging request')
    review_id=str(UUID(request['review_id']));space=_scope(service,identity,staging=True)
    expected=request['expected_revision']
    if type(expected) is not int or not 0<=expected<=space['revision']:raise RevisionConflict('Generation base changed')
    previous=service.store.call('generation_review',review_id=review_id)
    if previous and previous.get('space_id')!=space['id']:raise ValidationError('Generation review scope mismatch')
    if not previous and expected!=space['revision']:raise RevisionConflict('Generation base changed')
    order_review=request.get('source_order_review')
    base=_base(service,{**space,'revision':expected});plan,reviews=make_plan(base,request['changes'],request['identity_links'],request['topic_links'],order_review)
    hash_format=previous['payload'].get('state_hash_format') if previous else 'canonical-knowledge-v1'
    topic_audit=None if previous and 'topic_identity_links' not in previous['payload'] else request['topic_links']
    payload=compile_generation(base,plan,source_reviews=reviews,identity_links=request['identity_links'],reason=request['reason'],state_hash_format=hash_format,topic_identity_links=topic_audit,source_order_review=order_review)
    verify_generation(base,payload)
    old_db,_=materialize(base);new_db,_=materialize(expand_generation(base,payload))
    try:
        old_topics={r[0] for r in old_db.execute('select id from matters')};new_topics={r[0] for r in new_db.execute('select id from matters')}
        if any(link['old_id'] not in old_topics or link['new_id'] not in new_topics for link in request['topic_links']):raise ValidationError('Unknown topic linkage endpoint')
    finally:old_db.close();new_db.close()
    # All replacement originals must already exist in the authoritative archive.
    # An invented self-consistent hash cannot substitute for a stored transcript.
    owner={'role':'owner','id':space['owner_id']}
    with service.archive_projection(owner) as (archive,_):
        for entry in plan:
            if entry['kind']!='source' or entry['source']['source_id'] not in reviews:continue
            s=entry['source']
            row=archive.execute('select 1 from documents where source_id=? and body_hash=? and event_date=? and title=? and body=? limit 1',
                (s['source_id'],s['content_hash'],s['event_date'],s['title'],s['transcript'])).fetchone()
            if not row:raise ValidationError('Replacement is not an archived original')
    if len(json.dumps(payload,ensure_ascii=False,allow_nan=False).encode())>3_700_000:raise ValidationError('Generation review exceeds the bounded payload size')
    return service.store.call('generation_stage',review_id=review_id,expected_revision=expected,label=request['label'],payload=payload,job_id=request['job_id'])


@_generation_operation
def inspect(service,identity,review_id):
    review_id=str(UUID(review_id));space=_scope(service,identity)
    row=service.store.call('generation_review',review_id=review_id)
    if not row or row.get('space_id')!=space['id']:raise ValidationError('Unknown generation review')
    stale=row['expected_revision']!=space['revision'];payload=row['payload']
    if payload.get('review_sha256')!=row['review_sha256']:raise ValidationError('Generation envelope checksum mismatch')
    base=_base(service,{**space,'revision':row['expected_revision']})
    verify_generation(base,payload)
    plan=expand_generation(base,payload)
    old_sources={e['source']['source_id']:e['source'] for e in base if e['kind']=='source'}
    new_sources={e['source']['source_id']:e['source'] for e in plan if e['kind']=='source'}
    with service.archive_projection(identity) as (archive,_):
        def describe(source):
            if source is None:return None
            doc=archive.execute('select id from documents where source_id=? and body_hash=? and event_date=? and title=? order by id limit 1',
                (source['source_id'],source['content_hash'],source['event_date'],source['title'])).fetchone()
            return {'title':source['title'],'event_date':source['event_date'],'archive_id':doc[0] if doc else None}
        sources=[{'source_id':key,'reason':reason,'before':describe(old_sources.get(key)),'after':describe(new_sources.get(key))}
                 for key,reason in payload['source_reviews'].items()]
    old_versions={s['id']:s for s in old_sources.values()};new_versions={s['id']:s for s in new_sources.values()}
    observations=deepcopy(payload['observation_diff'])
    for difference in observations:
        for side,versions in [('before',old_versions),('after',new_versions)]:
            evidence=difference[side]
            if evidence:evidence['source_title']=versions[evidence['source_version']]['title']
    old_db,_=materialize(base);new_db,_=materialize(plan)
    try:
        def title(db,key):
            record=db.execute('select data_json from observations where id=?',(key,)).fetchone()
            return json.loads(record[0])['title'] if record else 'Aussage nicht verfügbar'
        def topic_title(db,key):
            record=db.execute('select title from matters where id=?',(key,)).fetchone()
            return record[0] if record else 'Thema nicht verfügbar'
        topic_identities=[{**link,'before_title':topic_title(old_db,link['old_id']),'after_title':topic_title(new_db,link['new_id'])} for link in payload.get('topic_identity_links',[])]
        identities=[{**link,'before_title':title(old_db,link['old_id']),'after_title':title(new_db,link['new_id'])} for link in payload['identity_links']]
    finally:old_db.close();new_db.close()
    order_review=payload.get('source_order_review')
    order_changes=[]
    if order_review:
        positions={key:i for i,key in enumerate(order_review['after'])}
        for i,key in enumerate(order_review['before']):
            if positions[key]!=i:
                order_changes.append({'source_id':key,'title':new_sources[key]['title'],'event_date':new_sources[key]['event_date'],
                                      'before_position':i+1,'after_position':positions[key]+1})
    return {k:row.get(k) for k in ('id','label','expected_revision','state','created_at','review_sha256','decision_result','decision_reason')}|{
        'current_revision':space['revision'],'stale':stale,'job_id':row.get('job_id'),
        'reason':payload['reason'],'sources':sources,'identity_links':identities,'topic_identity_links':topic_identities,
        'diff':payload['diff'],'observation_diff':observations,'before_counts':payload['before_counts'],
        'after_counts':payload['after_counts'],'personal_decisions_preserved':payload['personal_decisions_preserved'],
        'source_order_changes':order_changes,'source_order_reason':order_review['reason'] if order_review else None}


@_generation_operation
def decide(service,identity,request):
    keys={'review_id','command_id','expected_revision','review_sha256','action','reason'}
    if not isinstance(request,dict) or set(request)!=keys or request['action'] not in ('accept','reject'):
        raise ValidationError('Invalid generation decision')
    if not isinstance(request['reason'],str) or len(request['reason'].strip())>4000:raise ValidationError('Invalid generation review note')
    if type(request['expected_revision']) is not int or request['expected_revision']<0 or not isinstance(request['review_sha256'],str) or not re.fullmatch('[0-9a-f]{64}',request['review_sha256']):raise ValidationError('Invalid generation revision or hash')
    review_id=str(UUID(request['review_id']));command_id=str(UUID(request['command_id']));space=_scope(service,identity)
    row=service.store.call('generation_review',review_id=review_id)
    if not row or row.get('space_id')!=space['id']:raise ValidationError('Unknown generation review')
    # SQL checks exact retry identity even after the accepted revision advanced.
    if row['state']=='pending':
        if request['expected_revision']!=row['expected_revision'] or request['review_sha256']!=row['review_sha256']:raise RevisionConflict('Reviewed generation changed')
        if request['action']=='accept':
            if space['revision']!=row['expected_revision']:raise RevisionConflict('Generation base changed')
            verify_generation(_base(service,space),row['payload'])
    return service.store.call('generation_decide',review_id=review_id,command_id=command_id,expected_revision=request['expected_revision'],
        review_sha256=request['review_sha256'],action=request['action'],reason=request['reason'],actor_id=identity['id'])
