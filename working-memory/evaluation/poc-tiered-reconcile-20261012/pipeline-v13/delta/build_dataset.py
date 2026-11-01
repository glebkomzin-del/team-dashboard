"""Offline streaming extraction, exact delta roundtrip, size estimates and replay selection."""
import argparse
import copy
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
DEFAULT_SCRATCH = Path('/private/tmp/claude-501/-Users-glebkomzin-Documents-09-Tech-Appdaten-Code-Dashboard-Job/97396696-9d2c-4fb9-9608-9fd5187044bc/scratchpad/compact_calls.jsonl')
DEFAULT_ARCHIVE = Path.home() / 'Library/Application Support/Dashboard Job Backup/archives/dashboard-20261012T155114Z.tar.gz'

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def parsed(value):
    return json.loads(value) if isinstance(value, str) else value

def typed_equal(a,b):
    if type(a) is not type(b): return False
    if isinstance(a,dict): return a.keys()==b.keys() and all(typed_equal(a[k],b[k]) for k in a)
    if isinstance(a,list): return len(a)==len(b) and all(typed_equal(x,y) for x,y in zip(a,b))
    return a==b

def section(prompt,marker):
    return json.JSONDecoder().raw_decode(prompt.split(marker,1)[1].lstrip())[0]

def unpack(packed):
    result=dict(packed['metadata'])
    for name,table in packed['tables'].items():
        values=[]
        for row in table['rows']:
            if len(row)!=len(table['fields']): raise ValueError('packed column mismatch')
            value={}
            for key,cell in zip(table['fields'],row):
                if cell=={'missing':True}: continue
                if key in table['text_fields'] and cell is not None:
                    if type(cell) is not int: raise ValueError('packed text index')
                    cell=packed['texts'][cell]
                value[key]=cell
            values.append(value)
        result[name]=values
    return result

def extract(archive,scratch):
    prior={}
    with scratch.open() as handle:
        for line in handle:
            row=json.loads(line)
            prior[(row.get('job_id'),row.get('call_index'))]=row
    counts={'scratch_rows':len(prior),'archive_compact_calls':0,'parseable_responses':0,'unparseable_responses':0,'scratch_matches':0}
    with tarfile.open(archive,'r|gz') as stream:
        for member in stream:
            if not member.name.endswith('canonical/queue.jsonl'): continue
            for line in stream.extractfile(member):
                envelope=json.loads(line)
                if envelope.get('kind')!='call':continue
                record=parsed(envelope['record_json'])
                request=parsed(record.get('request_json')) or {}
                prompt=request.get('prompt','')
                if 'Bereits geöffnete Original-IDs' not in prompt:continue
                counts['archive_compact_calls']+=1
                response=parsed(record.get('response_json')) or {}
                key=(record.get('job_id'),record.get('call_index'))
                cached=prior.get(key)
                if cached:counts['scratch_matches']+=1
                try:
                    content=''.join(item.get('text','') for item in response.get('content',[]) if isinstance(item,dict))
                    full=json.loads(content)
                    if not isinstance(full,dict):raise ValueError('response not object')
                    obs=section(prompt,'Vorläufige Beobachtungen:\n')
                    work=unpack(section(prompt,'Kandidaten:\n'))['work']
                except (ValueError,KeyError,TypeError,IndexError):
                    counts['unparseable_responses']+=1
                    continue
                if cached and 'obs_in' in cached and not typed_equal(obs,cached['obs_in']):
                    raise ValueError('scratch observation mismatch')
                counts['parseable_responses']+=1
                yield {'job_id':key[0],'call_index':key[1], 'request_json':request,'obs_in':obs,'work':work,'full_response':full,'reference_usage':response.get('usage',{}),'stop_reason':response.get('stop_reason'),'terminal_status':response.get('terminal_status')},counts
            break
    if counts['archive_compact_calls']==0:raise ValueError('no compact calls')
    extract.counts=counts

