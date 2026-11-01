"""Explicit personal planning, separate from the immutable meeting interpretation.

Commands use the existing owner-only, revision-checked human journal. Planning
does not become a statement in a transcript or enter the model's work context.
"""
from datetime import date
import json
import re
from uuid import UUID

from memory import ValidationError, overview

ACTIONS = {'create_task', 'update_task', 'plan_task', 'configure_team',
           'create_memory', 'update_memory', 'delete_memory'}
PLAN_FIELDS = {'scheduled_date', 'priority', 'estimate_minutes', 'note'}
TASK_FIELDS = PLAN_FIELDS | {'title', 'owner', 'due_date', 'status'}
DEFAULT_TEAM = [
    {'id': 'jan-gieselberg', 'name': 'Jan Gieselberg', 'active': True,
     'aliases': ['Gieselberg, Jan Philipp', 'Jan Philipp Gieselberg']},
    {'id': 'nikolaos-ginnas', 'name': 'Giannas, Nikolaos', 'active': True,
     'aliases': ['Nikolaos Ginnas', 'Nikolaos Giannas', 'Nikolaus Ginas', 'Ginas, Nikolaus']},
    {'id': 'kimia-safei', 'name': 'Kimia Safei', 'active': True, 'aliases': []},
    {'id': 'mathias-hummel', 'name': 'Mathias Hummel', 'active': False,
     'aliases': ['Hummel, Mathias']},
]


def setup(db):
    db.execute('''CREATE TABLE IF NOT EXISTS planning_events (
        command_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, event_date TEXT NOT NULL,
        target_id TEXT NOT NULL, data_json TEXT NOT NULL)''')
    from projection_order import setup as setup_order
    setup_order(db)


def events(db, as_of='9999-12-31'):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='planning_events'").fetchone():
        return []
    return [{**json.loads(r['data_json']), 'command_id': r['command_id'], 'actor_id': r['actor_id']}
            for r in db.execute('SELECT * FROM planning_events WHERE event_date<=? ORDER BY rowid', (as_of,))]


def personal(owner):
    return re.sub(r'[^a-z]+', ' ', (owner or '').lower()).strip() in ('gleb', 'gleb komzin', 'komzin gleb')


def state(db, as_of='9999-12-31'):
    tasks, plans, memories = {}, {}, {}
    team = json.loads(json.dumps(DEFAULT_TEAM))
    for event in events(db, as_of):
        target, action, patch = event['target_id'], event['action'], event['patch']
        if action == 'configure_team':
            team = patch['members']
            continue
        if action == 'create_memory':
            memories[target] = {'id': target, 'title': patch['title'], 'claim': patch['claim'],
                'deleted': False, 'history': [], 'origin': 'manual', 'created_date': event['event_date']}
        if action in ('create_memory', 'update_memory', 'delete_memory'):
            memory = memories[target]
            if action == 'update_memory':memory.update(patch)
            elif action == 'delete_memory':memory['deleted'] = True
            memory['history'].append(event);memory['last_changed'] = event['event_date']
            memory['provenance'] = {'kind': 'explicit_user_memory', 'command_id': event['command_id'],
                'actor_id': event['actor_id'], 'event_date': event['event_date']}
            continue
        if action == 'create_task':
            tasks[target] = {'id': target, 'title': '', 'owner': 'Komzin, Gleb', 'status': 'open',
                'due_date': None, 'scheduled_date': None, 'priority': 'normal', 'estimate_minutes': None,
                'note': '', 'history': [], 'created_date': event['event_date'], 'origin': 'manual'}
        item = tasks[target] if target in tasks else plans.setdefault(target, {'history': []})
        item.update(patch)
        item['history'].append(event)
        item['last_changed'] = event['event_date']
    return {'tasks': tasks, 'plans': plans, 'memories': memories, 'team': team}


def valid_date(value):
    return isinstance(value, str) and date.fromisoformat(value).isoformat() == value


