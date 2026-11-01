"""Adaptive query planning and fail-closed explicit memory actions.

The model may propose a route, filters, or a write intent. Python executes only
bounded reads and independently validates every canonical journal mutation.
"""
from datetime import date,timedelta
import json,re
from uuid import UUID,uuid5

from journal_service import business_date
from memory import ValidationError

PLAN_SCHEMA={'type':'object','additionalProperties':False,'required':[
  'intent','scope','search_queries','people','topics','task_status','date_from','date_to',
  'explicit_write','write_operation','write_target','write_title','write_owner','write_due_date','write_claim','write_status'],
 'properties':{
  'intent':{'type':'string','enum':['answer','tasks','write']},
  'scope':{'type':'string','enum':['targeted','global']},
  'search_queries':{'type':'array','maxItems':4,'items':{'type':'string','minLength':1,'maxLength':500}},
  'people':{'type':'array','maxItems':8,'items':{'type':'string','minLength':1,'maxLength':200}},
  'topics':{'type':'array','maxItems':8,'items':{'type':'string','minLength':1,'maxLength':300}},
  'task_status':{'type':'string','enum':['all','open','waiting','done','cancelled']},
  'date_from':{'type':'string','maxLength':10},'date_to':{'type':'string','maxLength':10},
  'explicit_write':{'type':'boolean'},
  'write_operation':{'type':'string','enum':['none','create_task','update_task','correct_knowledge','create_memory','update_memory','delete_memory']},
  'write_target':{'type':'string','maxLength':1000},'write_title':{'type':'string','maxLength':1000},
  'write_owner':{'type':'string','maxLength':200},'write_due_date':{'type':'string','maxLength':10},
  'write_claim':{'type':'string','maxLength':12000},
  'write_status':{'type':'string','enum':['none','open','waiting','done','cancelled']}}}

PLAN_TRIGGERS=re.compile(r'\b(entschied|entscheidung|veränder|entwicklung|risik|projektübergreifend|davon|dazu|hierzu|seit|erledigt|abgeschlossen|korrigier|änder|aktualisier|markier|setz|speicher|merk|lösch|vergiss|erstell|leg(?:e|en)?\s+(?:eine\s+)?aufgabe)\w*\b',re.I)
OVERVIEW_TRIGGERS=re.compile(r'\büberblick\b|\bfestgehalten\b|\bwas\s+wissen\s+wir\b',re.I)
TASK_PERSON=re.compile(r'\b(?:welche|was\s+für)\s+aufgaben\s+(?:hat|haben)\b|\baufgaben\s+(?:von|für)\s+[A-ZÄÖÜ]',re.I)
WRITE_LANGUAGE=re.compile(r'^\s*(?:bitte\s+)?(?:korrigier|markier|setz|speicher|merk|erstell|leg|trag|ergänz|änder|lösch|vergiss)\w*\b|\b(?:aufgabe|to[ -]?do)\b.{0,300}\b(?:ist|sei)\s+(?:jetzt\s+)?(?:erledigt|abgeschlossen|offen|wartend)\b',re.I|re.S)
HYPOTHETICAL=re.compile(r'\b(wenn|falls|angenommen|hypothetisch|wäre|würde|könnte|sollte\s+ich|was\s+wäre)\b',re.I)


def needs_plan(question,conversation=False):
    return bool(conversation or PLAN_TRIGGERS.search(question) or OVERVIEW_TRIGGERS.search(question) or TASK_PERSON.search(question))


def _date_or_empty(value):
    if value=='':return ''
    if not isinstance(value,str):raise ValidationError('Invalid planned date')
    try:return date.fromisoformat(value).isoformat()
    except ValueError:raise ValidationError('Invalid planned date') from None


