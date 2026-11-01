"""Select final used filtered calls plus three original-request noise controls offline.
Cost heuristic reproduced from ../model-replay/replay.py:estimate (chars/3.6).
"""
import argparse
import copy
import importlib.util
import json
from decimal import Decimal, ROUND_CEILING
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('filtered_build_selection',ROOT/'build_filtered_requests.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)


def estimate(record):
    source=record['request_json']
    characters=len(source['prompt'])+len(json.dumps(source['schema'],ensure_ascii=False))
    tokens=int((Decimal(characters)/Decimal('3.6')).to_integral_value(rounding=ROUND_CEILING))
    allowance=source.get('max_tokens',16000)
    if type(allowance) is not int or not 1<=allowance<=128000:raise ValueError('Invalid max_tokens')
    return build.common.usage_micro_usd({'input_tokens':tokens,
        'input_tokens_details':{'cache_write_tokens':tokens},
        'output_tokens':max(16000,allowance)}, 'gpt-6.1-sol')


def make_control(record):
    out=copy.deepcopy(record)
    out['request_json']=copy.deepcopy(out['original_request_json'])
    out['replay_variant']='control'
    out['replay_id']=f"{out['job_id']}:{out['call_index']}:control"
    meta=out['filter_metadata']
    meta['kept_aliases']=list(meta['alias_work_indices'])
    meta['removed_aliases']=[]
    meta['candidates_after']=meta['candidates_before']
    meta['prompt_characters_after']=meta['prompt_characters_before']
    return out


def select(records,filtered_budget=2500000,control_budget=build.common.CONTROL_CAP_MICRO_USD,mandatory_prefix='4e7b6e03'):
    for cap in (filtered_budget, control_budget):
        if type(cap) is not int or cap <= 0:
            raise ValueError('Budgets must be positive integer microUSD')
    eligible=[r for r in records if build.is_final_used(dict(r,request_json=r['original_request_json']))]
    ordered=sorted(eligible,key=lambda r:(estimate(r),r['job_id'],r['call_index']))
    mandatory=[r for r in ordered if r['job_id'].startswith(mandatory_prefix)]
    if len(mandatory)!=1:raise ValueError('Mandatory call must exist exactly once')
    # Reserve mandatory before optional cheap calls; final output stays cost-sorted.
    chosen=list(mandatory);reserved=estimate(mandatory[0])
    if reserved>filtered_budget:raise ValueError('Mandatory call exceeds filtered budget')
    for r in ordered:
        if r is mandatory[0]:continue
        cost=estimate(r)
        if reserved+cost<=filtered_budget:
            chosen.append(r);reserved+=cost
    chosen.sort(key=lambda r:(estimate(r),r['job_id'],r['call_index']))
    controls=[make_control(r) for r in chosen[:3]]
    if len(controls)!=3:
        raise ValueError('Three original-request controls required')
    control_required=sum(estimate(r) for r in controls)
    feasible=control_required<=control_budget
    budget={'filtered_cap_micro_usd':filtered_budget,'control_cap_micro_usd':control_budget,'feasible':feasible}
    for r in chosen+controls:r['selection_budget']=dict(budget)
    for r in chosen+controls:r['estimated_micro_usd']=estimate(r)
    summary={'eligible_calls':len(eligible),'filtered_calls':len(chosen),'control_calls':len(controls),
             'filtered_upper_micro_usd':reserved,'control_upper_micro_usd':sum(estimate(r) for r in controls),
             'total_upper_micro_usd':reserved+sum(estimate(r) for r in controls),
             'filtered_budget_micro_usd':filtered_budget,'control_budget_micro_usd':control_budget,
             'mandatory_included':True,'feasible':feasible,
             'infeasible_control_budget':not feasible,
             'minimum_possible_control_micro_usd':sum(sorted(estimate(make_control(r)) for r in eligible)[:3]),
             'candidates_before':sum(r['filter_metadata']['candidates_before'] for r in chosen),
             'candidates_after':sum(r['filter_metadata']['candidates_after'] for r in chosen),
             'prompt_characters_before':sum(r['filter_metadata']['prompt_characters_before'] for r in chosen),
             'prompt_characters_after':sum(r['filter_metadata']['prompt_characters_after'] for r in chosen),
             'estimation':'ceil((prompt_chars+schema_chars)/3.6), cache-write input at 2.50, fully reserved output; heuristic not tokenizer bound'}
    return chosen+controls,summary


def remaining_selection(records, skip_done, max_micro_usd=3200000):
    """Keep the original controls; prune the largest remaining filtered calls."""
    if type(max_micro_usd) is not int or max_micro_usd <= 0:
        raise ValueError('Invalid remaining budget')
    done=build.common.completed_replay_ids(skip_done)
    selected=[];seen=set();keys=set();skipped=0
    for record in records:
        key=build.common.replay_identity(record)
        rid=record['replay_id']
        if rid in seen or key in keys:raise ValueError('Duplicate selection identity')
        seen.add(rid);keys.add(key)
        if rid in done:skipped+=1
        else:selected.append(copy.deepcopy(record))
    if sum(r['replay_variant']=='control' for r in records)!=3:
        raise ValueError('Original plan must contain three controls')
    before=sum(estimate(r) for r in selected)
    removed=0
    while (sum(estimate(r) for r in selected)>max_micro_usd or
           sum(estimate(r) for r in selected if r['replay_variant']=='filtered')>2500000):
        filtered=[r for r in selected if r['replay_variant']=='filtered']
        if not filtered:break
        largest=max(filtered,key=lambda r:(estimate(r),r['job_id'],r['call_index']))
        selected.remove(largest);removed+=1
    totals={v:sum(estimate(r) for r in selected if r['replay_variant']==v) for v in ('filtered','control')}
    feasible=(sum(totals.values())<=max_micro_usd and totals['filtered']<=2500000
              and totals['control']<=build.common.CONTROL_CAP_MICRO_USD)
    for r in selected:
        r['estimated_micro_usd']=estimate(r)
        r['selection_budget']={'filtered_cap_micro_usd':2500000,
            'control_cap_micro_usd':build.common.CONTROL_CAP_MICRO_USD,'feasible':feasible}
    return selected,{'calls':len(selected),'filtered_calls':sum(r['replay_variant']=='filtered' for r in selected),
        'control_calls':sum(r['replay_variant']=='control' for r in selected),'skipped_done_calls':skipped,
        'removed_largest_filtered_calls':removed,'before_reduction_upper_micro_usd':before,
        'filtered_upper_micro_usd':totals['filtered'],'control_upper_micro_usd':totals['control'],
        'total_upper_micro_usd':sum(totals.values()),'max_micro_usd':max_micro_usd,'feasible':feasible,
        'estimation':'chars/3.6 heuristic, all input at cache-write 2.50, full output at 10.00'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--requests',type=Path,default=ROOT/'filtered_requests.jsonl')
    p.add_argument('--filtered-max-usd',type=Decimal,default=Decimal('2.50'))
    p.add_argument('--control-max-usd',type=Decimal,default=Decimal(build.common.CONTROL_CAP_MICRO_USD)/Decimal(1000000))
    p.add_argument('--skip-done',type=Path,nargs='+',action='append',default=[])
    p.add_argument('--max-usd',type=Decimal,default=Decimal('3.20'))
    p.add_argument('--output',type=Path)
    p.add_argument('--summary',type=Path)
    a=p.parse_args()
    if any(not v.is_finite() or v <= 0 or v*1000000!=(v*1000000).to_integral_value()
           for v in (a.filtered_max_usd,a.control_max_usd,a.max_usd)):
        p.error('Budgets must be positive finite USD amounts')
    records=list(build.common.read_jsonl(a.requests))
    if a.skip_done:
        selected,summary=remaining_selection(records,[path for group in a.skip_done for path in group],int(a.max_usd*1000000))
        suffix='-run2'
    else:
        selected,summary=select(records,int(a.filtered_max_usd*1000000),int(a.control_max_usd*1000000))
        suffix=''
    build.write_jsonl(build.common.output_path(a.output or ROOT/('selected_requests'+suffix+'.jsonl')),selected)
    build.common.output_path(a.summary or ROOT/('selection-summary'+suffix+'.json')).write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))
    return 0 if summary['feasible'] else 2

if __name__=='__main__':raise SystemExit(main())
