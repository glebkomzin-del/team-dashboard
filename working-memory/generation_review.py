"""Compile an explicit replacement generation entirely from saved evidence.

This module has no network/model interface. It does not publish, choose semantic
identities, discard user decisions, or invent a plan. The caller supplies the full
proposed sequence, a reason for each changed source, and explicit identity links.
"""
from copy import deepcopy
import json
from uuid import UUID

from memory import connect,overview,ValidationError
from journal_projection import apply_saved,prepare_source,digest,verify_source
from human_decisions import record

FORMAT='wm-generation-review-v1'
SOURCE_FIELDS=('id','source_id','content_hash','event_date','title','transcript','observed_at')
GROUPS=('personal','waiting_dependencies','waiting','completed','cancelled')


def _reason(value):
    if not isinstance(value,str) or not 1<=len(value.strip())<=4000:
        raise ValidationError('A concrete generation review reason is required')


def _entry(entry):
    if not isinstance(entry,dict) or entry.get('kind') not in ('source','redacted_source','human'):
        raise ValidationError('Generation contains an unknown entry kind')
    if entry['kind']=='source':
        if set(entry)!={'kind','source','payload'}:raise ValidationError('Invalid generation source entry')
        verify_source(entry['source'])
    elif entry['kind']=='redacted_source':
        if set(entry)!={'kind','package'}:raise ValidationError('Invalid redacted generation source entry')
        from original_deletion import verify_redacted_entry
        verify_redacted_entry(entry['package'])
    else:
        if set(entry)!={'kind','command_id','actor_id','payload'}:raise ValidationError('Invalid generation human entry')
        UUID(entry['command_id']);UUID(entry['actor_id'])
    return entry


def _changes(old,new,path=()):
    if old==new:return []
    if isinstance(old,dict) and isinstance(new,dict):
        result=[]
        for key in sorted(old.keys()|new.keys()):
            if key not in new:result.append({'path':[*path,key],'remove':True})
            elif key not in old:result.append({'path':[*path,key],'value':deepcopy(new[key])})
            else:result.extend(_changes(old[key],new[key],(*path,key)))
        return result
    if isinstance(old,list) and isinstance(new,list) and len(old)==len(new):
        return [change for i,(a,b) in enumerate(zip(old,new)) for change in _changes(a,b,(*path,i))]
    return [{'path':list(path),'value':deepcopy(new)}]


def pack_entries(base,entries):
    def key(entry):
        if entry['kind']=='source':return ('source',entry['source']['source_id'])
        if entry['kind']=='redacted_source':return ('source',entry['package']['source']['source_id'])
        return ('human',entry['command_id'])
    prior={key(entry):entry for entry in base};packed=[]
    for entry in entries:
        old=prior.get(key(entry))
        if old is None:packed.append({'new':deepcopy(entry)})
        else:packed.append({'ref':digest(old),'changes':_changes(old,entry)})
    return packed


def expand_generation(base,payload):
    prior={digest(entry):entry for entry in base};entries=[]
    for item in payload['entries']:
        if not isinstance(item,dict):raise ValidationError('Invalid compact generation entry')
        if set(item)=={'new'}:entry=deepcopy(item['new'])
        elif set(item)=={'ref','changes'} and item['ref'] in prior and isinstance(item['changes'],list):
            entry=deepcopy(prior[item['ref']])
            for change in item['changes']:
                if not isinstance(change,dict) or set(change) not in ({'path','value'},{'path','remove'}):raise ValidationError('Invalid generation field change')
                path=change['path']
                if not isinstance(path,list) or len(path)>32 or any(type(k) not in (int,str) for k in path):raise ValidationError('Invalid generation field path')
                if not path:
                    if 'value' not in change:raise ValidationError('Cannot remove a whole referenced entry')
                    entry=deepcopy(change['value']);continue
                parent=entry
                try:
                    for key in path[:-1]:parent=parent[key]
                    key=path[-1]
                    if isinstance(parent,list):
                        if type(key) is not int or not 0<=key<len(parent) or 'remove' in change:raise ValidationError('Invalid array change')
                    elif not isinstance(parent,dict) or not isinstance(key,str):raise ValidationError('Invalid object change')
                    if 'remove' in change:
                        if change['remove'] is not True:raise ValidationError('Invalid removal flag')
                        del parent[key]
                    else:parent[key]=deepcopy(change['value'])
                except (KeyError,IndexError,TypeError):raise ValidationError('Generation field path does not match its base') from None
        else:raise ValidationError('Unknown generation entry reference')
        entries.append(_entry(entry))
    return entries


