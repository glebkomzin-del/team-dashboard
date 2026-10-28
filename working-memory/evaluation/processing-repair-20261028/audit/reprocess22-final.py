"""Read-only, metadata-only acceptance of the 22 explicitly selected originals."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REMOTE = r'''import base64, hashlib, json, subprocess, urllib.request
from pathlib import Path
CT='dashboard-memory-canonical-draft-canonical-draft-1'
DB='dashboard-supabase-20261003-db-1'
ROOT=Path('/opt/dashboard-memory-canonical-draft/.local/recovery/reprocess22-20261028')
DEPLOY=Path('/opt/dashboard-memory-canonical-draft/.local/recovery/processing-repair-20261028-lead/deployment')

def encode(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()

def command(args,data=None):
    result=subprocess.run(args,input=data,capture_output=True,timeout=180)
    if result.returncode: raise RuntimeError('Read-only command failed')
    return result.stdout

def lit(value):
    return "convert_from(decode('"+base64.b64encode(str(value).encode()).decode()+"','base64'),'UTF8')"

def human_check(payload,hashes):
    preserved=[x['ref'] for x in payload['entries'] if x.get('ref') in hashes and x.get('changes')==[]]
    return payload.get('personal_decisions_preserved')==11 and len(preserved)==11 and set(preserved)==hashes and not any(x.get('new',{}).get('kind')=='human' for x in payload['entries'])

def call_ranges(runs,calls):
    ordered=sorted(runs,key=lambda r:r['start_index'])
    slots=sorted(c['call_index'] for c in calls)
    if not ordered or not slots or len({r['start_index'] for r in ordered})!=len(ordered) or len({r['command_id'] for r in ordered})!=len(ordered):
        raise ValueError('Missing or duplicate attempt boundary')
    if slots!=list(range(ordered[0]['start_index'],slots[-1]+1)):
        raise ValueError('Call range is not contiguous and unique')
    result=[]
    for i,run in enumerate(ordered):
        end=ordered[i+1]['start_index']-1 if i+1<len(ordered) else slots[-1]
        part=[c for c in calls if run['start_index']<=c['call_index']<=end]
        if not part:raise ValueError('Attempt has no calls')
        result.append({'command_id':run['command_id'],'start_index':run['start_index'],'end_index':end,
                       'calls':len(part),'actual_micro_usd':sum(c['actual_micro_usd'] or 0 for c in part)})
    return result

def context_check(rows,artifact,calls):
    approval=artifact['context_continuation']; counts=artifact['context_counts']
    if len(rows)!=1 or not approval or rows[0]['command_id']!=approval['command_id'] or not rows[0]['owner'] or rows[0]['request']!=rows[0]['result'] or rows[0]['result']!=approval:
        raise ValueError('Context continuation audit differs')
    if approval['execution_path']!='owner_full_reprocess_context_continuation' or approval['attempt_command_id']!=artifact['owner_reprocess_command'] or approval['attempt_command_id']!='e9a2a394-dab8-5585-b7ee-7570223ac4b8' or approval['revision']!=355 or approval['next_new_call_index']!=125 or approval['calls_hash']!='c0ae6f2cb016070c62e7c0ad4d22c1333665d0970000210fca046b5d0b058e98' or approval['job_id']!='9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7' or approval['pipeline']!=artifact['pipeline'] or approval['failure_updated_at']!='2026-10-28T20:18:07.253703+00:00':
        raise ValueError('Context continuation scope differs')
    capture=approval['capture']
    if capture['prompt_sha256']!='d4c9b6455bc0e221b1e87ab34fe2b713f121631cb236daa3db7c34641f039073' or capture['schema_sha256']!='c5c64bd2012db4c6c937910cce3782f8e30e8457868e7cdf9595257f2fc71f07' or capture['max_output_tokens']!=59736 or capture['conservative_total_tokens']!=1062612:
        raise ValueError('Captured compact request differs')
    baseline=sorted((c for c in calls if 2<=c['call_index']<=124),key=lambda c:c['call_index'])
    signature='|'.join(':'.join(str(c[k]) for k in ('call_index','request_hash','response_hash','actual_micro_usd')) for c in baseline)
    if len(baseline)!=123 or hashlib.sha256(signature.encode()).hexdigest()!=approval['calls_hash'] or sum(c['actual_micro_usd'] for c in baseline)!=167049:
        raise ValueError('Known compact prefix changed')
    if not counts or len({x['request_hash'] for x in counts})!=len(counts) or sorted(counts,key=lambda x:x['request_hash'])!=sorted(artifact['saved_context_counts'],key=lambda x:x['request_hash']):
        raise ValueError('Exact count receipts differ')
    reservations={r['request_hash']:r for r in artifact['count_reservations']}
    if len(reservations)!=len(counts):raise ValueError('Exact count reservation coverage differs')
    result=[]
    for count in counts:
        matching=[c for c in calls if c['request_hash']==count['request_hash']]
        if len(matching)!=1:raise ValueError('Count request is not a unique normal call')
        call=matching[0]; reservation=reservations[count['request_hash']]; stage=count['stage']
        if not (stage.startswith('compact-') and stage[8:].isdigit() and type(count['input_tokens']) is int and count['input_tokens']>0 and type(count['max_output_tokens']) is int and 0<count['max_output_tokens']<=64000 and count['framing_tokens']==4096 and count['limit']==1050000 and count['input_tokens']+4096+count['max_output_tokens']<=1050000 and call['call_index']>=125 and call['received'] and call['stop_reason']=='end_turn' and call['model']==count['model'] and call['max_tokens']==count['max_output_tokens'] and type(call['actual_input_tokens']) is int and 0<call['actual_input_tokens']<=count['input_tokens']+4096 and reservation['call_index']==call['call_index'] and reservation['provider_input_tokens']==count['input_tokens'] and reservation['reserved_micro_usd']>0):
            raise ValueError('Exact count was not used within the normal budget')
        result.append({'stage':stage,'input_tokens':count['input_tokens'],'max_output_tokens':count['max_output_tokens'],'call_index':call['call_index']})
    return result

def run(bundle):
    targets=bundle['targets']; space=bundle['space']; sp=lit(space)+'::uuid'
    assert len(targets)==len({t['id'] for t in targets})==22
    ids=','.join(lit(t['id']) for t in targets)
    query="""BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SELECT json_build_object(
'space',(SELECT json_build_object('revision',revision,'archive_revision',archive_revision) FROM wm_spaces WHERE id=SPACE),
'config',(SELECT row_to_json(c) FROM wm_processing_config c WHERE space_id=SPACE),
'jobs',(SELECT json_agg(json_build_object('id',j.id,'state',j.state,'reason',j.reason,'source_id',j.source_id,'document_id',j.document_id,'event_date',j.event_date,'body_hash',d.body_hash,'body_content_hash',encode(sha256(convert_to(d.body,'UTF8')),'hex'))) FROM wm_jobs j LEFT JOIN wm_archive_documents d ON d.space_id=j.space_id AND d.id=j.document_id WHERE j.space_id=SPACE AND j.id IN (IDS)),
'sources',(SELECT json_agg(json_build_object('id',id,'source_id',source_id,'content_hash',content_hash,'event_date',event_date)) FROM wm_source_versions WHERE space_id=SPACE AND id IN (IDS)),
'source_count',(SELECT count(*) FROM wm_source_versions WHERE space_id=SPACE),
'notes',(SELECT json_agg(json_build_object('id',id,'document_id',document_id,'origin_id',origin_id,'note_hash',note_hash,'content_hash',encode(sha256(convert_to(note_json,'UTF8')),'hex'))) FROM wm_archive_notes WHERE space_id=SPACE AND origin='source_summary' AND origin_id IN (IDS)),
'reviews',(SELECT json_agg(json_build_object('id',id,'job_id',job_id,'state',state,'review_sha256',review_sha256,'payload',payload)) FROM wm_generation_reviews WHERE space_id=SPACE AND job_id IN (IDS) AND state='accepted'),
'journal',(SELECT json_agg(json_build_object('revision',revision,'review_sha256',payload->>'review_sha256')) FROM wm_journal WHERE space_id=SPACE AND kind='generation' AND revision>340),
'humans',(SELECT json_agg(json_build_object('kind',kind,'command_id',command_id,'actor_id',actor_id,'payload',payload)) FROM wm_journal WHERE space_id=SPACE AND kind='human' AND revision<=340),
'runs',(SELECT json_agg(json_build_object('job_id',job_id,'command_id',command_id,'start_index',(result->>'start_index')::int,'targets_sha256',request->>'targets_sha256','previous_command_id',request->>'previous_command_id','reviewed_failure',request->'reviewed_failure','reviewed_attempt_limit',request->'reviewed_attempt_limit','token_override',result->'token_override','owner',actor_id=(SELECT owner_id FROM wm_spaces WHERE id=SPACE))) FROM wm_job_decisions WHERE space_id=SPACE AND job_id IN (IDS) AND request->>'execution_path'='owner_full_reprocess_standard_ledger'),
'continuations',(SELECT json_agg(json_build_object('job_id',job_id,'command_id',command_id,'owner',actor_id=(SELECT owner_id FROM wm_spaces WHERE id=SPACE),'request',request,'result',result)) FROM wm_job_decisions WHERE space_id=SPACE AND request->>'execution_path'='owner_full_reprocess_context_continuation'),
'calls',(SELECT json_agg(json_build_object('job_id',m.job_id,'call_index',m.call_index,'request_hash',m.request_hash,'response_hash',m.response_hash,'received',m.response_json IS NOT NULL,'actual_micro_usd',m.actual_micro_usd,'model',m.request_json::jsonb->>'model','max_tokens',(m.request_json::jsonb->>'max_tokens')::int,'actual_input_tokens',(m.response_json::jsonb#>>'{usage,input_tokens}')::bigint,'stop_reason',m.response_json::jsonb->>'stop_reason')) FROM wm_model_calls m WHERE m.space_id=SPACE AND m.job_id IN (IDS) AND EXISTS(SELECT 1 FROM wm_job_decisions d WHERE d.space_id=m.space_id AND d.job_id=m.job_id AND d.request->>'execution_path'='owner_full_reprocess_standard_ledger' AND m.call_index>=(d.result->>'start_index')::int)),
'job_states',(SELECT json_object_agg(state,n) FROM (SELECT state,count(*) n FROM wm_jobs WHERE space_id=SPACE GROUP BY state)x)); COMMIT;""".replace('SPACE',sp).replace('IDS',ids)
    data=json.loads(command(['docker','exec','-i',DB,'psql','-U','postgres','-d','postgres','-XqAt','-v','ON_ERROR_STOP=1'],query.encode()))
    container_code="""import hashlib,json,os,sys
from pathlib import Path
ids=json.load(sys.stdin);root=Path('/app/.local/projections-rc1-20260919/worker-reprocess22');result={}
for ident in ids:
 p=root/ident/'prepared.json'
 if not p.exists():continue
 a=json.loads(p.read_text()); n=a['note']; g=a['generation']; receipts=[]
 ledger=Path('/app/.local/reprocess22-reservations')/ident
 if ledger.exists():
  for f in ledger.rglob('receipt.json'):
   r=json.loads(f.read_text()); receipts.append({k:r[k] for k in ('call_index','request_hash','response_hash','actual_micro_usd','model')})
 context_counts=a.get('context_counts',[]);count_reservations=[]
 for f in ledger.rglob('reservation.json'):
  r=json.loads(f.read_text())
  if r['request_hash'] in {x['request_hash'] for x in context_counts}:
   count_reservations.append({k:r[k] for k in ('call_index','request_hash','provider_input_tokens','reserved_micro_usd')})
 saved_counts=[]
 if a.get('context_continuation'):
  for f in (root/ident/'attempts'/a['context_continuation']['attempt_command_id']/'context-counts').glob('*.json'):
   saved_counts.append(json.loads(f.read_text()))
 result[ident]={'pipeline':a['pipeline'],'context_continuation':a.get('context_continuation'),'context_counts':context_counts,'saved_context_counts':saved_counts,'count_reservations':count_reservations,'review_id':a['review_id'],'review_sha256':g['review_sha256'],'expected_revision':a['expected_revision'],'owner_reprocess_command':a.get('owner_reprocess_command'),'body_hash':a['body_hash'],'note_id':n['id'],'note_hash':n['note_hash'],'note_content_hash':hashlib.sha256(n['note_json'].encode()).hexdigest(),'note_document_id':n['document_id'],'note_origin_id':n['origin_id'],'receipts':receipts}
print(json.dumps({'artifacts':result,'flags':{k:os.environ.get(k) for k in ('MEMORY_READ_ONLY','MEMORY_AUTOMATIC_ENABLED','MEMORY_INTAKE_ENABLED','MEMORY_QA_ENABLED','MEMORY_ORIGINAL_DELETION_ENABLED')},'code_hashes':{k:hashlib.sha256(Path('/app',k).read_bytes()).hexdigest() for k in ('memory.py','openai_provider.py')}}))
"""
    runtime=json.loads(command(['docker','exec','-i',CT,'python','-B','-c',container_code],json.dumps([t['id'] for t in targets]).encode()))
    state=json.loads((ROOT/'state.json').read_text())
    original_resources=json.loads((ROOT/'resource-before.json').read_text())
    original_flags=json.loads((DEPLOY/'state.json').read_text())['original_flags']
    resources=json.loads(command(['docker','inspect','--format','{{json .HostConfig}}',CT]))
    resources={k:resources[k] for k in original_resources}
    human_hashes={digest(h) for h in data['humans'] or []}
    jobs={x['id']:x for x in data['jobs'] or []};sources={x['id']:x for x in data['sources'] or []}
    reviews={x['job_id']:x for x in data['reviews'] or []}; artifacts=runtime['artifacts']
    notes={x['id']:x for x in data['notes'] or []}; journal={x['review_sha256']:x['revision'] for x in data['journal'] or []}
    runs={}
    for run in data['runs'] or []:runs.setdefault(run['job_id'],[]).append(run)
    calls=data['calls'] or []
    assert len(calls)==len({(x['job_id'],x['call_index']) for x in calls}), 'Duplicate call identity'
    errors=[];rows=[];normal_cost=0;bounded_cost=0;bounded_count=0
    if len(human_hashes)!=11:errors.append('Expected exactly 11 original personal decisions')
    if state['targets_sha256']!=bundle['targets_sha256']:errors.append('Runner target snapshot changed')
    if data['config']!=bundle['config']:errors.append('Processing configuration changed')
    expected_code={'memory.py':'e822eb293d6d87cc74f0df5671e4d656c060c81ccce6502860b7c142803c2316','openai_provider.py':'fe6dc8e07c5e90bacca8e1b6b364b97fab2715d1589209ea457a909d4a92c0d3'}
    if runtime['code_hashes']!=expected_code:errors.append('Runtime code changed')
    for target in targets:
        ident=target['id'];job=jobs.get(ident);checks={}
        checks['original']=bool(job and all(job[k]==target[k] for k in ('source_id','document_id','event_date','body_hash')) and job['body_content_hash']==target['body_hash'])
        row={'job':ident[:8],'state':job['state'] if job else 'missing','checks':checks}
        if job and job['state']=='applied':
            a=artifacts.get(ident);s=sources.get(ident);review=reviews.get(ident)
            checks['source_version']=bool(s and s['source_id']==target['source_id'] and s['content_hash']==target['body_hash'] and s['event_date']==target['event_date'])
            checks['artifact']=bool(a and a['body_hash']==target['body_hash'])
            note=notes.get(a['note_id']) if a else None
            checks['summary']=bool(a and note and note['note_hash']==note['content_hash']==a['note_hash']==a['note_content_hash'] and note['document_id']==a['note_document_id']==target['document_id'] and note['origin_id']==a['note_origin_id']==ident)
            payload=review['payload'] if review else {}
            checks['accepted_generation']=bool(a and review and review['id']==a['review_id'] and review['review_sha256']==a['review_sha256']==payload.get('review_sha256') and digest({k:v for k,v in payload.items() if k!='review_sha256'})==payload['review_sha256'] and journal.get(payload['review_sha256'])==a['expected_revision']+1)
            checks['personal_decisions']=bool(review and human_check(payload,human_hashes))
            checks['new_source']=len(payload.get('new_sources',[]))==1 and payload['new_sources'][0]['id']==ident
            if ident.startswith('be7fb810'):
                blocks=[]
                def walk(value):
                    if isinstance(value,dict):
                        if value.get('mode')=='bounded_recovery_generation' and value.get('job_id')==ident:blocks.append(value)
                        for v in value.values():walk(v)
                    elif isinstance(value,list):
                        for v in value:walk(v)
                walk(payload)
                receipts=blocks[0]['recovery_receipts'] if len(blocks)==1 else []
                checks['bounded_receipts']=len(receipts)==7 and len({x['call_index'] for x in receipts})==7 and all(type(x['actual_micro_usd']) is int for x in receipts)
                bounded_cost=sum(x['actual_micro_usd'] for x in receipts);bounded_count=len(receipts)
                row.update(calls=len(receipts),actual_micro_usd=bounded_cost)
            else:
                attempts=sorted(runs.get(ident,[]),key=lambda r:r['start_index']);selected=[c for c in calls if c['job_id']==ident]
                saved={r['call_index']:r for r in a['receipts']} if a else {}
                checks['owner_audit']=bool(a and attempts and len(attempts)<=2 and all(r['owner'] and r['targets_sha256']==bundle['targets_sha256'] for r in attempts) and attempts[-1]['command_id']==a['owner_reprocess_command'])
                if len(attempts)==2:
                    retry=attempts[1];reviewed=retry.get('reviewed_failure') or {}
                    cases={'f09befd74b16f5d6032a56de408f17aeb1abf458d0f0b828ddcab36534f435ae':(67,'3d47b003cdf39c2e836575122fcfe0fe3beec9c6598810d2e4201bbb1180ca5e'),
                           '9266439fe8c4bb320db97d2a4bb1c4f16b5badb43f9bebf51c2f2191df6a61f7':(2,'955a4f691e8ac47b3c97861886e13d8351cb0a24713feea55e89ecb5d3ac1a94')}
                    expected=cases.get(ident)
                    checks['reviewed_attempt']=bool(expected and attempts[0]['start_index']==1 and retry['start_index']==expected[0] and retry['previous_command_id']==attempts[0]['command_id'] and retry['reviewed_attempt_limit']==1 and reviewed.get('response_hash')==expected[1])
                    if ident.startswith('9266439f'):
                        override={'request_hash':'825d696d562fc164874de3d44bcd70541c3ab17ac165308f4ef567e5a48a9b59','from_max_tokens':24000,'to_max_tokens':48000}
                        by_index={c['call_index']:c for c in selected}
                        checks['token_limit_override']=bool(retry.get('token_override')==reviewed.get('token_override')==override and by_index.get(1,{}).get('request_hash')==override['request_hash'] and by_index.get(1,{}).get('response_hash')==expected[1] and by_index.get(1,{}).get('actual_micro_usd')==149115 and by_index.get(1,{}).get('max_tokens')==24000 and by_index.get(2,{}).get('max_tokens')==48000 and all(c.get('max_tokens')!=48000 for c in selected if c['call_index']!=2))
                if ident.startswith('9266439f'):
                    try:
                        context_counts=context_check([x for x in data['continuations'] or [] if x['job_id']==ident],a,selected)
                        row['context_counts']=context_counts;checks['context_continuation']=True
                    except (ValueError,KeyError,TypeError):checks['context_continuation']=False
                try:row['attempt_ranges']=call_ranges(attempts,selected);checks['attempt_ranges']=True
                except ValueError:checks['attempt_ranges']=False
                checks['normal_receipts']=bool(a and selected and len(selected)==len(saved)==len(a['receipts']) and all(c['received'] and type(c['actual_micro_usd']) is int and saved.get(c['call_index'])=={k:c[k] for k in ('call_index','request_hash','response_hash','actual_micro_usd','model')} for c in selected))
                row.update(calls=len(selected),actual_micro_usd=sum(c['actual_micro_usd'] or 0 for c in selected))
        if not all(checks.values()):errors.append('Failed checks: '+ident[:8])
        rows.append(row)
    applied=sum(r['state']=='applied' for r in rows)
    if applied!=len(state['applied']):errors.append('DB/runner applied count differs; retry after active adoption')
    normal_cost=sum(c['actual_micro_usd'] or 0 for c in calls)
    try:
        with urllib.request.urlopen('http://127.0.0.1:8798/health',timeout=10) as response:health=response.status
    except Exception:health=None
    restored=runtime['flags']==original_flags and resources==original_resources and data['config']['enabled'] is True
    complete=applied==22 and not errors
    result={'status':'FAIL' if errors else ('PASS' if complete else 'IN_PROGRESS'),'all_22_complete':complete,'applied':applied,'target_count':22,'revision':data['space']['revision'],'source_versions':data['source_count'],'expected_final_revision':362,'expected_final_source_versions':349,'personal_decisions':len(human_hashes),'rows':rows,'new_normal_calls':len(calls),'normal_received_calls':sum(c['received'] for c in calls),'normal_actual_micro_usd':normal_cost,'bounded_calls':bounded_count,'bounded_actual_micro_usd':bounded_cost,'combined_actual_micro_usd':normal_cost+bounded_cost,'cost_note':'Distinct normal ledger slots plus be7 bounded receipts; imported/replayed answers counted once. Pending source cost included.','runtime_flags':runtime['flags'],'original_flags':original_flags,'resources':resources,'original_resources':original_resources,'original_runtime_restored':restored,'health_status':health,'job_states':data['job_states'],'errors':errors,'read_only':True,'limits':'Metadata/readback audit; does not replace prior full generation verification or authenticated browser acceptance.'}
    if complete and (result['revision']!=362 or result['source_versions']!=349):result['status']='FAIL';result['errors'].append('Unexpected final revision/source count')
    print(json.dumps(result,ensure_ascii=False,indent=2))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete',action='store_true')
    parser.add_argument('--require-restored',action='store_true')
    parser.add_argument('--self-check',action='store_true')
    args=parser.parse_args()
    if args.self_check:
        namespace={};exec(REMOTE,namespace)
        humans=[{'kind':'human','command_id':str(n),'actor_id':'owner','payload':{'n':n}} for n in range(11)]
        hashes={namespace['digest'](h) for h in humans}
        payload={'personal_decisions_preserved':11,'entries':[{'ref':h,'changes':[]} for h in hashes]}
        assert namespace['human_check'](payload,hashes)
        payload['entries'][0]['changes']=[{'path':['payload'],'value':{}}]
        assert not namespace['human_check'](payload,hashes)
        print('PASS: unchanged human references accepted; altered human reference rejected; no network used')
        return
    here=Path(__file__).resolve().parent
    raw=(here/'private/reprocess22-targets.json').read_bytes();snapshot=json.loads(raw)
    config=json.loads((here/'private/reprocess22-config-before.json').read_text())['config']
    bundle={'space':snapshot['space']['id'],'targets':snapshot['targets'],'targets_sha256':hashlib.sha256(raw).hexdigest(),'config':config}
    source=REMOTE+'\nrun(json.loads(base64.b64decode('+repr(base64.b64encode(json.dumps(bundle).encode()).decode())+')))\n'
    result=subprocess.run(['ssh','-i','/Users/glebkomzin/.ssh/id_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=12','root@178.105.167.26','python3 -'],input=source.encode(),capture_output=True,timeout=240)
    if result.returncode:
        print(json.dumps({'status':'ERROR','error':'Read-only remote audit failed; raw diagnostic intentionally not printed'}));raise SystemExit(2)
    try:data=json.loads(result.stdout)
    except (ValueError,UnicodeError):raise SystemExit('Remote audit did not return metadata JSON')
    print(json.dumps(data,ensure_ascii=False,indent=2))
    if data['status']=='FAIL' or (args.require_complete and not data['all_22_complete']) or (args.require_restored and not data['original_runtime_restored']):raise SystemExit(1)


if __name__=='__main__':main()