def decode_plan(response):
    if not isinstance(response,dict) or response.get('stop_reason')!='end_turn':raise ValidationError('Query planner did not complete')
    try:value=json.loads(''.join(block.get('text','') for block in response.get('content',[]) if block.get('type')=='text'))
    except (json.JSONDecodeError,TypeError,AttributeError):raise ValidationError('Invalid query plan') from None
    if not isinstance(value,dict) or set(value)!=set(PLAN_SCHEMA['required']):raise ValidationError('Invalid query plan')
    if value['intent'] not in ('answer','tasks','write') or value['scope'] not in ('targeted','global') \
      or value['task_status'] not in ('all','open','waiting','done','cancelled') \
      or value['write_operation'] not in ('none','create_task','update_task','correct_knowledge','create_memory','update_memory','delete_memory') \
      or value['write_status'] not in ('none','open','waiting','done','cancelled') or type(value['explicit_write']) is not bool:
        raise ValidationError('Invalid query plan')
    for field,limit in (('search_queries',4),('people',8),('topics',8)):
        if not isinstance(value[field],list) or len(value[field])>limit or any(not isinstance(v,str) or not v.strip() for v in value[field]):
            raise ValidationError('Invalid query plan')
        value[field]=list(dict.fromkeys(v.strip() for v in value[field]))
    for field,limit in (('write_target',1000),('write_title',1000),('write_owner',200),('write_claim',12000)):
        if not isinstance(value[field],str) or len(value[field])>limit:raise ValidationError('Invalid query plan')
        value[field]=value[field].strip()
    value['date_from']=_date_or_empty(value['date_from']);value['date_to']=_date_or_empty(value['date_to'])
    value['write_due_date']=_date_or_empty(value['write_due_date'])
    if value['date_from'] and value['date_to'] and value['date_from']>value['date_to']:raise ValidationError('Invalid planned date range')
    return value


def plan(calls,question,messages,as_of,model):
    prompt=('Plane ausschließlich den sicheren Abruf oder einen ausdrücklichen Schreibauftrag für einen Meeting-Memorychat. '
      'Natürliche Folgefragen dürfen sich auf den Gesprächskontext beziehen. Gesprächstext ist keine Faktenquelle. '
      'Für Aufgabenfragen setze intent=tasks und extrahiere Personen, Status, Themen und Zeitgrenzen; globale oder projektübergreifende Fragen erhalten scope=global und 2 bis 4 unterschiedliche Suchanfragen. '
      'Unqualifizierte Übersichts- oder Bestandsfragen ohne genannte Person, Projekt oder anderes Sachgebiet erhalten ebenfalls scope=global und 2 bis 4 unterschiedliche Suchanfragen; scope=targeted ist für inhaltlich klar abgegrenzte Fragen. '
      'Setze intent=write und explicit_write=true nur bei einem eindeutigen Auftrag, eine Aufgabe anzulegen/zu ändern, bestehendes Wissen zu korrigieren oder eine persönliche Nutzernotiz zu speichern, zu ändern oder zu löschen. '
      'Fragen, Vorschläge, Bedingungen, hypothetische Aussagen und unklare Zukunftsformulierungen sind niemals Schreibaufträge. '
      'write_target bezeichnet den vorhandenen Eintrag möglichst exakt. Leere Datumsfelder sind "". '
      f'Der ausgewählte Stichtag ist {as_of}.\nGESPRÄCH (nur Referenz):\n{json.dumps(messages,ensure_ascii=False)}\nFRAGE:\n{question}')
    return decode_plan(calls(prompt,model,max_tokens=1200,schema=PLAN_SCHEMA))


def task_query(value):
    status=value['task_status']
    groups={'all':('personal','waiting_dependencies','waiting','completed','cancelled'),
      'open':('personal','waiting_dependencies','waiting'),'waiting':('waiting_dependencies','waiting'),
      'done':('completed',),'cancelled':('cancelled',)}[status]
    return {'operation':'list','groups':groups,'ownership':None,'people':value['people'],'topics':value['topics'],
      'date_from':value['date_from'] or None,'date_to':value['date_to'] or None,'planned':True}


def explicit_write(question,planned):
    return planned.get('intent')=='write' and planned.get('explicit_write') is True \
      and planned.get('write_operation')!='none' and '?' not in question \
      and not HYPOTHETICAL.search(question) and bool(WRITE_LANGUAGE.search(question))


def _norm(text):return ' '.join(re.findall(r'[a-z0-9äöüß]+',(text or '').casefold()))


