"""Explicit user decisions layered over immutable source observations.

A correction is a dated, attributable event. It never rewrites a quotation or
pretends that the user said something in the original meeting.
"""
from datetime import date
import json
import re
from uuid import UUID

from memory import ValidationError

ACTIONS={'approve','reject','correct','set_status','confirm_knowledge','correct_confirm'}
STATUSES={'open','waiting','done','cancelled'}
FIELDS={'title','claim','owner','due_date','status'}

# Automatic lifecycle events only mutate these effective task fields.  Title
# and claim corrections remain overlaid by ``project`` and therefore do not
# block an otherwise independent status/owner/deadline update.
UPDATE_FIELDS={
    'done': {'status': 'done'},
    'reopened': {'status': 'open'},
    'condition_met': {'status': 'open'},
}


def setup(db):
    db.execute('''CREATE TABLE IF NOT EXISTS human_decisions (
      command_id TEXT PRIMARY KEY, event_date TEXT NOT NULL, actor_id TEXT NOT NULL,
      observation_id TEXT NOT NULL REFERENCES observations(id),
      work_id TEXT, data_json TEXT NOT NULL)''')
    from projection_order import setup as setup_order
    setup_order(db)


def prepare(db, command):
    from planner import ACTIONS as PLANNING_ACTIONS, prepare as prepare_planning
    if isinstance(command,dict) and command.get("action") in PLANNING_ACTIONS:
        return prepare_planning(db,command)
    if not isinstance(command,dict) or set(command)-{'feedback_kind'}!={'action','target_id','reason','patch','event_date'}:
        raise ValidationError('Invalid human decision envelope')
    if 'feedback_kind' in command and command['feedback_kind'] not in ('interpretation','real_world_change'):
        raise ValidationError('Invalid feedback kind')
    if command.get('action')=='set_status' and command.get('feedback_kind')=='interpretation':
        raise ValidationError('A later status update is not interpretation feedback')
    action=command['action'];patch=command['patch']
    if action not in ACTIONS or not isinstance(command['target_id'],str):
        raise ValidationError('Invalid human decision')
    if not isinstance(command['reason'],str) or len(command['reason'].strip())>4000:
        raise ValidationError('Invalid decision note')
    if action not in ('approve','reject','confirm_knowledge') and not command['reason'].strip():
        raise ValidationError('A concrete decision reason is required')
    if not isinstance(patch,dict) or set(patch)-FIELDS:
        raise ValidationError('Only title, claim, owner, due date and status can be corrected')
    if date.fromisoformat(command['event_date']).isoformat()!=command['event_date']:
        raise ValidationError('Invalid decision date')
    row=db.execute('SELECT * FROM observations WHERE id=?',(command['target_id'],)).fetchone()
    if row is None:
        row=db.execute('SELECT o.* FROM work_events e JOIN observations o ON o.id=e.observation_id WHERE e.work_id=? ORDER BY e.rowid LIMIT 1',(command['target_id'],)).fetchone()
    if row is None:raise ValidationError('Unknown decision target')
    if command['event_date']<row['event_date']:
        raise ValidationError('A user decision cannot precede its source')
    observation=json.loads(row['data_json'])
    created=db.execute("SELECT work_id FROM work_events WHERE observation_id=? AND action='created'",(row['id'],)).fetchone()
    work_id=observation.get('update_target') or (created[0] if created else None)
    # A prior explicit approval may have created work without an automatic event.
    if not work_id:
        prior=db.execute('SELECT work_id,data_json FROM human_decisions WHERE observation_id=? ORDER BY rowid',(row['id'],)).fetchall()
        if any(r['work_id'] and json.loads(r['data_json'])['action'] in ('approve','correct_confirm') for r in prior):work_id=row['id']
    is_work=observation['kind']=='commitment' or bool(observation.get('update_target'))
    if action=='correct_confirm':
        if not patch:raise ValidationError('Empty correction')
        if command.get('feedback_kind','interpretation')!='interpretation':
            raise ValidationError('Correct and confirm is interpretation feedback')
        if not is_work and set(patch)-{'title','claim'}:
            raise ValidationError('Knowledge correction only changes title and claim')
        if is_work and any(json.loads(r[0])['action'] in ('approve','correct_confirm') for r in db.execute('SELECT data_json FROM human_decisions WHERE observation_id=?',(row['id'],))):
            raise ValidationError('Already reviewed; edit the accepted task instead')
    if 'claim' in patch and action not in ('correct','correct_confirm'):
        raise ValidationError('Text changes require an explicit correction')
    if action=='confirm_knowledge':
        if observation['kind']=='commitment' or observation.get('update_target') or patch:
            raise ValidationError('Knowledge confirmation cannot create or modify work')
    if action=='approve' or (action=='correct_confirm' and is_work):
        if observation['kind']!='commitment' and not observation.get('update_target'):
            raise ValidationError('Only an actual action proposal can be approved')
        if created:
            raise ValidationError('This commitment is already accepted; use a correction')
        # An update keeps the accepted task's owner unless it explicitly changes
        # that field. Requiring a new owner here would turn a status approval into
        # an unintended reassignment.
        if not observation.get('update_target') or observation.get('update')=='owner_changed' or 'owner' in patch:
            owner=patch.get('owner',observation.get('owner'))
            if not isinstance(owner,str) or not owner.strip() or re.fullmatch(r'(?:Speaker|Sprecher|Unknown Speaker|Unknown|Unbekannt)\s*\d*',owner,re.I):
                raise ValidationError('Approval needs an identified person')
        work_id=work_id or row['id']
    if action in ('correct','set_status') and not work_id:
        raise ValidationError('Correction requires existing work')
    if action=='correct' and not patch:raise ValidationError('Empty correction')
    if action=='set_status' and set(patch)!={'status'}:raise ValidationError('Status action requires exactly one status')
    if action=='reject' and patch:raise ValidationError('Rejection cannot also modify work')
    if 'claim' in patch and (not isinstance(patch['claim'],str) or not 1<=len(patch['claim'].strip())<=12000):
        raise ValidationError('Invalid corrected claim')
    for field in ('title','owner'):
        if field in patch and (not isinstance(patch[field],str) or not 1<=len(patch[field].strip())<=1000):
            raise ValidationError('Invalid corrected '+field)
    if 'due_date' in patch and patch['due_date'] is not None:
        if not isinstance(patch['due_date'],str) or date.fromisoformat(patch['due_date']).isoformat()!=patch['due_date']:
            raise ValidationError('A user-set due date must be ISO formatted')
    if 'status' in patch and patch['status'] not in STATUSES:
        raise ValidationError('Invalid corrected status')
    # Rejecting a suggested update leaves the existing task intact.
    reject_work=bool(work_id) and not observation.get('update_target')
    return {**command,'observation_id':row['id'],'work_id':work_id,'reject_work':reject_work}


