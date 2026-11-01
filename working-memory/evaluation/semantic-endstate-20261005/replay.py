"""Private, offline replay of one saved source; never calls a provider or writes a database."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

from compact_reconcile import GATE_RULES
from future_summary import from_value
from hybrid_index import current_source_documents, encode
from hybrid_pipeline import apply_endstate, confidence, decoded, guard_gate_escalation
from hybrid_pipeline import resolve_v10
from memory import ValidationError, validate
from processor import apply_work_gate, units


def sha(value):return hashlib.sha256(value.encode()).hexdigest()


def response(call):return decoded(json.loads(call['response']))


def inputs(path):
    data=json.loads(Path(path).read_text())
    document=data['document'];calls=data['calls']
    if [row['index'] for row in calls]!=list(range(23)):
        raise ValidationError('Saved call ledger is incomplete')
    original=units(document['body'])
    extraction=response(calls[0]);aligned=response(calls[18]);old_gate=response(calls[19])
    if [row['source_index'] for row in aligned['observations']]!=list(range(len(extraction['observations']))):
        raise ValidationError('Saved alignment indices changed')
    proposal=resolve_v10(aligned,original)
    if any(row.get('update_target') for row in proposal['observations']):
        raise ValidationError('Replay needs an explicit matched-work catalog')
    return document,calls,original,extraction,proposal,old_gate


def prompt_for(document,original,extraction,proposal):
    candidates=[{'index':i,**row} for i,row in enumerate(proposal['observations']) if row['kind']=='commitment' or row.get('update')!='none']
    meeting={'title':document['title'],'meeting_date':document['event_date'],'raw_transcript':document['body']}
    base='\nMeeting: '+meeting['title']+'\nDatum: '+meeting['meeting_date'][:10]+'\nVollständiges Original:\n'+encode(original)
    rules=(ROOT/'evaluation/work-gate-prompt-v9.txt').read_text()+'\n'+(ROOT/'evaluation/endstate-gate-prompt-v1.txt').read_text()+'\n'+GATE_RULES
    return (rules+'\nKandidaten:\n'+encode(candidates)+'\nAlle aktuellen Beobachtungen:\n'
            +encode([{'index':i,**row} for i,row in enumerate(proposal['observations'])])
            +'\nVorläufige Zusammenfassung:\n'+encode(extraction['meeting_summary'])
            +'\nBestehende Arbeit:\n[]'+base)


def check(document,original,extraction,proposal,gate):
    checked=guard_gate_escalation(proposal,apply_work_gate(copy.deepcopy(proposal),gate['verdicts'],original))
    final=apply_endstate(checked,extraction,gate,original)
    for row in checked['observations']:
        existing={(span['start'],span['end']) for span in row['source_spans']}
        for evidence_id in row.get('work_gate',{}).get('evidence_ids',[]):
            unit=original[evidence_id]
            if (unit['start'],unit['end']) not in existing:
                row['source_spans'].append({'start':unit['start'],'end':unit['end'],'quote':unit['text']})
    confidence(checked)
    projected=validate(checked,document['body'],set())
    final_raw={**extraction,'meeting_summary':final}
    summary=from_value(final_raw,original,document['title'],document['body'])
    meeting={'source_id':document['source_id'],'meeting_date':document['event_date'],
             'title':document['title'],'raw_transcript':document['body']}
    indexed='\n'.join(row['text'] for row in current_source_documents(meeting,final_raw) if row['kind']=='summary')
    # The saved upload and Caroline commitments are already pending review.
    # Preserve that accepted input state rather than clearing it to create work.
    retained=('kind','title','claim','owner','commitment_strength','due_text',
              'condition_text','work_state','required_review')
    independent=all(checked['observations'][i].get(k)==proposal['observations'][i].get(k)
                    for i in (0,2) for k in retained)
    independent=independent and all(checked['observations'][i]['kind']=='commitment'
                    and all(q in checked['observations'][i]['quotes'] for q in proposal['observations'][i]['quotes'])
                    for i in (0,2))
    withdrawal=checked['observations'][1].get('endstate',{})
    contradictory=gate['final_summary'][2]
    if (checked['observations'][1]['kind']!='decision' or projected[1]['creates_work']
            or not independent or withdrawal.get('status')!='withdrawn'
            or 'U0134' not in withdrawal.get('later_evidence_ids',[])
            or not set(withdrawal.get('earlier_evidence_ids',[]))&{'U0085','U0088'}
            or contradictory['status']!='corrected' or 'U0134' not in final[2]['evidence_ids']
            or final[2]==extraction['meeting_summary'][2]
            or summary['ai_summary']!=indexed.replace('\n','\n\n')):
        raise ValidationError('Endstate reference criteria not met')
    return {'passed':True,'observation_count':len(projected),'creates_work_indices':[i for i,row in enumerate(projected) if row['creates_work']],
             'withdrawn_index':1,'independent_commitment_indices':[0,2],
             'preserved_review_indices':[i for i in (0,2) if checked['observations'][i].get('required_review')],
             'semantic_original_review_required':True,
             'corrected_summary_indices':[i for i,(a,b) in enumerate(zip(extraction['meeting_summary'],final)) if a!=b],
            'summary_sha256':sha(summary['ai_summary']),'index_summary_sha256':sha(indexed)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',required=True,help='Private JSON from the existing 23-call ledger')
    parser.add_argument('--out',required=True,help='Private directory for review input and result')
    parser.add_argument('--gate-file',help='One later real gate response, JSON envelope or value')
    args=parser.parse_args()
    out=Path(args.out);out.mkdir(mode=0o700,parents=True,exist_ok=True)
    document,calls,original,extraction,proposal,old_gate=inputs(args.input)
    prompt=prompt_for(document,original,extraction,proposal)
    schema=(ROOT/'evaluation/endstate-gate-schema-v1.json').read_text()
    (out/'prompt.txt').write_text(prompt)
    (out/'schema.json').write_text(schema)
    binding={'source_body_sha256':sha(document['body']),'saved_calls':len(calls),
             'saved_ledger_micro_usd':sum(int(c['actual_micro_usd'] or 0) for c in calls),
             'extraction_sha256':sha(encode(extraction)),'alignment_sha256':sha(encode(proposal)),
             'old_gate_sha256':sha(encode(old_gate)),'prompt_sha256':sha(prompt),'schema_sha256':sha(schema),
             'expected':{'withdrawn_observation_index':1,'independent_commitment_indices':[0,2],
                         'preserve_existing_required_review':True,'semantic_original_review_required':True,
                         'contradictory_summary_index':2}}
    (out/'binding.json').write_text(json.dumps(binding,indent=2)+'\n')
    if args.gate_file:
        value=json.loads(Path(args.gate_file).read_text())
        if 'content' in value:value=decoded(value)
        result=check(document,original,extraction,proposal,value)
        (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,sort_keys=True))
    else:print(json.dumps({'prepared':True,'prompt_sha256':binding['prompt_sha256'],'source_body_sha256':binding['source_body_sha256']}))


if __name__=='__main__':main()