def logical_entries(entries):
    """Remove transport metadata, retaining the last accepted generation if any."""
    logical=[]
    for entry in entries:
        if entry['kind']=='generation':
            payload=entry['payload']
            verify_generation(logical,payload)
            logical=expand_generation(logical,payload)
        elif entry['kind']=='redaction':
            from projection_snapshot import verify_snapshot
            payload=verify_snapshot(entry['payload'])
            logical=deepcopy(payload['logical_basis'])
        elif entry['kind']=='source':
            source=entry.get('source')
            if not source or source['id']!=entry.get('source_version',source['id']):
                raise ValidationError('Generation needs every pinned source, not a floating reference')
            logical.append(_entry({'kind':'source','source':{key:source[key] for key in SOURCE_FIELDS},'payload':entry['payload']}))
        elif entry['kind']=='human':
            logical.append(_entry({key:entry[key] for key in ('kind','command_id','actor_id','payload')}))
        else:raise ValidationError('Generation contains an unknown journal entry')
    return logical


def materialize(entries, *, prepare=False, human_guard='field-v1', prepare_sources=None):
    if prepare_sources is not None and not prepare:
        raise ValidationError('Selective source preparation requires prepare mode')
    if prepare_sources is not None:
        prepare_sources=set(prepare_sources)
    db=connect(':memory:');normalized=[];sources=set();humans=set();last_date=None
    try:
        for raw in entries:
            entry=deepcopy(_entry(raw))
            if entry['kind']=='source':
                source=entry['source'];payload=entry['payload']
                if source['source_id'] in sources:raise ValidationError('Generation repeats a source identity')
                if last_date is not None and source['event_date']<last_date:raise ValidationError('Generation source order is not chronological')
                sources.add(source['source_id']);last_date=source['event_date']
                should_prepare=prepare and (prepare_sources is None or source['source_id'] in prepare_sources)
                if should_prepare:
                    entry['payload']=prepare_source(db,source,payload['proposal'],pipeline=payload['pipeline'],model=payload['model'],
                        provenance=payload['provenance'],usage=payload.get('usage'),matter_links=payload.get('matter_links'),
                        human_guard=human_guard)
                    if 'archive_note' in payload:entry['payload']['archive_note']=deepcopy(payload['archive_note'])
                elif not payload.get('result_sha256'):raise ValidationError('Generation lacks an accepted result checksum')
                apply_saved(db,source,entry['payload'])
            elif entry['kind']=='redacted_source':
                from journal_projection import apply_redacted_saved
                apply_redacted_saved(db,entry['package'])
            else:
                if entry['command_id'] in humans:raise ValidationError('Generation repeats a personal decision')
                humans.add(entry['command_id'])
                record(db,command_id=entry['command_id'],actor_id=entry['actor_id'],command=entry['payload'])
            normalized.append(entry)
        return db,normalized
    except Exception:
        db.close();raise


def _observations(db):
    import json
    return {row['id']:{'source_version':row['source_version'],'matter_id':row['matter_id'],'event_date':row['event_date'],
            'data':json.loads(row['data_json'])} for row in db.execute('SELECT * FROM observations')}


