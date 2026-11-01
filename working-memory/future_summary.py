"""Summary in the existing extraction call; never re-summarize legacy stock."""
import copy
import json
from memory import ValidationError

INSTRUCTION='''
Erstelle zusätzlich meeting_summary als kurze sachliche Zusammenfassung dieses
Meetings. Jeder Absatz braucht evidence_ids aus genau diesem Original. Ergänze
keine Zusagen, Fristen oder Entscheidungen allein aus dem Kontext. Bereits
erledigte Punkte, Bedingungen und Unsicherheit müssen als solche erkennbar sein.
Die Zusammenfassung ist eine Lesefassung; sie erteilt keine Aufgabenfreigabe.

Erstelle außerdem meeting_display_title als kurzen, natürlich lesbaren Titel
zum zentralen Gegenstand oder Ergebnis. Verwende nur Begriffe, die in den
angegebenen evidence_ids ausdrücklich belegt sind. Teilnehmernamen, „Meeting",
„Abstimmung“ oder eine bloße Liste von Stichworten sind kein ausreichender
Titel. Wenn kein einzelner Titel zuverlässig belegt ist, liefere null.
'''

def schema(base):
    value=copy.deepcopy(base)
    value['properties']['meeting_summary']={'type':'array','items':{'type':'object','additionalProperties':False,
        'properties':{'text':{'type':'string'},'evidence_ids':{'type':'array','items':{'type':'string'}}},
        'required':['text','evidence_ids']}}
    value['properties']['meeting_display_title']={'anyOf':[{'type':'null'},{'type':'object','additionalProperties':False,
        'properties':{'text':{'type':'string','minLength':5,'maxLength':120},
                      'evidence_ids':{'type':'array','minItems':1,'maxItems':4,'items':{'type':'string'}}},
        'required':['text','evidence_ids']}]}
    value['required'] += ['meeting_summary','meeting_display_title']
    return value

def from_response(response,originals,title,transcript=None):
    value=json.loads(''.join(c.get('text','') for c in response.get('content',[]) if c.get('type')=='text'))
    return from_value(value,originals,title,transcript)

def from_value(value,originals,title,transcript=None):
    paragraphs=value.get('meeting_summary')
    if not isinstance(paragraphs,list) or not 1<=len(paragraphs)<=12:raise ValidationError('Missing or excessive summary')
    evidence=[];texts=[]
    for p in paragraphs:
        if not isinstance(p,dict) or set(p)!={'text','evidence_ids'} or not isinstance(p['text'],str) or not p['text'].strip():
            raise ValidationError('Invalid summary paragraph')
        ids=p['evidence_ids']
        if not isinstance(ids,list) or not ids or any(not isinstance(i,str) or i not in originals for i in ids):
            raise ValidationError('Summary lacks original evidence')
        texts.append(p['text']);evidence.append({'text':p['text'],'passages':[originals[i] for i in dict.fromkeys(ids)]})
    if sum(map(len,texts))>12000:raise ValidationError('Summary too long')
    from meeting_naming import title_from_response
    transcript = transcript if isinstance(transcript,str) else '\n'.join(row['text'] for row in originals.values())
    display_title=title_from_response(value.get('meeting_display_title'),originals,transcript)
    return {'title':title,'display_title':display_title,'ai_summary':'\n\n'.join(texts),'executive_summary':'','topics':[],'key_decisions':[],
            'participants':[],'summary_evidence':evidence,'link_provenance':{'method':'same_call_source_cited_summary'}}