def record(db, *, command_id, actor_id, command):
    from planner import ACTIONS as PLANNING_ACTIONS, record as record_planning
    if isinstance(command,dict) and command.get("action") in PLANNING_ACTIONS:
        return record_planning(db,command_id=command_id,actor_id=actor_id,command=command)
    command_id=str(UUID(command_id));actor_id=str(UUID(actor_id))
    existing=db.execute('SELECT data_json,actor_id FROM human_decisions WHERE command_id=?',(command_id,)).fetchone()
    if existing:
        saved=json.loads(existing['data_json'])
        if existing['actor_id']!=actor_id or any(saved.get(k)!=v for k,v in command.items()):
            raise ValidationError('Decision identity reused with different content')
        return saved
    normalized=prepare(db,command)
    db.execute('INSERT INTO human_decisions VALUES (?,?,?,?,?,?)',(command_id,command['event_date'],actor_id,
                normalized['observation_id'],normalized['work_id'],json.dumps(normalized,ensure_ascii=False)))
    from projection_order import record as record_order
    record_order(db,'human',command_id)
    return normalized


def guard_updates(db, proposal, *, mode='field-v1'):
    if mode not in ('legacy','field-v1'):raise ValidationError('Unknown human update guard')
    if mode=='legacy':
        touched={r[0] for r in db.execute('SELECT work_id FROM human_decisions WHERE work_id IS NOT NULL')}
        result={**proposal,'observations':[]}
        for original in proposal['observations']:
            o=dict(original)
            if o.get('update_target') in touched and o.get('update')!='none':
                o['required_review']=True
                o['action_uncertainty']='Für diese Aufgabe liegt eine persönliche Entscheidung vor; die vorgeschlagene automatische Änderung benötigt eine Bestätigung.'
                o['resolution_basis']='human_decision_protected'
            result['observations'].append(o)
        return result
    def mutations(observation):
        update=observation.get('update')
        result=dict(UPDATE_FIELDS.get(update,{}))
        if update=='progress' and observation.get('work_state') in ('open','waiting'):
            result['status']=observation['work_state']
        elif update=='reopened' and observation.get('work_state')=='waiting':
            result['status']='waiting'
        elif update=='owner_changed':
            result['owner']=observation.get('owner')
        elif update=='date_changed':
            result['due_date']=observation.get('due_text')
        return result

    def equivalent(left, right):
        if isinstance(left,str) and isinstance(right,str):
            return ' '.join(left.split()).casefold()==' '.join(right.split()).casefold()
        return left==right

    from projection_order import sequence
    protected={};rejected={};timeline=[]
    for row in db.execute('SELECT command_id,work_id,data_json FROM human_decisions WHERE work_id IS NOT NULL ORDER BY rowid'):
        timeline.append((sequence(db,'human',row['command_id']),'human',row))
    # Manually created tasks may participate in meeting matching. Their explicit
    # assignee/deadline and later manual corrections keep the same field-level
    # protection as corrections to meeting-derived work. The initial open status
    # is lifecycle state, so later evidenced completion is allowed.
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning_events'").fetchone():
        for row in db.execute('SELECT command_id,target_id,data_json FROM planning_events ORDER BY rowid'):
            timeline.append((sequence(db,'planning',row['command_id']),'planning',row))
    for _,kind,row in sorted(timeline,key=lambda item:item[0]):
        if kind=='human':
            decision=json.loads(row['data_json']);work_id=row['work_id'];action=decision.get('action')
            observation_row=db.execute('SELECT data_json FROM observations WHERE id=?',(decision.get('observation_id'),)).fetchone()
            automatic=mutations(json.loads(observation_row[0])) if observation_row else {}
            if action=='reject':
                for field,value in automatic.items():rejected.setdefault(work_id,{})[field]=value
            elif action in ('approve','correct_confirm'):
                # An explicit later approval supersedes older planning or
                # correction values for the fields it actually accepts.
                for field,value in automatic.items():
                    protected.setdefault(work_id,{})[field]=value
                    rejected.get(work_id,{}).pop(field,None)
            if action!='reject':
                for field,value in decision.get('patch',{}).items():
                    protected.setdefault(work_id,{})[field]=value
                    rejected.get(work_id,{}).pop(field,None)
        else:
            event=json.loads(row['data_json']);action=event.get('action');work_id=row['target_id']
            if action not in ('create_task','update_task'):continue
            for field,value in event.get('patch',{}).items():
                if field in ('owner','due_date') or (action=='update_task' and field=='status'):
                    protected.setdefault(work_id,{})[field]=value
                    rejected.get(work_id,{}).pop(field,None)

    result={**proposal,'observations':[]}
    for original in proposal['observations']:
        o=dict(original)
        changed=mutations(o)
        target=o.get('update_target');conflicts=sorted(field for field,value in changed.items()
            if (field in protected.get(target,{}) and not equivalent(value,protected[target][field]))
            or (field in rejected.get(target,{}) and equivalent(value,rejected[target][field])))
        if conflicts:
            o['required_review']=True
            o['action_uncertainty']='Die vorgeschlagene automatische Änderung widerspricht einer persönlichen Korrektur der Felder: '+', '.join(conflicts)+'.'
            o['resolution_basis']='human_decision_protected'
            o['human_conflict_fields']=conflicts
        result['observations'].append(o)
    return result