def _diff(before,after):
    old={item['id']:{'group':group,**item} for group in GROUPS for item in before.get(group,[])}
    new={item['id']:{'group':group,**item} for group in GROUPS for item in after.get(group,[])}
    fields=('title','owner','status','group','due_text','due_date','condition_text','claim','required_review','action_uncertainty')
    def compact(item):return {key:item.get(key) for key in fields}
    rows=[]
    for key in sorted(old.keys()|new.keys()):
        previous=compact(old[key]) if key in old else None;following=compact(new[key]) if key in new else None
        if previous!=following:rows.append({'id':key,'before':previous,'after':following})
    return rows


def _state_digest(state,format):
    if format is None:return digest(state)
    if format!='canonical-knowledge-v1':raise ValidationError('Unknown generation state hash format')
    # context() retains the original SQLite JSON string alongside parsed data.
    # PostgreSQL JSONB and compact patches may reorder object keys. Hash their
    # content, not incidental serialization order, without rewriting evidence.
    value=deepcopy(state)
    for row in value['knowledge']:
        if 'data_json' in row:row['data_json']=json.loads(row['data_json'])
    return digest(value)


def compile_generation(base,plan,*,source_reviews,identity_links,reason,state_hash_format='canonical-knowledge-v1',topic_identity_links=None,source_order_review=None,projection_rules='field-v1'):
    """Validate a fully explicit plan and produce an immutable review package.

    Each source addition/removal/change needs a reason keyed by source_id. Every
    affected existing personal decision must keep its command/actor/date/patch;
    a changed target needs an explicit one-to-one old/new observation link.
    """
    _reason(reason)
    if projection_rules not in ('legacy','field-v1'):raise ValidationError('Unknown generation projection rules')
    if not isinstance(source_reviews,dict) or not isinstance(identity_links,list):raise ValidationError('Invalid generation review input')
    for value in source_reviews.values():_reason(value)
    before_db,old_entries=materialize(base)
    after_db=None
    try:
        def source_id(entry):
            return entry['source']['source_id'] if entry['kind']=='source' else entry['package']['source']['source_id']
        old_sources={source_id(e):e for e in old_entries if e['kind'] in ('source','redacted_source')}
        plan_sources={}
        for entry in plan:
            _entry(entry)
            if entry['kind'] in ('source','redacted_source'):
                key=source_id(entry)
                if key in plan_sources:raise ValidationError('Duplicate planned source')
                plan_sources[key]=entry
        def comparable(entry):
            entry=deepcopy(entry)
            if entry['kind']=='source':entry['payload'].pop('result_sha256',None)
            return entry
        changed={key for key in old_sources.keys()|plan_sources.keys() if key not in old_sources or key not in plan_sources or comparable(old_sources[key])!=comparable(plan_sources[key])}
        if any(old_sources.get(key,{}).get('kind')=='redacted_source' for key in changed):
            raise ValidationError('A deleted original cannot be rewritten by source generation')
        if changed!=set(source_reviews):raise ValidationError('Each changed source needs exactly one explicit review; unchanged sources cannot hide edits')
        if not changed and source_order_review is None:raise ValidationError('Generation has no reviewed source change')
        old_humans={e['command_id']:e for e in old_entries if e['kind']=='human'}
        new_humans={e['command_id']:e for e in plan if e['kind']=='human'}
        if set(old_humans)!=set(new_humans):raise ValidationError('A generation must preserve every personal decision; new decisions use the normal owner flow')
        links={};destinations=set()
        for link in identity_links:
            if not isinstance(link,dict) or set(link)!={'old_id','new_id','reason'}:raise ValidationError('Invalid explicit identity link')
            _reason(link['reason'])
            if link['old_id'] in links or link['new_id'] in destinations:raise ValidationError('Identity links must be one-to-one')
            links[link['old_id']]=link['new_id'];destinations.add(link['new_id'])
        old_obs=_observations(before_db)
        for command_id,old in old_humans.items():
            new=new_humans[command_id]
            old_target=old['payload']['target_id']
            wanted=deepcopy(old);wanted['payload']['target_id']=links.get(old_target,old_target)
            if new!=wanted:raise ValidationError('Personal decision content cannot be rewritten in a generation')
        # Keep relative human-decision order, not only their set. Otherwise two
        # competing owner corrections could silently reverse precedence.
        if [e['command_id'] for e in plan if e['kind']=='human']!=list(old_humans):raise ValidationError('Personal decision order changed')
        # Existing decisions stay between the same retained original entries.
        # Moving one after a later update could bypass its protection even if
        # every command field and the final human list appeared unchanged.
        retained=set(old_sources)&set(plan_sources)
        def anchors(entries):
            return [('source',source_id(e)) if e['kind'] in ('source','redacted_source') else ('human',e['command_id'])
                    for e in entries if e['kind']=='human' or source_id(e) in retained]
        if source_order_review is None:
            if anchors(old_entries)!=anchors(plan):
                raise ValidationError('Existing source and personal-decision order must remain anchored')
        else:
            if not isinstance(source_order_review,dict) or set(source_order_review)!={'before','after','reason'}:
                raise ValidationError('Invalid explicit source-order review')
            _reason(source_order_review['reason'])
            before_order=[source_id(e) for e in old_entries if e['kind'] in ('source','redacted_source') and source_id(e) in retained]
            after_order=[source_id(e) for e in plan if e['kind'] in ('source','redacted_source') and source_id(e) in retained]
            if source_order_review['before']!=before_order or source_order_review['after']!=after_order or before_order==after_order:
                raise ValidationError('Source-order review must exactly describe a changed retained sequence')
            # Only explicitly reviewed ties may be reordered. Correcting a date
            # across existing days is a different operation, still unsupported.
            positions={key:i for i,key in enumerate(after_order)}
            for i,left in enumerate(before_order):
                for right in before_order[i+1:]:
                    if positions[left]>positions[right]:
                        def event_date(entry):return entry['source']['event_date'] if entry['kind']=='source' else entry['package']['source']['event_date']
                        dates={event_date(old_sources[k]) for k in (left,right)}|{event_date(plan_sources[k]) for k in (left,right)}
                        if len(dates)!=1:raise ValidationError('Source-order review can only correct same-day ordering')
            # No retained source may cross a personal decision. Same-day source
            # order may change within the interval on either side of a decision.
            def decision_sides(entries):
                seen=set();result={}
                for e in entries:
                    if e['kind'] in ('source','redacted_source') and source_id(e) in retained:seen.add(source_id(e))
                    elif e['kind']=='human':result[e['command_id']]=frozenset(seen)
                return result
            if decision_sides(old_entries)!=decision_sides(plan):
                raise ValidationError('Personal decisions must remain anchored to the same retained sources')
        # Recompute only the explicitly reviewed source changes. Re-preparing
        # every retained source would silently upgrade legacy guard semantics
        # and make the generation fail its own immutable replay check.
        after_db,prepared=materialize(plan,prepare=True,human_guard=projection_rules,prepare_sources=changed)
        new_obs=_observations(after_db)
        if topic_identity_links is not None:
            if not isinstance(topic_identity_links,list):raise ValidationError('Invalid topic identity links')
            old_topics={r[0] for r in before_db.execute('select id from matters')}
            new_topics={r[0] for r in after_db.execute('select id from matters')}
            seen_topics=set();topic_destinations=set()
            for link in topic_identity_links:
                if not isinstance(link,dict) or set(link)!={'old_id','new_id','reason'}:raise ValidationError('Invalid topic identity link')
                _reason(link['reason'])
                if link['old_id'] in seen_topics or link['new_id'] in topic_destinations:raise ValidationError('Topic identity links must be one-to-one')
                if link['old_id'] not in old_topics or link['new_id'] not in new_topics:raise ValidationError('Unknown topic linkage endpoint')
                seen_topics.add(link['old_id']);topic_destinations.add(link['new_id'])
        for old_id,new_id in links.items():
            if old_id not in old_obs or new_id not in new_obs:raise ValidationError('Identity link endpoint is not an observation')
        for old in old_humans.values():
            from planner import ACTIONS as PLANNING_ACTIONS
            if old['payload']['action'] in PLANNING_ACTIONS:
                target=old['payload']['target_id']
                # Manual tasks/team are independent; source-linked planning must
                # not silently attach to a changed interpretation at the same ID.
                if old['payload']['action']=='plan_task' and target in old_obs and old_obs[target]!=new_obs.get(target) and target not in links:
                    raise ValidationError('Changed planned evidence requires an explicit identity link')
                continue
            target=old['payload']['target_id']
            if target not in old_obs:raise ValidationError('Personal decision has an unsupported indirect target')
            if old_obs[target]!=new_obs.get(target) and target not in links:
                raise ValidationError('Changed personally reviewed evidence requires an explicit identity link, including same-ID changes')
        referenced={o['data']['update_target'] for o in old_obs.values() if o['data'].get('update_target')}
        for target in referenced:
            if old_obs.get(target)!=new_obs.get(target) and target not in links:
                raise ValidationError('Changed evidence with dependent updates requires an explicit identity link')
        before=overview(before_db);after=overview(after_db)
        def evidence(row):
            if row is None:return None
            fields=('kind','title','claim','owner','due_text','condition_text','quotes','update','update_target','required_review','action_uncertainty')
            return {**{k:row[k] for k in ('source_version','matter_id','event_date')},
                    **{k:row['data'].get(k) for k in fields}}
        observation_diff=[{'id':key,'before':evidence(old_obs.get(key)),'after':evidence(new_obs.get(key))}
                          for key in sorted(old_obs.keys()|new_obs.keys()) if old_obs.get(key)!=new_obs.get(key)]
        result={'format':FORMAT,'base_sha256':digest(old_entries),'reason':reason,
                'source_reviews':deepcopy(source_reviews),'identity_links':deepcopy(identity_links),'entries':pack_entries(old_entries,prepared),
                'new_sources':[e['source'] for e in prepared if e['kind']=='source' and e['source']['id'] not in {
                    old['source']['id'] if old['kind']=='source' else old['package']['source']['id'] for old in old_sources.values()}],
                'diff':_diff(before,after),'observation_diff':observation_diff,'before_counts':{g:len(before.get(g,[])) for g in GROUPS},
                'after_counts':{g:len(after.get(g,[])) for g in GROUPS},
                'observation_counts':{'before':len(old_obs),'after':len(new_obs)},
                'personal_decisions_preserved':len(old_humans),'state_sha256':_state_digest(after,state_hash_format)}
        if topic_identity_links is not None:result['topic_identity_links']=deepcopy(topic_identity_links)
        if source_order_review is not None:result['source_order_review']=deepcopy(source_order_review)
        if state_hash_format is not None:result['state_hash_format']=state_hash_format
        if projection_rules!='legacy':result['projection_rules']=projection_rules
        result['review_sha256']=digest(result)
        return result
    finally:
        before_db.close()
        if after_db:after_db.close()


def verify_generation(base,payload):
    if not isinstance(payload,dict) or payload.get('format')!=FORMAT:raise ValidationError('Unknown generation format')
    unsigned={k:v for k,v in payload.items() if k!='review_sha256'}
    if digest(unsigned)!=payload.get('review_sha256'):raise ValidationError('Generation review checksum mismatch')
    if digest(base)!=payload.get('base_sha256'):raise ValidationError('Generation base has changed')
    checked=compile_generation(base,expand_generation(base,payload),source_reviews=payload['source_reviews'],identity_links=payload['identity_links'],reason=payload['reason'],state_hash_format=payload.get('state_hash_format'),topic_identity_links=payload.get('topic_identity_links'),source_order_review=payload.get('source_order_review'),projection_rules=payload.get('projection_rules','legacy'))
    if checked!=payload:raise ValidationError('Generation no longer reproduces the reviewed result')
    return True