def prepare(db, command):
    if not isinstance(command, dict) or set(command) != {'action', 'target_id', 'reason', 'patch', 'event_date'}:
        raise ValidationError('Invalid planning envelope')
    action, target, patch = command['action'], command['target_id'], command['patch']
    if action not in ACTIONS or not isinstance(target, str) or not target or not isinstance(patch, dict):
        raise ValidationError('Invalid planning command')
    if not isinstance(command['reason'], str) or not 1 <= len(command['reason'].strip()) <= 4000:
        raise ValidationError('A concrete planning description is required')
    if not valid_date(command['event_date']):
        raise ValidationError('Invalid planning date')
    current = state(db)
    if events(db) and command['event_date'] < events(db)[-1]['event_date']:
        raise ValidationError('Planning events cannot be backdated')
    if action == 'configure_team':
        if target != 'team' or set(patch) != {'members'} or not isinstance(patch['members'], list) or len(patch['members']) > 100:
            raise ValidationError('Invalid team configuration')
        ids, names = set(), set()
        for m in patch['members']:
            if not isinstance(m, dict) or set(m) != {'id', 'name', 'active', 'aliases'}:
                raise ValidationError('Invalid team member')
            if not isinstance(m['id'], str) or not re.fullmatch(r'[a-z0-9-]{1,80}', m['id']) or m['id'] in ids:
                raise ValidationError('Duplicate or invalid member identity')
            if type(m['active']) is not bool or not isinstance(m['aliases'], list) or len(m['aliases']) > 20:
                raise ValidationError('Invalid member attributes')
            for name in [m['name'], *m['aliases']]:
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 200 or name.casefold().strip() in names:
                    raise ValidationError('Person names must be nonempty and unambiguous')
                names.add(name.casefold().strip())
            ids.add(m['id'])
        return command
    if action == 'create_memory':
        if str(UUID(target)) != target or target in current['memories'] or set(patch) != {'title','claim'}:
            raise ValidationError('New memory needs a fresh identity, title and claim')
    elif action == 'update_memory':
        if target not in current['memories'] or current['memories'][target]['deleted'] or not patch or set(patch)-{'title','claim'}:
            raise ValidationError('Unknown, deleted or invalid user memory')
    elif action == 'delete_memory':
        if target not in current['memories'] or current['memories'][target]['deleted'] or patch:
            raise ValidationError('Unknown, deleted or invalid user memory')
    if action in ('create_memory','update_memory'):
        for field,limit in (('title',1000),('claim',12000)):
            if field in patch and (not isinstance(patch[field],str) or not 1<=len(patch[field].strip())<=limit):
                raise ValidationError('Invalid user memory '+field)
    if action in ('create_memory','update_memory','delete_memory'):
        return command
    if action == 'create_task':
        if str(UUID(target)) != target or target in current['tasks'] or not {'title', 'owner'} <= set(patch):
            raise ValidationError('New tasks need a fresh identity, title and owner')
    elif action == 'update_task':
        if target not in current['tasks']:
            raise ValidationError('Unknown manually created task')
    else:
        if target not in current['tasks']:
            source = overview(db, command['event_date'])
            work = {w['id']: w for group in ('personal', 'waiting_dependencies', 'waiting', 'completed', 'cancelled') for w in source.get(group, [])}
            if target not in work:
                raise ValidationError('Unknown meeting task')
    allowed = PLAN_FIELDS if action == 'plan_task' else TASK_FIELDS
    if not patch or set(patch) - allowed:
        raise ValidationError('Unsupported planning field')
    for field in ('title', 'owner'):
        if field in patch and (not isinstance(patch[field], str) or not 1 <= len(patch[field].strip()) <= 1000):
            raise ValidationError('Invalid task ' + field)
    for field in ('scheduled_date', 'due_date'):
        if field in patch and patch[field] is not None and not valid_date(patch[field]):
            raise ValidationError('Invalid task date')
    if 'priority' in patch and patch['priority'] not in ('low', 'normal', 'high'):
        raise ValidationError('Invalid priority')
    if 'estimate_minutes' in patch and patch['estimate_minutes'] is not None and (type(patch['estimate_minutes']) is not int or not 1 <= patch['estimate_minutes'] <= 10080):
        raise ValidationError('Invalid effort estimate')
    if 'status' in patch and patch['status'] not in ('open', 'waiting', 'done', 'cancelled'):
        raise ValidationError('Invalid task status')
    if 'note' in patch and (not isinstance(patch['note'], str) or len(patch['note']) > 10000):
        raise ValidationError('Invalid task note')
    if 'owner' in patch:
        owner = patch['owner'].casefold().strip()
        for member in current['team']:
            if not member['active'] and owner in {n.casefold().strip() for n in [member['name'], *member['aliases']]}:
                prior = current['tasks'].get(target, {}).get('owner', '').casefold().strip()
                if prior != owner:
                    raise ValidationError('An inactive colleague cannot receive a new assignment')
    return command


def record(db, *, command_id, actor_id, command):
    setup(db)
    command_id, actor_id = str(UUID(command_id)), str(UUID(actor_id))
    old = db.execute('SELECT actor_id,data_json FROM planning_events WHERE command_id=?', (command_id,)).fetchone()
    if old:
        if old['actor_id'] != actor_id or json.loads(old['data_json']) != command:
            raise ValidationError('Planning identity reused with different content')
        return command
    prepare(db, command)
    db.execute('INSERT INTO planning_events VALUES (?,?,?,?,?)',
        (command_id, actor_id, command['event_date'], command['target_id'], json.dumps(command, ensure_ascii=False)))
    from projection_order import record as record_order
    record_order(db,'planning',command_id)
    return command


