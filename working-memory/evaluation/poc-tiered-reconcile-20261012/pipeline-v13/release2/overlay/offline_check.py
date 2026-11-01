"""Stdlib-only container checks; python3 -I -B offline_check.py [--local]."""
import argparse
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
MODULES = ('canonical_worker.py','compact_reconcile.py','hybrid_schema.py','hybrid_pipeline.py','candidate_filter.py','delta_codec.py')
PAYLOADS = (*MODULES, 'offline_check.py', 'default_contract.json')
MODEL = 'gpt-6.1-sol'

def require(value):
    if not value: raise AssertionError('offline check')

def no_network(event,args):
    if event.startswith(('socket.','subprocess.','os.system','os.exec','os.spawn')):
        raise RuntimeError('offline restriction')

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def fixture():
    text='Synthetic speaker: Synthetic status.'
    obs=dict(matter='Synthetic',matter_id=None,kind='fact',title='Synthetic status',claim=text,
        owner=None,commitment_strength='not_applicable',due_text=None,update_target=None,update='none',
        uncertainty=None,required_review=False,evidence_ids=['U0001'],action_uncertainty=None,
        condition_text=None,work_state='not_applicable',state_evidence_ids=[],subject='Synthetic',
        search_keywords=[],assignment_score=2,change_score=2,confidence_reason='Synthetic evidence')
    work=[dict(id='synthetic-work',title='Synthetic work',claim='Synthetic prior task',last_changed='2026-10-12',parent_matter_id=None)]
    full={'open_ids':[],'observations':[{**obs,'source_index':0}],'work_results':{'0':'unchanged'},'coverage_notes':[]}
    return text,obs,work,full

def provider_request(provider,prompt,schema,limit):
    body={'id':'synthetic','model':MODEL,'status':'completed','service_tier':'default',
          'usage':{'input_tokens':1,'output_tokens':1},'output':[{'type':'message','role':'assistant','status':'completed',
          'content':[{'type':'output_text','text':'{}'}]}]}
    class Stream:
        def __enter__(self):return self
        def __exit__(self,*args):return False
        def __iter__(self):return iter([('data: '+json.dumps({'type':'response.completed','response':body})+'\n').encode(),b'\n'])
    with patch.object(provider,'api_key',return_value='synthetic'), patch.object(provider.urllib.request,'urlopen',return_value=Stream()) as transport:
        provider.request(prompt,MODEL,max_tokens=limit,schema=schema)
    require(transport.call_count==1)
    return transport.call_args.args[0].data.decode('utf-8')

def contract(compact,schema,provider,*,work_override=None):
    import processor
    import hybrid_pipeline
    text,obs,work,full=fixture()
    if work_override is not None:
        work=work_override
        full['work_results']={str(i):'unchanged' for i in range(len(work))}
    originals=processor.units(text)
    meeting={'title':'Synthetic meeting','meeting_date':'2026-10-13','raw_transcript':text}
    rules=(schema.ROOT/'evaluation/prompt-v9.txt').read_text()
    base='\nMeeting: '+meeting['title']+'\nDatum: 2026-10-13\nVollständiges Original:\n'+hybrid_pipeline.encode(originals)
    captures=[]
    def stage(name,prompt,shape,check,limit):
        captures.append({'name':name,'prompt':prompt,'schema':json.dumps(shape,ensure_ascii=False),
                         'limit':limit,'request':provider_request(provider,prompt,shape,limit)})
        value=copy.deepcopy(full)
        if os.environ.get('DASHBOARD_DELTA_OUTPUT')=='1':
            from delta_codec import to_delta
            value=to_delta(value,[obs],work)
        return check(value)
    compact.run(raw={'observations':[obs],'coverage_notes':[]},work=work,hits={},query_hits={},originals=originals,
        meeting=meeting,known={'synthetic-work'},stage=stage,rules=rules,base=base,confidence_rules=hybrid_pipeline.CONFIDENCE)
    # Extraction and gate schemas/instructions must remain exactly the production ones.
    extraction=schema.extraction_schema()
    gate=json.loads((schema.ROOT/'evaluation/work-gate-schema-v9.json').read_text())
    return {'compact':captures,'extraction_schema':json.dumps(extraction,ensure_ascii=False),
        'extraction_instruction':hybrid_pipeline.EXTRACTION,'confidence':hybrid_pipeline.CONFIDENCE,
        'gate_instruction':(schema.ROOT/'evaluation/work-gate-prompt-v9.txt').read_text()+'\n'+compact.GATE_RULES,
        'gate_schema':json.dumps(gate,ensure_ascii=False),
        'extraction_request':provider_request(provider,'synthetic',extraction,24000),
        'gate_request':provider_request(provider,'synthetic',gate,12000)}

