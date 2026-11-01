"""Freeze one prospective medium comparison, without provider or host calls."""
import hashlib,json,os
from pathlib import Path

ROOT=Path(__file__).parent
OLD=Path('/private/tmp/semantic-relation-sol61-default-qualification-20261005')
OLD_REQUEST='b8e14586cc637dcb4ee6bd8d0a6323be8602f01bf99886633ffd23215eccac93'
OLD_BINDINGS='ed48fa373449a917174db5155e1a73f3961fdbb2e2dbed0255c6426fff62752c'
EXPECTED_SHA='d9f105645d2014a0c1e4c078ace726f0c8a6217bedc6cd8e743593c10ada2964'
SOL_HIGH={'response.json':'a6ea1e73de70cac429c79e45978f78fdb0047b3402cc99080ae1acddb65de897',
          'receipt.json':'dba931fa60157287950623f4dd513357cf87aea07acbf2ae87953120931ea93f',
          'reservation.json':'3ea20dde012bd1f269e7ad786f34dc8ceb89ad96958a15722af898d150630b32'}

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    assert sha(OLD/'request/request.json')==OLD_REQUEST
    assert sha(OLD/'request/bindings.json')==OLD_BINDINGS
    assert sha(ROOT/'expected-private/expected.json')==EXPECTED_SHA
    old=json.loads((OLD/'request/request.json').read_text())
    request={**old,'reasoning_effort':'medium'}
    assert {k:v for k,v in request.items() if k!='reasoning_effort'}=={k:v for k,v in old.items() if k!='reasoning_effort'}
    request_path=ROOT/'request/request.json'
    request_path.write_text(json.dumps(request,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    request_path.chmod(0o600)
    bindings=json.loads((OLD/'request/bindings.json').read_text())
    for name,part in bindings['prior_attempts'].items():
        for filename,wanted in part['sha256'].items():
            assert sha(ROOT/'prior-attempts'/name/filename)==wanted
    for filename,wanted in SOL_HIGH.items():
        assert sha(ROOT/'prior-attempts/sol61high'/filename)==wanted
    sol_receipt=json.loads((ROOT/'prior-attempts/sol61high/receipt.json').read_text())
    assert sol_receipt['actual_micro_usd']==104459 and sol_receipt['reserved_micro_usd']==191475
    assert sol_receipt['stop_reason'] is None
    previous=bindings['prior_attempts']
    previous['sol61high']={'sha256':SOL_HIGH,'actual_micro_usd':104459,
                           'reserved_micro_usd':191475,'state':sol_receipt['state']}
    assert sum(previous[n]['actual_micro_usd'] for n in previous if n!='http400')==398890
    assert previous['http400']['actual_micro_usd'] is None and previous['http400']['reserved_micro_usd']==221248
    new={**bindings,'request_sha256':sha(request_path),'reasoning_effort':'medium',
         'provider_adapter_sha256':sha(ROOT/'provider/openai_provider.py'),
         'previous_sol61_default_request_sha256':OLD_REQUEST,
         'previous_sol61_default_bindings_sha256':OLD_BINDINGS,
         'prior_attempts':previous}
    path=ROOT/'request/bindings.json'
    path.write_text(json.dumps(new,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    path.chmod(0o600)
    for name,wanted in new['runtime_source_sha256'].items():
        assert sha(ROOT/'runtime'/name)==wanted
    assert sha(ROOT/'runner/cost_sol61.py')==new['cost_adapter_sha256']
    print(json.dumps({'result':'MEDIUM_PREPARED_UNSENT','request_sha256':sha(request_path),
                      'bindings_sha256':sha(path),'provider_sha256':new['provider_adapter_sha256'],
                      'prior_known_micro_usd':398890,'prior_http400_actual_micro_usd':None,
                      'prior_http400_reserved_micro_usd':221248,'reserve_micro_usd':191475,
                      'comparison_cap_micro_usd':250000,'provider_calls':0},sort_keys=True))

if __name__=='__main__':main()
