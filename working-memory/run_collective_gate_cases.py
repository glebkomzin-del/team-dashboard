"""Four predeclared positive/negative gates for collective commitment handling."""
import json
from pathlib import Path
from compact_reconcile import GATE_RULES
from evaluation_budget import EvaluationCalls
from hybrid_pipeline import decoded
from openai_provider import request
from processor import units
from run_hybrid_validation import setup, ROOT

CASES = [
    ('collective_promise', 'Mara: Leon und ich übernehmen den Importtest. Wir versuchen beide Formate einzulesen; wer welches testet, teilen wir später auf.',
     'Mara', 'Mara übernimmt mit Leon die Erprobung beider Importformate, ohne Zusage eines erfolgreichen Imports.', ['supported']),
    ('collective_wish', 'Mara: Leon und ich könnten irgendwann beide Importformate testen. Leon: Vielleicht, entscheiden wir nächste Woche.',
     'Mara', 'Mara übernimmt mit Leon die Erprobung beider Importformate.', ['unsupported', 'ambiguous']),
    ('request_is_not_ownership', 'Mara: Leon, kannst du den Export testen? Leon: Ich kann derzeit nichts zusagen.',
     'Mara', 'Mara übernimmt den Exporttest.', ['unsupported']),
    ('unclear_collective', 'Mara: Mit wir meinte ich entweder das Betriebsteam oder die Lieferanten. Wer den Backup-Test übernimmt, ist noch offen.',
     'Mara', 'Mara übernimmt den Backup-Test.', ['unsupported', 'ambiguous']),
]


def main():
    store=setup(); schema=json.loads((Path(__file__).parent/'evaluation/work-gate-schema-v9.json').read_text())
    calls=EvaluationCalls(ROOT/'budget.sqlite',store,request,schema,{'component':'collective-gate-v1'},ceiling=11500000)
    results=[]
    try:
        for name,text,owner,claim,expected in CASES:
            candidate={'index':0,'kind':'commitment','owner':owner,'claim':claim,'title':claim,
                       'update':'none','update_target':None,'due_text':None}
            original=units(text)
            prompt=(Path(__file__).parent/'evaluation/work-gate-prompt-v9.txt').read_text()+'\n'+GATE_RULES+'\nKandidaten:\n'+json.dumps([candidate],ensure_ascii=False)+'\nBestehende Arbeit: []\nVollständiges Original:\n'+json.dumps(original,ensure_ascii=False)
            before=calls.total(); raw=decoded(calls(prompt,'gpt-5.6-terra',max_tokens=800))
            values=raw.get('verdicts',[])
            passed=len(values)==1 and values[0]['index']==0 and values[0]['verdict'] in expected and bool(values[0]['evidence_ids']) and all(i in original for i in values[0]['evidence_ids'])
            results.append({'case':name,'passed':passed,'expected':expected,'verdicts':values,'incremental_upper_usd':(calls.total()-before)/1e6})
            print(json.dumps(results[-1],ensure_ascii=False),flush=True)
            if not passed:break
    finally:
        (ROOT.parent/'cost-optimization-20260908'/'collective-gate.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        calls.close()

if __name__=='__main__':main()
