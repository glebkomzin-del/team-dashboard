"""Replay saved observations/gate judgments into a NEW database, without API calls.

The original database and its paid-call ledger remain unchanged. Projection IDs
are stable so explicit links survive. Missing targets are a visible review case.
"""
import argparse
import json
from pathlib import Path
from memory import connect, register, claim, apply, overview
from processor import apply_work_gate, units

def reproject(source_path, target_path, *, guard_same_day=False):
    if Path(source_path).resolve() == Path(target_path).resolve() or Path(target_path).exists():
        raise ValueError('Target must be a new database')
    if not Path(source_path).is_file():
        raise ValueError('Source database missing')
    source = connect(source_path)
    target = connect(target_path)
    try:
        for job in source.execute("SELECT j.id AS job_id,j.pipeline,s.* FROM jobs j JOIN source_versions s ON s.id=j.source_version WHERE j.status='applied' ORDER BY s.event_date,s.observed_at"):
            observations = [json.loads(r[0]) for r in source.execute('SELECT data_json FROM observations WHERE job_id=? ORDER BY rowid', (job['job_id'],))]
            proposal = {'observations': observations, 'coverage_notes': ['Deterministic replay; no new model calls.']}
            gate = source.execute("SELECT proposal_json FROM runs WHERE job_id=? AND outcome='work_gate' ORDER BY rowid DESC LIMIT 1", (job['job_id'],)).fetchone()
            # Applied rows already contain resolved gate judgments and may include
            # later lifecycle observations or human corrections. Do not gate twice.
            if gate and not any(o.get('work_gate') for o in observations):
                response = json.loads(gate[0])
                verdicts = json.loads(''.join(c.get('text', '') for c in response['content'] if c['type'] == 'text'))['verdicts']
                proposal = apply_work_gate(proposal, verdicts, units(job['transcript']))
            known = {r[0] for r in target.execute('SELECT DISTINCT work_id FROM work_events')}
            for o in observations:
                if o.get('update_target') and o['update_target'] not in known:
                    o['unapplied_target'] = o['update_target']
                    o['unapplied_update'] = o['update']
                    o.update(update_target=None, update='none', required_review=True,
                             action_uncertainty='Zielzusage ist in der korrigierten Projektion nicht vorhanden.')
            jid = register(target, source_id=job['source_id'], event_date=job['event_date'], title=job['title'], transcript=job['transcript'], pipeline=job['pipeline'])
            if guard_same_day:
                from temporal_guard import guard
                proposal=guard(target,{'meeting_date':job['event_date']},proposal)
            apply(target, jid, claim(target, jid), proposal, model='deterministic-reprojection')
        if guard_same_day:
            import hashlib
            root=Path(__file__).resolve().parent
            receipt={'source':str(Path(source_path).resolve()),'rules_sha256':hashlib.sha256((root/'memory.py').read_bytes()+(root/'temporal_guard.py').read_bytes()).hexdigest(),'method':'saved_observations_with_identity_and_temporal_guards','paid_calls':0}
            target.execute('CREATE TABLE replay_receipt (id INTEGER PRIMARY KEY CHECK(id=1), receipt_json TEXT NOT NULL)')
            target.execute('INSERT INTO replay_receipt VALUES (1,?)',(json.dumps(receipt),))
        result = overview(target)
        return {k: len(v) for k, v in result.items() if isinstance(v, list)}
    finally:
        source.close()
        target.close()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('target')
    parser.add_argument('--guard-same-day',action='store_true')
    args = parser.parse_args()
    print(json.dumps(reproject(args.source, args.target,guard_same_day=args.guard_same_day)))