def project(db, state, as_of):
    groups=('personal','waiting_dependencies','waiting','completed')
    work={item['id']:dict(item) for group in groups for item in state[group]}
    decisions={};history=[]
    for row in db.execute('SELECT * FROM human_decisions WHERE event_date<=? ORDER BY rowid',(as_of,)):
        d=json.loads(row['data_json']);wid=d['work_id'];oid=d['observation_id']
        observation_row=db.execute('SELECT o.data_json,o.event_date,o.source_version,s.title AS source_title,s.content_hash FROM observations o JOIN source_versions s ON s.id=o.source_version WHERE o.id=?',(oid,)).fetchone()
        o=json.loads(observation_row['data_json'])
        audit={'command_id':row['command_id'],'actor_id':row['actor_id'],'event_date':row['event_date'],
               'action':d['action'],'reason':d['reason'],'patch':d['patch'],'observation_id':oid,'work_id':wid}
        decisions[oid]=audit;history.append(audit)
        if d['action']=='approve' or (d['action']=='correct_confirm' and wid):
            if wid not in work:
                work[wid]={**o,'id':wid,'status':o['work_state'] if o.get('work_state') in ('waiting','done') else 'open',
                           'history':[{'action':'proposed','event_date':observation_row['event_date'],
                                       'source_version':observation_row['source_version'],'source_title':observation_row['source_title'],
                                       'content_hash':observation_row['content_hash'],'quotes':o['quotes'],'claim':o['claim'],
                                       'owner':o.get('owner'),'due_text':o.get('due_text')}],
                           'due_reference_date':observation_row['event_date'] if o.get('due_text') else None}
            elif o.get('update_target'):
                change=o.get('update')
                if change=='done':work[wid]['status']='done'
                elif change=='reopened':work[wid]['status']='open'
                elif change=='owner_changed':work[wid]['owner']=o['owner']
                elif change=='date_changed':
                    work[wid]['due_text']=o.get('due_text');work[wid]['due_reference_date']=observation_row['event_date']
                elif change=='progress' and work[wid]['status'] not in ('done','cancelled') and o.get('work_state') in ('open','waiting'):
                    work[wid]['status']=o['work_state']
                elif change=='condition_met' and work[wid]['status'] in ('open','waiting'):
                    work[wid]['condition_text']=None
                    work[wid]['status']='open'
            work[wid]['required_review']=False;work[wid]['action_uncertainty']=None
        if d['action']=='reject' and d['reject_work'] and wid in work:
            work[wid]['status']='dismissed'
        if d['action']!='reject' and wid in work:
            item=work[wid]
            for field,value in d['patch'].items():
                if field=='due_date':
                    item['due_text']=value;item['due_reference_date']=None
                    item['due_date']=value
                else:item[field]=value
            item['last_changed']=row['event_date']
            item['human_decision']=audit
            item['history']=[*item.get('history',[]),{**audit,'human':True,'quotes':[],'claim':d['reason']}]
    def personal(item):
        return re.sub(r'[^a-z]+',' ',(item.get('owner') or '').lower()).strip() in ('gleb','gleb komzin','komzin gleb')
    knowledge=project_knowledge(db,state['knowledge'],as_of)
    return {**state,'knowledge':knowledge,'human_decisions':history,
        'personal':[w for w in work.values() if personal(w) and w['status']=='open'],
        'waiting_dependencies':[w for w in work.values() if personal(w) and w['status']=='waiting'],
        'waiting':[w for w in work.values() if not personal(w) and w['status'] in ('open','waiting')],
        'completed':[w for w in work.values() if w['status']=='done'],
        'cancelled':[w for w in work.values() if w['status'] in ('cancelled','dismissed')]}