def overlay(db, source, as_of):
    """Merge planning into a read model without changing evidence/checksums."""
    planning = state(db, as_of)
    groups = ('personal', 'waiting_dependencies', 'waiting', 'completed', 'cancelled')
    result = {**source, **{g: [{**w} for w in source.get(g, [])] for g in groups}}
    for group in groups:
        for item in result[group]:
            plan = planning['plans'].get(item['id'], {})
            item.update({k: v for k, v in plan.items() if k in PLAN_FIELDS})
            item['planning_history'] = plan.get('history', [])
    source_tasks={item['id']:(group,item) for group in groups for item in result[group]}
    for task in planning['tasks'].values():
        source_group,source_item=source_tasks.get(task['id'],(None,None))
        if source_item is not None:
            result[source_group].remove(source_item)
        item = {**task, 'claim': task.get('note', ''), 'kind': 'commitment', 'matter': 'Eigene Planung',
                'quotes': [], 'due_text': task.get('due_date'), 'due_reference_date': None, 'required_review': False,
                'planning_history': task['history'], 'history': list(source_item.get('history',[])) if source_item else []}
        if source_item:
            # Source batches, planning commands and explicit approvals live in
            # separate tables.  Calendar dates cannot order two commands from
            # the same day, so select each lifecycle field by canonical replay
            # sequence instead.
            from projection_order import sequence
            field_events=[]
            for event in task['history']:
                action=event.get('action');patch=event.get('patch',{})
                seq=sequence(db,'planning',event['command_id'])
                if action=='create_task':
                    field_events.append((seq,'status','open',event['event_date']))
                for field in ('status','owner','due_date'):
                    if field in patch:field_events.append((seq,field,patch[field],event['event_date']))
            source_rows=db.execute('''SELECT e.action,e.data_json,e.event_date,o.source_version
              FROM work_events e JOIN observations o ON o.id=e.observation_id
              WHERE e.work_id=? AND e.event_date<=? ORDER BY e.rowid''',(task['id'],as_of)).fetchall()
            for row in source_rows:
                data=json.loads(row['data_json']);action=row['action'];seq=sequence(db,'source',row['source_version'])
                if action=='done':field_events.append((seq,'status','done',row['event_date']))
                elif action in ('reopened','progress') and data.get('work_state') in ('open','waiting'):
                    field_events.append((seq,'status',data['work_state'],row['event_date']))
                elif action=='condition_met':field_events.append((seq,'status','open',row['event_date']))
                elif action=='owner_changed':field_events.append((seq,'owner',data.get('owner'),row['event_date']))
                elif action=='date_changed':field_events.append((seq,'due_date',data.get('due_text'),row['event_date']))
            decision_rows=db.execute('SELECT command_id,event_date,data_json FROM human_decisions WHERE work_id=? AND event_date<=? ORDER BY rowid',
                                     (task['id'],as_of)).fetchall()
            for row in decision_rows:
                decision=json.loads(row['data_json']);action=decision.get('action')
                seq=sequence(db,'human',row['command_id'])
                observation=db.execute('SELECT data_json FROM observations WHERE id=?',(decision['observation_id'],)).fetchone()
                automatic=json.loads(observation[0]) if observation else {}
                update=automatic.get('update')
                if action in ('approve','correct_confirm'):
                    if update=='done':field_events.append((seq,'status','done',row['event_date']))
                    elif update in ('reopened','progress') and automatic.get('work_state') in ('open','waiting'):
                        field_events.append((seq,'status',automatic['work_state'],row['event_date']))
                    elif update=='condition_met':field_events.append((seq,'status','open',row['event_date']))
                    elif update=='owner_changed':field_events.append((seq,'owner',automatic.get('owner'),row['event_date']))
                    elif update=='date_changed':field_events.append((seq,'due_date',automatic.get('due_text'),row['event_date']))
                if action!='reject':
                    for field in ('status','owner','due_date'):
                        if field in decision.get('patch',{}):field_events.append((seq,field,decision['patch'][field],row['event_date']))
            latest={}
            for candidate in field_events:
                if candidate[1] not in latest or candidate[0]>latest[candidate[1]][0]:latest[candidate[1]]=candidate
            if 'status' in latest:item['status']=latest['status'][2]
            if 'owner' in latest:item['owner']=latest['owner'][2]
            if 'due_date' in latest:
                item['due_text']=latest['due_date'][2];item['due_date']=latest['due_date'][2]
                item['due_reference_date']=None
            item['last_changed']=max(item.get('last_changed',''),source_item.get('last_changed',''),
                                     *(candidate[3] for candidate in latest.values()))
        group = 'completed' if item['status'] == 'done' else 'cancelled' if item['status'] == 'cancelled' else (
            'waiting_dependencies' if personal(item['owner']) and item['status'] == 'waiting' else
            'personal' if personal(item['owner']) else 'waiting')
        result[group].append(item)
    result['planner'] = {'team': planning['team'], 'supported': True}
    result['knowledge'] = [{**entry} for entry in result.get('knowledge', [])]
    for memory in planning['memories'].values():
        if memory['deleted']:continue
        result['knowledge'].append({'id':memory['id'],'matter_id':'explicit-user-memory',
          'matter_title':'Nutzernotizen','event_date':memory['last_changed'],'data':{
            'kind':'fact','title':memory['title'],'claim':memory['claim'],'owner':None,'due_text':None,
            'quotes':[memory['claim']],'required_review':False,'origin':'manual','provenance':memory['provenance'],
            'memory_history':memory['history']}})
    return result