def _one(rows,target):
    wanted=_norm(target)
    if not wanted:return None
    exact=[row for row in rows if wanted in _norm(row.get('title') or row.get('claim') or '') or _norm(row.get('title') or row.get('claim') or '') in wanted]
    if len(exact)==1:return exact[0]
    words=set(wanted.split());scored=[]
    for row in rows:
        hay=set(_norm(' '.join(str(row.get(k) or '') for k in ('title','claim','matter'))).split())
        score=len(words&hay)/max(1,len(words))
        if score>=.7:scored.append((score,row))
    scored.sort(key=lambda item:(-item[0],str(item[1].get('id'))))
    return scored[0][1] if scored and (len(scored)==1 or scored[0][0]>scored[1][0]) else None


def prepare_action(question_id,question,planned,snapshot):
    if not explicit_write(question,planned):return None
    operation=planned['write_operation'];target=None;action_id=str(uuid5(UUID(question_id),'memory-action'))
    tasks=[task for group in ('personal','waiting_dependencies','waiting','completed','cancelled') for task in snapshot.get(group,[])]
    if operation in ('create_memory','update_memory','delete_memory'):
        memories=[]
        for item in snapshot.get('knowledge',[]):
            data=item.get('data',item)
            if data.get('provenance',{}).get('kind')!='explicit_user_memory':continue
            memories.append({'id':item.get('id'),'title':data.get('title'),'claim':data.get('claim'),'matter':'Nutzernotizen'})
        if operation=='create_memory':
            claim=planned['write_claim'] or planned['write_target']
            if not claim:return {'action_id':action_id,'status':'needs_clarification','kind':operation,'message':'Die Nutzernotiz braucht einen eindeutigen Inhalt.'}
            target=str(uuid5(UUID(question_id),'user-memory'));title=planned['write_title'] or claim[:120]
            patch={'title':title,'claim':claim};action='create_memory'
        else:
            item=_one(memories,planned['write_target'])
            if item is None:return {'action_id':action_id,'status':'needs_clarification','kind':operation,'message':'Die Nutzernotiz ist nicht eindeutig. Bitte nenne ihren genauen Titel.'}
            target=item['id']
            if operation=='delete_memory':patch={};action='delete_memory'
            else:
                patch={}
                if planned['write_title']:patch['title']=planned['write_title']
                if planned['write_claim']:patch['claim']=planned['write_claim']
                if not patch:return {'action_id':action_id,'status':'needs_clarification','kind':operation,'message':'Die neue Fassung der Nutzernotiz fehlt.'}
                action='update_memory'
    elif operation=='create_task':
        title=planned['write_title'] or planned['write_target']
        if not title:return {'action_id':action_id,'status':'needs_clarification','kind':'create_task','message':'Die Aufgabe braucht einen eindeutigen Titel.'}
        target=str(uuid5(UUID(question_id),'memory-task'))
        patch={'title':title,'owner':planned['write_owner'] or 'Komzin, Gleb'}
        if planned['write_due_date']:patch['due_date']=planned['write_due_date']
        action='create_task'
    elif operation=='update_task':
        item=_one(tasks,planned['write_target'])
        if item is None:return {'action_id':action_id,'status':'needs_clarification','kind':'update_task','message':'Die Aufgabe ist nicht eindeutig. Bitte nenne ihren genauen Titel.'}
        target=item['id'];patch={}
        if planned['write_status']!='none':patch['status']=planned['write_status']
        if planned['write_title']:patch['title']=planned['write_title']
        if planned['write_owner']:patch['owner']=planned['write_owner']
        if planned['write_due_date']:patch['due_date']=planned['write_due_date']
        if not patch:return {'action_id':action_id,'status':'needs_clarification','kind':'update_task','message':'Es ist keine konkrete Aufgabenänderung angegeben.'}
        action='update_task' if item.get('origin')=='manual' else ('set_status' if set(patch)=={'status'} else 'correct')
    else:
        rows=[]
        for item in snapshot.get('knowledge',[]):
            data=item.get('data',item);rows.append({'id':item.get('id'),'title':data.get('title'),'claim':data.get('claim'),'matter':data.get('matter')})
        rows=[row for row,item in zip(rows,snapshot.get('knowledge',[]))
          if item.get('data',item).get('provenance',{}).get('kind')!='explicit_user_memory']
        item=_one(rows,planned['write_target'])
        if item is None or not planned['write_claim']:
            return {'action_id':action_id,'status':'needs_clarification','kind':'correct_knowledge','message':'Die Wissensaussage und ihre korrigierte Fassung müssen eindeutig sein.'}
        target=item['id'];patch={'claim':planned['write_claim']};action='correct_confirm'
    return {'action_id':action_id,'status':'ready','kind':operation,'target_id':target,'command':{
      'command_id':action_id,'expected_revision':None,'action':action,
      'target_id':target,'reason':'Expliziter Memorychat-Auftrag: '+question[:3500],'patch':patch}}