def project_knowledge(db, entries, as_of, *, active_only=False):
    """Effective user wording; immutable extraction and quotations stay intact.

    This is deliberately separate from memory.context, whose raw data also
    participates in verification of already-published source batches.
    """
    events={}
    for row in db.execute('SELECT * FROM human_decisions WHERE event_date<=? ORDER BY rowid',(as_of,)):
        d=json.loads(row['data_json'])
        events.setdefault(d['observation_id'],[]).append({
            'command_id':row['command_id'],'actor_id':row['actor_id'],'event_date':row['event_date'],
            'action':d['action'],'reason':d['reason'],'patch':d['patch'],
            'observation_id':d['observation_id'],'work_id':d['work_id']})
    result=[]
    for entry in entries:
        data=dict(entry['data']); original=dict(data); corrections=[];decision_history=[];active=True
        for audit in events.get(entry['id'],[]):
            if audit['action']=='correct_confirm' or (audit['action']=='correct' and 'claim' in audit['patch']):
                for key,value in audit['patch'].items():
                    if key in ('title','claim','owner'):data[key]=value
                    elif key=='due_date':data['due_text']=value
                corrections.append(audit)
            if audit['action']=='reject':active=False
            elif audit['action'] in ('approve','confirm_knowledge','correct_confirm'):active=True
            decision_history.append(audit)
            data['human_decision']=audit;data['required_review']=False
        if decision_history:
            data['human_decision_history']=decision_history
            data['knowledge_status']='active' if active else 'rejected'
        if corrections:
            data['original_interpretation']={k:original.get(k) for k in ('title','claim','owner','due_text')}
            data['correction_history']=corrections
        if active_only and not active:continue
        result.append({**entry,'data':data})
    return result