def independent_version(directory):
    # Read the actual fixed fingerprint lists without invoking their functions.
    hybrid_tree=ast.parse((directory/'hybrid_pipeline.py').read_text())
    function=next(n for n in hybrid_tree.body if isinstance(n,ast.FunctionDef) and n.name=='version')
    names=ast.literal_eval(next(n.value for n in function.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='names' for t in n.targets)))
    for node in function.body:
        if isinstance(node,ast.If) and isinstance(node.test,ast.Name) and node.test.id=='compact':
            for child in node.body:
                if isinstance(child,ast.AugAssign) and isinstance(child.target,ast.Name) and child.target.id=='names':names+=ast.literal_eval(child.value)
    tree=ast.parse((directory/'canonical_worker.py').read_text())
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='pipeline_version')
    generator=next(n for n in ast.walk(function) if isinstance(n,ast.GeneratorExp))
    canonical_names=ast.literal_eval(generator.generators[0].iter)
    digest=lambda paths:hashlib.sha256(''.join((directory/name).read_text() for name in paths).encode()).hexdigest()[:16]
    return 'v11:compact1:gate1:'+MODEL+':'+digest(names)+':canonical1:'+digest(canonical_names)

def check_delta():
    from delta_codec import to_delta,from_delta,equal
    _,obs,work,full=fixture()
    delta=to_delta(full,[obs],work)
    require(equal(full,from_delta(delta,[obs],work)))
    require(delta['observations'][0]['decision']=={'matter_id':None,'update_target':None,'update':'none'})
    for invalid in ('decision','coverage','overlap','observation'):
        broken=copy.deepcopy(delta)
        if invalid=='decision':del broken['observations'][0]['decision']['matter_id']
        if invalid=='coverage':broken['unchanged_work_indices']=[]
        if invalid=='overlap':broken['work_results']=[{'work_index':'0','result':{'action':'progress'}}]
        if invalid=='observation':broken['observations']=[]
        try:from_delta(broken,[obs],work)
        except ValueError:pass
        else:raise AssertionError('delta gate')
    expansion={'open_ids':['H0'],'observations':[],'work_results':None,'coverage_notes':[]}
    require(equal(expansion,from_delta(to_delta(expansion,[obs],work),[obs],work)))

def check_filter():
    from candidate_filter import filter_work
    obs={'title':'Synthetic','subject':'','search_keywords':[]}
    work=[{'id':'age30','last_changed':'2026-09-13'},{'id':'age31','last_changed':'2026-09-12'},
          {'id':'rank4','last_changed':'2026-01-01'},{'id':'rank5','last_changed':'2026-01-01'},
          {'id':'exact','last_changed':'2026-01-01'},{'id':'unknown'}]
    hits={'Synthetic ':[{'kind':'work','target_id':str(i)} for i in range(4)]+[{'kind':'work','target_id':'rank4'},{'kind':'work','target_id':'rank5'}]}
    kept,dropped,_=filter_work(work,hits,[obs],'2026-10-13',{'exact'})
    require([w['id'] for w in kept]==['age30','rank4','exact','unknown'])
    require([w['id'] for w in dropped]==['age31','rank5'])

def check_diagnostic(worker):
    from memory import ValidationError
    output=io.StringIO()
    with contextlib.redirect_stderr(output):worker.job_failed_diagnostic('abcdefgh123','validation_failed',ValidationError('Invalid\n coverage: SECRET'))
    require(len(output.getvalue().splitlines())==1)
    value=json.loads(output.getvalue())
    require(value=={'event':'job_failed','job':'abcdefgh','reason':'validation_failed','error_type':'ValidationError','stage':None,'message':'Invalid coverage'})

