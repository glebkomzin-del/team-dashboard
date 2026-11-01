"""Compile explicitly reviewed existing items into a private journal draft.

No network, no model API, no writes to the original archive or production.
Publishing a full generation requires complete coverage; partial previews are
explicitly marked and never qualify as migration completion.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3
from uuid import NAMESPACE_URL,uuid5

from legacy_review import validate_review,original_for,save_private,canonical,digest
from memory import connect,known_work_ids,fingerprint,overview,ValidationError
from journal_projection import prepare_source,apply_saved


def compile_reviews(inventory, review_paths, archive, destination, *, allow_partial=False):
    known={source['source_id']:source for source in inventory['sources']}
    reviews={}
    for path in review_paths:
        review=json.loads(Path(path).read_text())
        if review['source_id'] in reviews:raise ValidationError('Duplicate source review')
        if review['source_id'] not in known:raise ValidationError('Review is outside the retained inventory')
        reviews[review['source_id']]=review
    if not allow_partial and set(reviews)!=set(known):
        raise ValidationError('Full migration requires explicit review of every retained source')
    target=Path(destination)
    target.mkdir(mode=0o700,parents=True,exist_ok=False)
    db=connect(target/'projection.sqlite')
    (target/'projection.sqlite').chmod(0o600)
    batches=[];item_count=0
    try:
        for item in inventory['sources']:
            if item['source_id'] not in reviews:continue
            reviewed=validate_review(item,reviews[item['source_id']],archive,known_work_ids(db,item['event_date']))
            body=original_for(item,archive)
            doc=archive.execute('SELECT observed_at FROM documents WHERE id=?',(item['document_id'],)).fetchone()
            source={'id':fingerprint(item['source_id']+':'+item['body_sha256']),
                    'source_id':item['source_id'],'content_hash':item['body_sha256'],
                    'event_date':item['event_date'],'title':item['title'],'transcript':body,'observed_at':doc['observed_at']}
            payload=prepare_source(db,source,{'observations':reviewed['observations'],
                'coverage_notes':reviews[item['source_id']]['coverage_notes']},
                pipeline='codex-direct-review-v1',model='codex_direct_review',
                matter_links=reviewed['matter_links'] or None,
                provenance={'review_sha256':reviewed['review_sha256'],
                            'inventory_sha256':inventory['inventory_sha256'],
                            'legacy_decisions':reviews[item['source_id']]['decisions'],
                            **({'source_updates':reviews[item['source_id']]['source_updates']}
                               if reviews[item['source_id']].get('source_updates') else {}),
                            **({'item_splits':reviews[item['source_id']]['item_splits']}
                               if reviews[item['source_id']].get('item_splits') else {})})
            apply_saved(db,source,payload)
            command=str(uuid5(NAMESPACE_URL,item['source_id']+':'+reviewed['review_sha256']))
            batches.append({'command_id':command,'kind':'source','source':source,'payload':payload})
            item_count+=reviewed['item_count']
        state=overview(db)
        manifest={'format':'legacy-journal-draft-v1','created_at':datetime.now(timezone.utc).isoformat(),
            'inventory_sha256':inventory['inventory_sha256'],'partial':set(reviews)!=set(known),
            'sources_reviewed':len(reviews),'sources_total':len(known),
            'items_reviewed':item_count,'items_total':inventory['item_count'],
            'observations':len(state['knowledge']),
            'work_counts':{k:len(state[k]) for k in ('personal','waiting_dependencies','waiting','completed','cancelled')},
            'batch_sha256':digest(canonical(batches)),'published':False,'api_calls':0,
            'requires_fresh_production_row_check':True}
        save_private(target/'batches.json',batches);save_private(target/'manifest.json',manifest)
        return manifest
    finally:db.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory',required=True);parser.add_argument('--archive',required=True)
    parser.add_argument('--output',required=True);parser.add_argument('--allow-partial-preview',action='store_true')
    parser.add_argument('reviews',nargs='+');args=parser.parse_args()
    archive=sqlite3.connect(Path(args.archive).resolve().as_uri()+'?mode=ro',uri=True);archive.row_factory=sqlite3.Row
    try:
        print(json.dumps(compile_reviews(json.loads(Path(args.inventory).read_text()),args.reviews,archive,args.output,
                         allow_partial=args.allow_partial_preview),ensure_ascii=False))
    finally:archive.close()
