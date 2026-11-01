"""Experimental action gate: replay actual extracted proposals into a separate projection.

Extraction costs stay in the source DB; gate calls have a separate ledger. This is
not a recall evaluation and cannot recover commitments the extractor omitted.
"""
import argparse,json,time,uuid
from pathlib import Path
from processor import ROOT,units,anthropic,MAX_PROMPT_CHARS,apply_work_gate
from memory import connect,register,claim,apply,overview,ValidationError

SCHEMA={'type':'object','additionalProperties':False,'properties':{'verdicts':{'type':'array','items':{'type':'object','additionalProperties':False,'properties':{'index':{'type':'integer'},'verdict':{'type':'string','enum':['supported','unsupported','ambiguous','already_done']},'reason':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string'}}},'required':['index','verdict','reason','evidence_ids']}}},'required':['verdicts']}

def replay_guarded(source_path,target_path,model='claude-opus-5'):
    if Path(target_path).exists():raise ValueError('Use a new output database')
    source=connect(source_path);target=connect(target_path)
    folder=ROOT/'.local/gate-runs'/uuid.uuid4().hex;folder.mkdir(parents=True)
    for job in source.execute("SELECT j.id AS job_id,j.pipeline,s.* FROM jobs j JOIN source_versions s ON s.id=j.source_version WHERE j.status='applied' ORDER BY s.event_date,s.observed_at"):
        observations=[json.loads(r[0]) for r in source.execute('SELECT data_json FROM observations WHERE job_id=? ORDER BY rowid',(job['job_id'],))]
        originals=units(job['transcript'])
        candidates=[{'index':i,**o} for i,o in enumerate(observations) if o['kind']=='commitment' or o.get('update','none')!='none']
        prompt=(ROOT/'evaluation/work-gate-prompt.txt').read_text()+'\nMeetingdatum: '+job['event_date']+'\nKandidaten (unverbindlich):\n'+json.dumps(candidates,ensure_ascii=False)+'\nBestehende Arbeit:\n'+json.dumps({k:v for k,v in overview(target,job['event_date']).items() if k!='knowledge'},ensure_ascii=False)+'\nVollständiges Original:\n'+json.dumps(originals,ensure_ascii=False)
        if len(prompt)>MAX_PROMPT_CHARS:raise ValidationError('Gate context budget exceeded')
        jid=register(target,source_id=job['source_id'],event_date=job['event_date'],title=job['title'],transcript=job['transcript'],pipeline=job['pipeline'])
        token=claim(target,jid,seconds=600)
        response=anthropic(prompt,model,max_tokens=6000,schema=SCHEMA)
        (folder/(jid+'.json')).write_text(json.dumps(response,ensure_ascii=False,indent=2))
        target.execute('INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,jid,time.time(),model,json.dumps(response.get('usage',{})),response['elapsed_seconds'],'work_gate',json.dumps(response,ensure_ascii=False)))
        if response.get('stop_reason')!='end_turn':raise ValidationError('Gate incomplete: '+str(response.get('error')))
        data=json.loads(''.join(c.get('text','') for c in response['content'] if c['type']=='text'))
        verdicts=data['verdicts'];indices=[v['index'] for v in verdicts]
        if len(indices)!=len(set(indices)) or set(indices)!={c['index'] for c in candidates}:raise ValidationError('Gate coverage mismatch')
        proposal=apply_work_gate({'observations':observations,'coverage_notes':['Original extraction retained; additional action gate.']},verdicts,originals)
        apply(target,jid,token,proposal,model='deterministic-projection',usage={},elapsed=0)
        print(json.dumps({'meeting':job['title'],'verdicts':[{'index':v['index'],'verdict':v['verdict'],'reason':v['reason']} for v in verdicts],'elapsed':response['elapsed_seconds'],'usage':response.get('usage')},ensure_ascii=False),flush=True)
    source.close();target.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('target');a=p.parse_args();replay_guarded(a.source,a.target)
