from copy import deepcopy
from pathlib import Path
from memory import connect,overview,fingerprint
from test_generation_review import entry
from test_memory import observation,proposal
from durable_calls import encode,sha
from journal_projection import prepare_source

def configure(store):
 db=connect(':memory:')
 first='Gleb: Nach Freigabe sende ich morgen den Bericht.\nGleb: Auch die Kurse müssen vorliegen.'
 old=entry(db,'synthetic:conditional',first,'2026-07-14',observation(work_state='waiting',condition_text='Nach Freigabe\nAuch die Kurse müssen vorliegen',quotes=first.splitlines()))
 wid=overview(db)['waiting_dependencies'][0]['id']
 later='Alice: Die nächste Besprechung findet im September statt.'
 future=entry(db,'synthetic:later',later,'2026-07-16',observation(kind='fact',commitment_strength='not_applicable',owner=None,due_text=None,quotes=[later],title='Späteres Protokoll',claim=later))
 body='Gleb: Die Freigabe und die Kurse sind jetzt beide da. Den Bericht muss ich noch senden.'
 meta=encode({'source_id':'synthetic:future','event_date':'2026-07-15','title':'Verspätete Freigabemeldung','body_sha256':sha(body),'export_sha256':sha(body),'body_offset_characters':0})
 store.document.update(id=sha('synthetic:future:'+meta),event_date='2026-07-15',title='Verspätete Freigabemeldung',body=body,export=body,body_hash=sha(body),export_hash=sha(body),metadata_json=meta)
 store.job.update(id=sha('synthetic:future:'+sha(body)),document_id=store.document['id'],event_date='2026-07-15',reason='out_of_order',expected_revision=2)
 store.journal=[{**e,'source_version':e['source']['id']} for e in (old,future)];store.revision=2
 store.job['prepared_payload']={'proposal':proposal(observation(kind='status',commitment_strength='not_applicable',title='Voraussetzungen jetzt eingetreten',claim=body,owner=None,due_text=None,condition_text=None,work_state='waiting',update='progress',update_target=wid,quotes=[body],state_quotes=[]))}
 db.close()
 Path('/tmp/dashboard-condition-ui-target.json').write_text(__import__('json').dumps({'work_id':wid,'job_id':store.job['id']}))