def run_checks(directory,expected):
    import canonical_worker as worker
    import compact_reconcile as compact
    import hybrid_schema as schema
    import hybrid_pipeline as pipeline
    import openai_provider as provider
    checks=[]
    def syntax():
        for name in (*MODULES,'offline_check.py'):compile((directory/name).read_bytes(),name,'exec')
    checks.append(('syntax',syntax))
    def identity():
        actual=worker.pipeline_version(MODEL)
        require(actual==independent_version(directory)==expected['pipeline_version'])
    checks.append(('version',identity))
    checks.append(('default_prompt_schema_request',lambda:require(contract(compact,schema,provider)==expected['contract'])))
    checks.append(('diagnostic',lambda:check_diagnostic(worker)))
    checks.append(('delta',check_delta));checks.append(('filter',check_filter))
    def combination():
        from candidate_filter import filter_work
        _,obs,work,_=fixture()
        candidates=[{'id':'synthetic-dropped','last_changed':'2026-01-01'},*work]
        kept,dropped,_=filter_work(candidates,{},[obs],'2026-10-13',set())
        require(kept==work and len(dropped)==1)
        with patch.dict(os.environ,{'DASHBOARD_DELTA_OUTPUT':'1','DASHBOARD_HOTSET_FILTER':'1'}):
            value=contract(compact,schema,provider,work_override=kept)
        require('synthetic-dropped' not in value['compact'][0]['prompt'])
        shape=json.loads(value['compact'][0]['schema'])
        require('decision' in shape['properties']['observations']['items']['required'])
    checks.append(('delta_filter_combination',combination))
    def manifest():
        value=json.loads((directory/'build-manifest.json').read_text())
        for name in PAYLOADS:require(value[name]==hashlib.sha256((directory/name).read_bytes()).hexdigest())
    checks.append(('manifest',manifest))
    def switches():
        base=worker.pipeline_version(MODEL)
        for env,suffix in (({'DASHBOARD_DELTA_OUTPUT':'1'},':delta2'),
            ({'DASHBOARD_HOTSET_FILTER':'1'},':hotset1:age=30:rank=5'),
            ({'DASHBOARD_HOTSET_FILTER':'1','DASHBOARD_DELTA_OUTPUT':'1'},':hotset1:age=30:rank=5:delta2')):
            with patch.dict(os.environ,env):
                value=pipeline.version(MODEL,compact=True)
                # Canonical suffix follows features; compare the whole derived identity.
                require(worker.pipeline_version(MODEL)==value+base[base.index(':canonical1:'):])
                require(value.endswith(suffix))
    checks.append(('switch_versions',switches))
    passed=0
    for name,check in checks:
        try:check()
        except Exception:print('fail '+name)
        else:passed+=1;print('ok '+name)
    print(str(passed)+'/'+str(len(checks)))
    return 0 if passed==len(checks) else 1

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--local',action='store_true');args=parser.parse_args(argv)
    with contextlib.ExitStack() as stack:
        if args.local:
            sys.path.insert(0,str(ROOT.parent))
            from local_support import configure,sources
            configure();stack.enter_context(sources())
        else:
            sys.path.insert(0,'/app')  # -I intentionally ignores PYTHONPATH.
            sys.addaudithook(no_network)
        stack.enter_context(patch.dict(os.environ,{'MEMORY_PROMPT_VERSION':'v11','MEMORY_ACTION_GATE':'1',
            'DASHBOARD_DELTA_OUTPUT':'0','DASHBOARD_HOTSET_FILTER':'0','DASHBOARD_SERVICE_TIER':'default',
            'DASHBOARD_HOTSET_AGE_DAYS':'30','DASHBOARD_HOTSET_RANK':'5'}))
        expected=json.loads((ROOT/'default_contract.json').read_text())
        try:return run_checks(ROOT,expected)
        except Exception:print('fail imports/setup');return 1

if __name__=='__main__':raise SystemExit(main())
