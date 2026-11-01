"""Do not infer a causal ordering from sorted filenames on the same day."""
from memory import overview

def guard(db, meeting, proposal):
    day=meeting['meeting_date'][:10]
    state=overview(db,day)
    unordered={item['id'] for key in ('personal','waiting','waiting_dependencies','completed') for item in state[key] if item['last_changed']==day}
    for item in proposal['observations']:
        if item.get('update_target') in unordered and item.get('update','none')!='none':
            item['unordered_same_day_proposal']={'update':item['update'],'action_uncertainty':item.get('action_uncertainty')}
            item['update']='none'
            item['action_uncertainty']='Die Reihenfolge der Quellen am selben Tag ist nicht belegt; der vorgeschlagene Zustandswechsel benötigt Prüfung.'
            item['required_review']=True
    return proposal
