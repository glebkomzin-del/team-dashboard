"""Versioned contracts for source extraction and evidence-based alignment."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).parent

def extraction_schema(evidence_ids=None):
    from future_summary import schema
    value = schema(json.loads((ROOT/'evaluation/schema-v9.json').read_text()))
    item = value['properties']['observations']['items']
    extra = {
        'subject': {'type': 'string'},
        'search_keywords': {'type': 'array', 'maxItems': 8, 'items': {'type': 'string'}},
        'assignment_score': {'type': 'integer', 'enum': [0, 1, 2]},
        'change_score': {'type': 'integer', 'enum': [0, 1, 2]},
        'confidence_reason': {'type': 'string'},
    }
    item['properties'].update(extra)
    item['required'].extend(extra)
    value['properties']['search_queries'] = {'type': 'array', 'items': {
        'type': 'object', 'additionalProperties': False,
        'properties': {'text': {'type': 'string'}, 'evidence_ids': {'type': 'array', 'items': {'type': 'string'}}},
        'required': ['text', 'evidence_ids']}}
    value['required'].append('search_queries')
    if evidence_ids is not None:
        allowed=sorted(set(evidence_ids))
        value.setdefault('$defs',{})['evidence_id']={'type':'string','enum':allowed}
        reference={'$ref':'#/$defs/evidence_id'}
        for key in ('evidence_ids','state_evidence_ids'):
            item['properties'][key]['items']=reference
        value['properties']['meeting_summary']['items']['properties']['evidence_ids']['items']=reference
        value['properties']['meeting_display_title']['anyOf'][1]['properties']['evidence_ids']['items']=reference
        value['properties']['search_queries']['items']['properties']['evidence_ids']['items']=reference
    return value

def alignment_schema(*, work_ids=None, matter_ids=None, source_indices=None):
    value = extraction_schema()
    for key in ('meeting_summary', 'meeting_display_title', 'search_queries'):
        del value['properties'][key]
        value['required'].remove(key)
    item = value['properties']['observations']['items']
    item['properties']['source_index'] = {'type': 'integer', 'minimum': 0}
    item['required'].append('source_index')
    for key,values in (('update_target',work_ids),('matter_id',matter_ids)):
        if values is not None:item['properties'][key]['enum']=[None,*sorted(set(values))]
    if source_indices is not None:item['properties']['source_index']['enum']=sorted(set(source_indices))
    return value

def lifecycle_schema(work_ids=None):
    import reconcile
    fields = copy.deepcopy(reconcile.FIELDS)
    fields['action']['enum'].remove('unchanged')
    for key in ('assignment_score', 'change_score'):
        fields[key] = {'type': 'integer', 'enum': [0, 1, 2]}
    if work_ids is not None:
        del fields['work_id']
        value={'anyOf':[{'type':'string','enum':['unchanged']},
                         {'type':'object','additionalProperties':False,'properties':fields,'required':list(fields)}]}
        slots={str(i):{'$ref':'#/$defs/lifecycle_result'} for i in range(len(work_ids))}
        return {'type':'object','additionalProperties':False,'required':['results'],'$defs':{'lifecycle_result':value},
                'properties':{'results':{'type':'object','additionalProperties':False,'properties':slots,'required':list(slots)}}}
    return {'type': 'object', 'additionalProperties': False, 'required': ['unchanged', 'changes'],
        'properties': {
            'unchanged': {'type': 'array', 'items': {'type': 'string'}},
            'changes': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                'properties': fields, 'required': list(fields)}}}}