def helper(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
    return module

def token_estimate(text):return math.ceil(len(text)/3.6)

def stats(values):
    return {'sum':sum(values),'median':statistics.median(values),'max':max(values)}

def measure_and_select(rows,counts):
    codec=helper('delta_codec');schema=helper('delta_schema')
    sizes=[];prepared=[];success=0
    for row in rows:
        full=row['full_response'];obs=row['obs_in'];work=row['work']
        delta=codec.to_delta(full,obs,work)
        decoded=codec.from_delta(delta,obs,work)
        if not typed_equal(decoded,full):raise ValueError('roundtrip mismatch: '+str(row['call_index']))
        success+=1
        a=dump(full);b=dump(delta)
        sizes.append({'job_id':row['job_id'],'call_index':row['call_index'],'original_chars':len(a),'delta_chars':len(b),'original_tokens_estimate':token_estimate(a),'delta_tokens_estimate':token_estimate(b)})
        if full.get('open_ids') or full.get('work_results') is None:continue
        req=copy.deepcopy(row['request_json'])
        req['prompt']=schema.delta_prompt(req['prompt']);req['schema']=schema.delta_schema(req['schema'])
        # Reserve all output, including reasoning; estimate input conservatively from UTF-8 bytes.
        original_request=row['request_json']
        added_prompt=max(0,len(req['prompt'].encode('utf-8'))-len(original_request['prompt'].encode('utf-8')))
        added_schema=max(0,len(dump(req['schema']).encode('utf-8'))-len(dump(original_request['schema']).encode('utf-8')))
        input_est=row['reference_usage'].get('input_tokens',0)+added_prompt+added_schema+4096
        output_cap=max(4096,token_estimate(b)+2048)
        prepared.append({ 'job_id':row['job_id'],'call_index':row['call_index'],'replay_id':str(row['job_id'])+':'+str(row['call_index'])+':delta','request_json':{**req,'model':'gpt-6.1-sol','max_tokens':output_cap},'obs_in':obs,'work':work,'reference_full':full,'reference_schema':row['request_json']['schema'],'reference_request_json':row['request_json'],'reference_usage':row['reference_usage'],'input_tokens_estimate':input_est,'max_output_tokens':output_cap,'original_chars':len(a),'delta_chars':len(b),'reserved_usd':(input_est*2.5+output_cap*10)/1000000})
    prepared.sort(key=lambda row:row['original_chars'])
    selected=[]
    windows=(('small',lambda n:n<2000),('medium',lambda n:4500<=n<=12000),('large',lambda n:n>20000))
    for name,predicate in windows:
        group=[row for row in prepared if predicate(row['original_chars'])]
        candidates=sorted(group,key=lambda row:row['reserved_usd'])[:2]
        for row in candidates:row['size_group']=name
        selected.extend(candidates)
    selector_reservation=sum(row['reserved_usd'] for row in selected)
    # Bind the reported reservation to the exact future harness serialization.
    replay=helper('replay_delta')
    reservation=sum(replay.estimate(row)['reserved_micro_usd'] for row in selected)/1000000
    if len(selected)!=6:raise ValueError('six-call selection unavailable')
    original=[x['original_chars'] for x in sizes];deltas=[x['delta_chars'] for x in sizes]
    ot=[x['original_tokens_estimate'] for x in sizes];dt=[x['delta_tokens_estimate'] for x in sizes]
    largest=sizes[max(range(len(sizes)),key=lambda i:original[i])]
    measurement={'source_counts':counts,'roundtrip_total':len(rows),'roundtrip_passed':success,'token_estimation':'ceil(compact JSON Unicode characters / 3.6); visible text only, excludes reasoning','original_chars':stats(original),'delta_chars':stats(deltas),'original_tokens_estimate':stats(ot),'delta_tokens_estimate':stats(dt),'largest_original_case':largest,'expected_visible_output_reduction_fraction':1-sum(dt)/sum(ot),'expected_visible_output_savings_usd_at_10_per_million':(sum(ot)-sum(dt))*10/1000000,'reference_real_input_tokens':sum(x['reference_usage'].get('input_tokens',0) for x in rows),'reference_real_output_tokens_including_reasoning':sum(x['reference_usage'].get('output_tokens',0) for x in rows),'reference_real_reasoning_tokens':sum(x['reference_usage'].get('output_tokens_details',{}).get('reasoning_tokens',0) for x in rows),'replay_selected':len(selected),'replay_reserved_usd':reservation,'replay_max_usd':1.0,'replay_budget_blocked':reservation>1.0,'input_estimation_assumption':'observed reference input tokens plus positive UTF8 byte increases from delta prompt and schema, plus 4096 margin; no assumed cache hit','selection_rule':'fixed visible JSON character windows: small <2000, medium 4500..12000, large >20000; two lowest conservative reservation cases per window','selection_limit':'budget sample spans these fixed sizes; does not cover global upper tercile or maximum 20000-output-token cases and proves no model reliability' }
    measurement['replay_selector_proxy_usd']=selector_reservation
    return measurement,selected

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--archive',type=Path,default=DEFAULT_ARCHIVE);ap.add_argument('--scratch',type=Path,default=DEFAULT_SCRATCH);ap.add_argument('--extract-only',action='store_true');args=ap.parse_args()
    data=ROOT/'data';data.mkdir(exist_ok=True)
    if args.extract_only or not (data/'all_calls.jsonl').exists():
        rows=[]
        with (data/'all_calls.jsonl').open('w') as handle:
            for row,counts in extract(args.archive,args.scratch):handle.write(dump(row)+'\n');rows.append(row)
        counts=extract.counts
        (data/'source_counts.json').write_text(dump(counts)+'\n')
    else:
        rows=[json.loads(line) for line in (data/'all_calls.jsonl').open()];counts=json.loads((data/'source_counts.json').read_text())
    if args.extract_only:print(dump(counts));return
    measurement,selected=measure_and_select(rows,counts)
    (ROOT/'measurements.json').write_text(json.dumps(measurement,ensure_ascii=False,indent=2)+'\n')
    with (ROOT/'selected_requests.jsonl').open('w') as handle:
        for row in selected:handle.write(dump(row)+'\n')
    print(dump({'roundtrip_passed':measurement['roundtrip_passed'],'roundtrip_total':measurement['roundtrip_total'],'replay_selected':len(selected),'replay_reserved_usd':measurement['replay_reserved_usd']}))
if __name__=='__main__':main()