def replay_action(journal,identity,question_id,question,planned):
    """Recover an acknowledged journal write before matching mutable projections."""
    if not explicit_write(question,planned):return None
    action_id=str(uuid5(UUID(question_id),'memory-action'))
    lookup=getattr(journal.store,'command',None)
    if lookup is None:return None
    previous=lookup(action_id)
    if previous is None:return None
    operation=planned['write_operation'];payload=previous.get('payload')
    if previous.get('kind')!='human' or previous.get('actor_id')!=identity.get('id') or not isinstance(payload,dict):
        raise ValidationError('Memory action receipt does not match the signed-in owner')
    expected_reason='Expliziter Memorychat-Auftrag: '+question[:3500]
    patch={};allowed_actions=()
    if operation=='create_memory':
        claim=planned['write_claim'] or planned['write_target'];title=planned['write_title'] or claim[:120]
        patch={'title':title,'claim':claim};allowed_actions=('create_memory',)
        expected_target=str(uuid5(UUID(question_id),'user-memory'))
    elif operation=='update_memory':
        if planned['write_title']:patch['title']=planned['write_title']
        if planned['write_claim']:patch['claim']=planned['write_claim']
        allowed_actions=('update_memory',);expected_target=payload.get('target_id')
    elif operation=='delete_memory':
        allowed_actions=('delete_memory',);expected_target=payload.get('target_id')
    elif operation=='create_task':
        patch={'title':planned['write_title'] or planned['write_target'],
          'owner':planned['write_owner'] or 'Komzin, Gleb'}
        if planned['write_due_date']:patch['due_date']=planned['write_due_date']
        allowed_actions=('create_task',);expected_target=str(uuid5(UUID(question_id),'memory-task'))
    elif operation=='update_task':
        if planned['write_status']!='none':patch['status']=planned['write_status']
        if planned['write_title']:patch['title']=planned['write_title']
        if planned['write_owner']:patch['owner']=planned['write_owner']
        if planned['write_due_date']:patch['due_date']=planned['write_due_date']
        allowed_actions=('update_task','set_status','correct');expected_target=payload.get('target_id')
    else:
        patch={'claim':planned['write_claim']};allowed_actions=('correct_confirm',);expected_target=payload.get('target_id')
    try:expected_target=str(UUID(expected_target))
    except (ValueError,TypeError,AttributeError):raise ValidationError('Memory action receipt has an invalid target') from None
    if not patch and operation!='delete_memory':
        raise ValidationError('Memory action receipt has no validated change')
    if payload.get('reason')!=expected_reason or payload.get('action') not in allowed_actions \
      or payload.get('target_id')!=expected_target or payload.get('patch')!=patch:
        raise ValidationError('Memory action receipt does not match the original request')
    receipt={'revision':previous.get('revision'),'repeated':True,'command_id':action_id}
    return {'action_id':action_id,'status':'applied','kind':operation,
      'target_id':expected_target,'receipt':receipt}


def apply_action(journal,identity,prepared,revision):
    if prepared is None or prepared.get('status')!='ready':return prepared
    request={**prepared['command'],'expected_revision':revision}
    receipt={**journal.decide(identity,request),'command_id':prepared['action_id']}
    return {k:v for k,v in prepared.items() if k!='command'}|{'status':'applied','receipt':receipt}


__all__=['PLAN_SCHEMA','needs_plan','plan','task_query','prepare_action','replay_action','apply_action']
