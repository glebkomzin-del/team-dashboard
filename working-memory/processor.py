"""Real API processor for the isolated SQLite prototype; never writes to Supabase."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from memory import connect,register,claim,apply,record_failure,context,overview,ValidationError,fingerprint

ROOT=Path(__file__).resolve().parent
DEFAULT_MODEL='gpt-5.6-terra'
PROMPT_VERSION=os.environ.get('MEMORY_PROMPT_VERSION','v4')
MAX_PROMPT_CHARS=600_000 if PROMPT_VERSION in ('v5','v6','v7','v8','v9') else 140_000
ACTION_GATE=os.environ.get('MEMORY_ACTION_GATE','1')=='1'

def pipeline_version(model):
    if PROMPT_VERSION in ('v10','v11'):
        from hybrid_pipeline import version
        return version(model,compact=PROMPT_VERSION=='v11')
    rules=(ROOT/f'evaluation/prompt-{PROMPT_VERSION}.txt').read_text()+(ROOT/f'evaluation/schema-{PROMPT_VERSION}.json').read_text()
    if ACTION_GATE:rules+=(ROOT/(f'evaluation/work-gate-prompt-{PROMPT_VERSION}.txt' if PROMPT_VERSION in ('v6','v7','v8','v9') else 'evaluation/work-gate-prompt.txt')).read_text()
    if PROMPT_VERSION in ('v6','v7','v8','v9'):rules+=(ROOT/f'evaluation/work-gate-schema-{PROMPT_VERSION}.json').read_text()
    if PROMPT_VERSION in ('v7','v8','v9'):
        for name in ('processor.py','memory.py','corrections.py','human_decisions.py'):rules+=(ROOT/name).read_text()
    if PROMPT_VERSION in ('v8','v9'):rules+=(ROOT/'reconcile.py').read_text()
    if PROMPT_VERSION=='v9':rules+=(ROOT/'temporal_guard.py').read_text()
    if model==DEFAULT_MODEL:
        rules+=(ROOT/'openai_provider.py').read_text()+(ROOT/'call_budget.py').read_text()
    rules+=(ROOT/'evaluation/source-corrections.json').read_text()
    if PROMPT_VERSION in ('v5','v6','v7','v8','v9'): rules+=(ROOT/'context_window.py').read_text()
    return PROMPT_VERSION + (':gate1' if ACTION_GATE else '') + ':' + model + ':' + fingerprint(rules)[:16]

def validate_semantics(proposal):
    for observation in proposal['observations']:
        if observation.get('update', 'none') == 'none' and observation.get('commitment_strength') in ('explicit', 'accepted_request') and observation.get('kind') != 'commitment':
            raise ValidationError('Contradictory commitment classification: an explicit new promise must have kind=commitment; recheck against the original, do not silently discard it')

def apply_work_gate(proposal,verdicts,originals):
    candidates={i for i,o in enumerate(proposal['observations']) if o['kind']=='commitment' or o.get('update','none')!='none'}
    indices=[v['index'] for v in verdicts]
    if len(indices)!=len(set(indices)) or set(indices)!=candidates:raise ValidationError('Gate coverage mismatch')
    for v in verdicts:
        if v.get('verdict') not in ('supported','unsupported','ambiguous','already_done','duplicate','withdrawn'):raise ValidationError('Unknown gate verdict')
        if not v.get('evidence_ids') or any(i not in originals for i in v['evidence_ids']):raise ValidationError('Invalid gate evidence')
        if v.get('due_role') is not None and v['due_role'] not in ('work_deadline','event_time','data_reference','unclear','none'):raise ValidationError('Invalid time role')
        if v['verdict']!='duplicate' and v.get('duplicate_of') is not None:raise ValidationError('Unexpected duplicate target')
        o=proposal['observations'][v['index']];o['work_gate']={**v,'quotes':[originals[i]['text'] for i in v['evidence_ids']]}
        if 'action_uncertainty' in v:
            if v['action_uncertainty'] is not None and not isinstance(v['action_uncertainty'],str):raise ValidationError('Invalid gate action uncertainty')
            if v['verdict'] in ('supported','already_done') and v['action_uncertainty']:raise ValidationError('Supported gate cannot retain unresolved action uncertainty')
            if v['verdict']=='ambiguous' and not v['action_uncertainty']:raise ValidationError('Ambiguous gate needs concrete uncertainty')
            o['prior_action_uncertainty']=o.get('action_uncertainty',o.get('uncertainty'))
            o['action_uncertainty']=v['action_uncertainty']
            o['quotes']=list(dict.fromkeys(o['quotes']+o['work_gate']['quotes']))
            o['resolution_basis']='secondary_source_check'
        if v.get('due_role') in ('event_time','data_reference','unclear') and o.get('due_text'):
            o['original_time_expression']=o['due_text'];o['time_expression_role']=v['due_role'];o['due_text']=None
        if v['verdict']=='already_done':
            o['work_state']='done';o['state_quotes']=o['work_gate']['quotes'];o['quotes']=list(dict.fromkeys(o['quotes']+o['state_quotes']))
            o['prior_action_uncertainty']=o.get('action_uncertainty',o.get('uncertainty'))
            o['action_uncertainty']=None
            o['resolution_basis']='secondary_source_check'
            if o.get('update_target'):o['update']='done'
    by_index={v['index']:v for v in verdicts}
    for verdict in verdicts:
        if verdict['verdict']!='duplicate':continue
        index=verdict['index'];target=verdict.get('duplicate_of')
        if not isinstance(target,int) or isinstance(target,bool) or target>=index or target not in by_index or by_index[target]['verdict'] not in ('supported','already_done'):
            raise ValidationError('Invalid duplicate target')
        duplicate=proposal['observations'][index];primary=proposal['observations'][target]
        if any(o['kind']!='commitment' or o.get('update_target') or o.get('update','none')!='none' for o in (primary,duplicate)) or not primary.get('owner') or primary['owner']!=duplicate.get('owner'):
            raise ValidationError('Duplicate requires same owner and new commitment')
        for field in ('due_text','condition_text'):
            if primary.get(field) and duplicate.get(field) and primary[field]!=duplicate[field]:raise ValidationError('Ambiguous duplicate timing or condition')
            if not primary.get(field) and duplicate.get(field):primary[field]=duplicate[field]
        if primary.get('work_state','open')!=duplicate.get('work_state','open'):
            raise ValidationError('Duplicate states disagree; consolidate from original')
        primary['quotes']=list(dict.fromkeys(primary['quotes']+duplicate['quotes']+duplicate['work_gate']['quotes']))
        primary['state_quotes']=list(dict.fromkeys(primary.get('state_quotes',[])+duplicate.get('state_quotes',[])))
        primary.setdefault('same_meeting_duplicate_indices',[]).append(index)
        duplicate['duplicate_of_index']=target
    return proposal

def units(transcript):
    result={};offset=0
    for index,line in enumerate(transcript.splitlines(keepends=True)):
        value=line.rstrip('\r\n')
        if value.strip(): result[f'U{index+1:04d}']={'text':value,'start':offset,'end':offset+len(value)}
        offset+=len(line)
    return result

def resolve(proposal, originals):
    if not isinstance(proposal,dict) or not isinstance(proposal.get('observations'),list): raise ValidationError('Invalid proposal')
    result={'coverage_notes':proposal.get('coverage_notes',[]),'observations':[]}
    for original in proposal['observations']:
        o=dict(original);ids=o.pop('evidence_ids',[])
        if not ids or any(i not in originals for i in ids): raise ValidationError('Unknown or missing evidence ID')
        state_ids=o.pop('state_evidence_ids',[])
        if any(i not in originals for i in state_ids):raise ValidationError('Unknown state evidence ID')
        o['state_quotes']=[originals[i]['text'] for i in dict.fromkeys(state_ids)]
        o['quotes']=[originals[i]['text'] for i in dict.fromkeys(ids+state_ids)]
        result['observations'].append(o)
    return result

def build_prompt(meeting, db, *, archive_db=None, extra_instruction=''):
    originals=units(meeting['raw_transcript'])
    history=context(db,meeting['meeting_date'][:10])
    state=overview(db,meeting['meeting_date'][:10])
    # Prototype deliberately includes all as-of state within a checked budget.
    # No silent top-k exclusion, no summaries substituted for original evidence.
    prior={'matters':list({r['matter_id']: {'id':r['matter_id'],'title':r['matter_title']} for r in history}.values()),
           'work':state['personal']+state['waiting']+state['waiting_dependencies']+state['completed'],
           'observations':[{'id':r['id'],'matter_id':r['matter_id'],'date':r['event_date'],**r['data']} for r in history]}
    if PROMPT_VERSION in ('v5','v6','v7','v8','v9'):
        from context_window import retrieval
        prior=retrieval(db,meeting,os.environ.get('MEMORY_ARCHIVE_DB','') if archive_db is None else archive_db,prior_days_only=PROMPT_VERSION=='v9')
    prompt=(ROOT/f'evaluation/prompt-{PROMPT_VERSION}.txt').read_text()+'\n\nMeeting: '+meeting['title']+'\nDatum: '+meeting['meeting_date'][:10]+'\nBestehender belegter Stand (Stand zum Meetingdatum):\n'+json.dumps(prior,ensure_ascii=False)+'\nOriginalpassagen:\n'+json.dumps(originals,ensure_ascii=False)
    prompt+=extra_instruction
    if len(prompt)>MAX_PROMPT_CHARS: raise ValidationError('Context budget exceeded; source retained, explicit retrieval/segmentation required')
    return prompt,originals

def collect_stream(response,deadline):
    result={'content':[],'usage':{},'usage_final':False,'stop_reason':None};blocks={};data=[]
    def event(lines):
        if not lines:return
        value=json.loads('\n'.join(lines));kind=value.get('type')
        if kind=='message_start':
            result.update(value['message']);result['usage_final']=False
        elif kind=='content_block_start':
            block=value['content_block']
            if block.get('type')=='fallback':raise ValidationError('Unexpected provider model fallback')
            blocks[value['index']]=dict(block)
        elif kind=='content_block_delta':
            delta=value['delta']
            if delta.get('type')=='text_delta':
                block=blocks[value['index']];block['text']=block.get('text','')+delta['text']
        elif kind=='message_delta':
            result.update(value.get('delta',{}));result['usage'].update(value.get('usage',{}))
        elif kind=='message_stop':result['usage_final']=True
        elif kind=='error':raise ValidationError('Stream error: '+value.get('error',{}).get('type','unknown'))
    try:
        for raw_line in response:
            if time.monotonic()>deadline:raise TimeoutError('Total request deadline exceeded')
            line=raw_line.decode('utf-8').rstrip('\r\n')
            if line.startswith('data:'):data.append(line[5:].lstrip())
            elif not line:event(data);data=[]
        event(data)
        if not result['usage_final']:raise ValidationError('Incomplete event stream')
    except Exception as e:
        result['error']=type(e).__name__+': '+str(e)[:200];result['stop_reason']=None;result['usage_final']=False
    result['content']=[blocks[i] for i in sorted(blocks)]
    return result

def anthropic(prompt,model,max_tokens=24000,schema=None):
    key=os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        keyfile=ROOT/'.local/model-keys.json'
        if keyfile.exists(): key=json.loads(keyfile.read_text()).get('ANTHROPIC_API_KEY')
    if not key: raise RuntimeError('ANTHROPIC_API_KEY missing')
    payload={'model':model,'max_tokens':max_tokens,'stream':True,'messages':[{'role':'user','content':prompt}],
             'output_config':{'format':{'type':'json_schema','schema':schema or json.loads((ROOT/f'evaluation/schema-{PROMPT_VERSION}.json').read_text())}}}
    if model in ('claude-sonnet-5','claude-opus-5'): payload['thinking']={'type':'disabled'}
    req=urllib.request.Request('https://api.anthropic.com/v1/messages',data=json.dumps(payload).encode(),
        headers={'x-api-key':key,'anthropic-version':'2023-06-01','Content-Type':'application/json'})
    started=time.time()
    try:
        # Streaming avoids a long silent HTTP request. Total budget remains bounded.
        with urllib.request.urlopen(req,timeout=60) as response: raw=collect_stream(response,time.monotonic()+420)
    except urllib.error.HTTPError as e:
        # Provider error bodies can contain credential fragments; do not persist them.
        raw={'error':'HTTP '+str(e.code)}
    except Exception as e: raw={'error':type(e).__name__}
    raw['elapsed_seconds']=round(time.time()-started,3)
    return raw

def model_request(prompt,model,max_tokens=24000,schema=None):
    if model in (DEFAULT_MODEL, 'gpt-5.6-luna', 'text-embedding-3-small'):
        from openai_provider import request
        effective=schema if schema is not None else json.loads((ROOT/f'evaluation/schema-{PROMPT_VERSION}.json').read_text())
        return request(prompt,model,max_tokens=max_tokens,schema=effective)
    if model.startswith('claude-'):
        return anthropic(prompt,model,max_tokens=max_tokens,schema=schema)
    raise ValidationError('Unsupported model provider')

def process(db,meeting,model,*,api=None,pipeline=None,archive_db=None,extra_instruction='',extraction_recovery=False):
    if PROMPT_VERSION in ('v10','v11'):
        from hybrid_pipeline import process as hybrid_process
        return hybrid_process(db,meeting,model,api=api,pipeline=pipeline,archive_db=archive_db,
            extra_instruction=extra_instruction,compact=PROMPT_VERSION=='v11',extraction_recovery=extraction_recovery)
    # The production worker injects its persistent budget wrapper. Each request,
    # including repair, gate and lifecycle calls, must pass the same wrapper.
    request_model = api or model_request
    source=meeting.get('source_id') or (meeting.get('baseline_items') or [{}])[0].get('source') or 'supabase-meeting:'+meeting['id']
    job=register(db,source_id=source,event_date=meeting['meeting_date'][:10],title=meeting['title'],transcript=meeting['raw_transcript'],pipeline=pipeline or pipeline_version(model))
    token=claim(db,job,seconds=600)
    if token is None: return {'job':job,'status':'already_applied'}
    folder=ROOT/'.local/runs'/job/__import__('uuid').uuid4().hex;folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        prompt,originals=build_prompt(meeting,db,archive_db=archive_db,extra_instruction=extra_instruction)
        (folder/'prompt.txt').write_text(prompt)
        total_elapsed=0
        for repair in range(2):
            updated=db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND status='leased' AND lease_token=? AND lease_until>?",(time.time()+600,job,token,time.time()))
            if updated.rowcount!=1:raise ValidationError('Lost lease before provider call')
            response=request_model(prompt,model)
            total_elapsed+=response['elapsed_seconds']
            (folder/f'response-{repair}.json').write_text(json.dumps(response,ensure_ascii=False,indent=2))
            run_id=__import__('uuid').uuid4().hex
            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(run_id,job,time.time(),model,json.dumps(response.get('usage',{})),response['elapsed_seconds'],'received',json.dumps(response,ensure_ascii=False)))
            if response.get('stop_reason')!='end_turn':
                db.execute("UPDATE runs SET outcome='provider_incomplete' WHERE id=?",(run_id,))
                raise ValidationError('Provider failed or output incomplete: '+str(response.get('error') or response.get('stop_reason')))
            try:
                raw=json.loads(''.join(c.get('text','') for c in response['content'] if c['type']=='text'))
                proposal=resolve(raw,originals)
                if PROMPT_VERSION in ('v7','v8','v9'):validate_semantics(proposal)
                # Validate citations before paying for the independent action-focused pass.
                from memory import validate,known_work_ids
                known_work=known_work_ids(db,meeting['meeting_date'][:10])
                validate(proposal,meeting['raw_transcript'],known_work)
                if ACTION_GATE:
                    from verify_actions import SCHEMA as gate_schema
                    if PROMPT_VERSION in ('v6','v7','v8','v9'):gate_schema=json.loads((ROOT/f'evaluation/work-gate-schema-{PROMPT_VERSION}.json').read_text())
                    fields=('kind','title','claim','owner','commitment_strength','due_text','condition_text','update_target','update','work_state','action_uncertainty')
                    candidates=[{'index':i,**{k:o.get(k) for k in fields}} for i,o in enumerate(proposal['observations']) if o['kind']=='commitment' or o.get('update','none')!='none']
                    if candidates:
                        current=overview(db,meeting['meeting_date'][:10])
                        if PROMPT_VERSION in ('v5','v6','v7','v8','v9'):
                            from context_window import compact_work
                            current={'work':compact_work(current)}
                        gate_prompt=(ROOT/(f'evaluation/work-gate-prompt-{PROMPT_VERSION}.txt' if PROMPT_VERSION in ('v6','v7','v8','v9') else 'evaluation/work-gate-prompt.txt')).read_text()+'\nMeetingdatum: '+meeting['meeting_date'][:10]+'\nKandidaten (unverbindlich):\n'+json.dumps(candidates,ensure_ascii=False)+'\nBestehende Arbeit:\n'+json.dumps({k:v for k,v in current.items() if k!='knowledge'},ensure_ascii=False)+'\nVollständiges Original:\n'+json.dumps(originals,ensure_ascii=False)
                        if len(gate_prompt)>MAX_PROMPT_CHARS:raise ValidationError('Gate context budget exceeded')
                        checked=db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND lease_token=? AND lease_until>?",(time.time()+600,job,token,time.time()))
                        if checked.rowcount!=1:raise ValidationError('Lost lease before action gate')
                        gate=request_model(gate_prompt,model,max_tokens=6000,schema=gate_schema)
                        total_elapsed+=gate['elapsed_seconds']
                        (folder/f'gate-response-{repair}.json').write_text(json.dumps(gate,ensure_ascii=False,indent=2))
                        db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(uuid_hex:=__import__('uuid').uuid4().hex,job,time.time(),model,json.dumps(gate.get('usage',{})),gate['elapsed_seconds'],'work_gate',json.dumps(gate,ensure_ascii=False)))
                        if gate.get('stop_reason')!='end_turn':raise ValidationError('Gate incomplete: '+str(gate.get('error')))
                        verdicts=json.loads(''.join(c.get('text','') for c in gate['content'] if c['type']=='text'))['verdicts']
                        proposal=apply_work_gate(proposal,verdicts,originals)
                if PROMPT_VERSION in ('v8','v9'):
                    import reconcile
                    pending=reconcile.candidates(db,meeting,proposal,prior_days_only=PROMPT_VERSION=='v9')
                    if pending:
                        changes=[]
                        for batch_index,batch in enumerate(reconcile.partitions(meeting,pending,originals,MAX_PROMPT_CHARS)):
                            lifecycle_prompt=reconcile.prompt(meeting,batch,originals)
                            checked=db.execute("UPDATE jobs SET lease_until=? WHERE id=? AND lease_token=? AND lease_until>?",(time.time()+600,job,token,time.time()))
                            if checked.rowcount!=1:raise ValidationError('Lost lease before lifecycle review')
                            lifecycle=request_model(lifecycle_prompt,model,max_tokens=12000,schema=reconcile.SCHEMA)
                            total_elapsed+=lifecycle['elapsed_seconds']
                            (folder/f'lifecycle-response-{repair}-{batch_index}.json').write_text(json.dumps(lifecycle,ensure_ascii=False,indent=2))
                            db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(__import__('uuid').uuid4().hex,job,time.time(),model,json.dumps(lifecycle.get('usage',{})),lifecycle['elapsed_seconds'],'lifecycle_review',json.dumps(lifecycle,ensure_ascii=False)))
                            if lifecycle.get('stop_reason')!='end_turn':raise ValidationError('Lifecycle review incomplete')
                            changes.extend(json.loads(''.join(c.get('text','') for c in lifecycle['content'] if c['type']=='text'))['results'])
                        proposal['observations'].extend(reconcile.observations(pending,changes,originals))
                if PROMPT_VERSION=='v9':
                    from temporal_guard import guard
                    proposal=guard(db,meeting,proposal)
                result=apply(db,job,token,proposal,model=model,usage=response.get('usage'),elapsed=response['elapsed_seconds'],run_id=run_id)
                return {'job':job,'status':'applied','observations':len(result),'new_work':sum(o['creates_work'] for o in result),
                        'elapsed_seconds':total_elapsed,'repair_calls':repair,'usage_last_call':response.get('usage')}
            except (ValidationError,ValueError) as e:
                db.execute("UPDATE runs SET outcome='rejected' WHERE id=?",(run_id,))
                if repair:raise
                # Explicitly untrusted proposal. Original source and as-of context remain authoritative.
                failed_text=''.join(c.get('text','') for c in response['content'] if c['type']=='text')
                prompt+='\n\nTECHNISCHE KORREKTUR EINES UNGÜLTIGEN VORSCHLAGS. Der folgende Vorschlag ist keine Wissensquelle. Prüfe ihn ausschließlich am obigen Original. Fehler: '+str(e)+'\nKorrigiere Beleg-IDs, due_text und condition_text (jeweils eine zusammenhängende buchstabengetreue Zeichenfolge aus den ausgewählten Belegpassagen, sonst null; Einschränkung dann im claim erhalten). Alle relevanten Aussagen erhalten, keine neuen unbelegten Aussagen hinzufügen. Antworte mit dem vollständigen korrigierten JSON.\nUnverbindlicher Vorschlag:\n'+failed_text
                if len(prompt)>MAX_PROMPT_CHARS:raise ValidationError('Repair context budget exceeded')
                (folder/'repair-prompt.txt').write_text(prompt)

    except Exception as e:
        record_failure(db,job,token,e)
        raise

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('meetings',nargs='+');parser.add_argument('--db',default='.local/prototype.sqlite');parser.add_argument('--model',default=DEFAULT_MODEL)
    args=parser.parse_args();db=connect(args.db)
    meetings=sorted([json.loads(Path(path).read_text()) for path in args.meetings],key=lambda m:(m['meeting_date'],m['id']))
    failed=False
    for meeting in meetings:
        try: print(json.dumps({'meeting':meeting['title'],**process(db,meeting,args.model)},ensure_ascii=False),flush=True)
        except Exception as e:
            print(json.dumps({'meeting':meeting['title'],'status':'failed','error':str(e)},ensure_ascii=False),flush=True);failed=True;break
    db.close()
    if failed: raise SystemExit(1)
