"""One anonymous verification of the already promoted artifact; never a promotion.

Static acceptance is historical and immutable. Owner/Writer must separately bind
fresh operational observations and the unchanged current provider access contract.
Missing raw bytes or a supplied success boolean cannot establish this exception.
"""
import argparse
import base64
import concurrent.futures
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

PROBLEM = 'HZ-MIGRATION-20261003-FINAL-CUTOVER'
SCHEMA = 'frontend-access-successor-v1'
PHASE = 'FRONTEND_ACCESS_CONTRACT_RECONCILIATION_1'
PRIMARY = 'team-dashboard-rho.vercel.app'
SECONDARY = 'team-dashboard-glebkomzin-dels-projects.vercel.app'
ALIASES = {PRIMARY, SECONDARY}
PROJECT = 'prj_pWCB8TaGLQesLsT9me0jgT0FqcC5'
OPS = Path(__file__).resolve().parent
ARTIFACT_SHA = 'f1c11b1f683f53b0dbc5e6c793350a25b9156a957787f0b0c335a1029c95829f'
ENV = {'VITE_SUPABASE_URL', 'VITE_SUPABASE_ANON_KEY'}
PARENT_SHA = 'baca4e5fd444620307fa78830c1b98222e564302766b25238b08aa009b25ff7d'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(body): return hashlib.sha256(body).hexdigest()


def stamp(value):
    result = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    need(result.tzinfo is not None, 'Timestamp timezone missing')
    return result.astimezone(dt.timezone.utc)


def references(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}:
            yield value
        else:
            for key, item in value.items():
                if key != 'origin_refs': yield from references(item)
    elif isinstance(value, list):
        for item in value: yield from references(item)


def local_read(path):
    path = Path(path)
    need(path.is_absolute() and path.is_file() and not path.is_symlink(), 'Unsafe access primary')
    return path.read_bytes()


def bound(ref, read_bytes, hashes=None):
    need(set(ref) == {'path', 'sha256'} and Path(ref['path']).is_absolute(), 'Malformed access ref')
    if hashes is not None: need(hashes.get(ref['path']) == ref['sha256'], 'Access primary not gate-bound')
    body = read_bytes(ref['path'])
    need(sha(body) == ref['sha256'], 'Access primary SHA differs')
    return body


def api_payload(primary):
    need(primary['exit_code'] == 0 and primary['args'][0:1] == ['api']
         and primary['args'][2:4] == ['--method', 'GET'], 'Access provider observation is not successful GET')
    return json.loads(base64.b64decode(primary['stdout_b64'], validate=True))


def provider_projection(payload):
    need(set(payload) == {'project', 'deployment', 'alias-primary', 'alias-secondary'}, 'Access provider set incomplete')
    project, deployment = payload['project'], payload['deployment']
    need(project['id'] == PROJECT == deployment['projectId'], 'Access project differs')
    need(project.get('ssoProtection') == {'deploymentType': 'all_except_custom_domains'}, 'Existing SSO policy unknown/different')
    need(deployment['target'] == 'production' and deployment['readyState'] == 'READY'
         and deployment['id'].startswith('dpl_') and ALIASES.issubset(set(deployment['alias']))
         and SECONDARY in deployment['automaticAliases'], 'Same READY automatic production absent')
    aliases = {}
    for name, alias in [('alias-primary', PRIMARY), ('alias-secondary', SECONDARY)]:
        item = payload[name]
        need(item['alias'] == alias and item['projectId'] == PROJECT and item['deploymentId'] == deployment['id']
             and item.get('redirect') is None and item.get('redirectStatusCode') is None, 'Foreign/redirecting access alias')
        aliases[alias] = {'deploymentId': item['deploymentId'], 'projectId': item['projectId'],
                          'redirect': item.get('redirect'), 'redirectStatusCode': item.get('redirectStatusCode')}
    # No secret value is exposed. A digest binds existing bypass configuration too.
    policy = {key: {'present': key in project, 'value': project.get(key)} for key in
              ('ssoProtection', 'passwordProtection', 'trustedIps', 'deploymentProtection')}
    policy['existing_bypass_configuration_sha256'] = sha(json.dumps(project.get('protectionBypass'), sort_keys=True).encode())
    return {'project_id': PROJECT, 'policy': policy, 'production_id': deployment['id'],
            'production_url': deployment['url'], 'automatic_aliases': sorted(deployment['automaticAliases']), 'aliases': aliases}


def current_observation(ref, read_bytes, hashes, *, run, now):
    observation=json.loads(bound(ref,read_bytes,hashes))
    need(observation['problem_id']==PROBLEM and observation['run_dir']==run
         and 0 <= (now-stamp(observation['observed_at'])).total_seconds() <= 300,
         'Current access operational observation stale/foreign')
    raw={name:json.loads(bound(primary,read_bytes,hashes)) for name,primary in observation['provider_primaries'].items()}
    for value in raw.values():
        need(0 <= (now-stamp(value['observed_at'])).total_seconds() <= 300,'Current raw access GET stale')
    provider={name:api_payload(value) for name,value in raw.items()}
    need(provider==observation['payload'],'Current access payload differs from raw GETs')
    provider_projection(provider)
    return provider


def validate(receipt, read_bytes=local_read, hashes=None, *, run=None, recovery_sha=None, current_provider=None):
    """Recalculate positives from bound raw primaries; never trust checks flags."""
    need(receipt['schema'] == SCHEMA and receipt['status'] == 'READONLY_VERIFIED'
         and receipt['phase'] == PHASE and receipt['problem_id'] == PROBLEM
         and receipt['operational_go'] is False, 'Access successor schema/status differs')
    if run is not None: need(receipt['run_dir'] == run, 'Access run differs')
    start, end = stamp(receipt['window_started_at']), stamp(receipt['observed_at'])
    need(0 <= (end-start).total_seconds() <= 300, 'Access verification window exceeds 300s')
    for ref in references(receipt): bound(ref, read_bytes, hashes)
    need(receipt['parent_receipt']['sha256'] == PARENT_SHA, 'Original STOPPED parent hash differs')
    parent = json.loads(bound(receipt['parent_receipt'], read_bytes, hashes))
    need(parent['status'] == 'STOPPED_NO_RETRY' and parent['promotion_attempts'] == 1
         and parent['url_env_added'] is True and parent['anon_env_added'] is True
         and parent['return_ownership_known'] is True and parent['unknown_ownership'] == []
         and all(parent['ownership'][key] == 'OWN_ADD_CONFIRMED_EXIT_0' for key in ENV), 'Actual STOPPED parent/ENV ownership absent')
    for key in ('production_deployment_id', 'runtime_recovery_sha256', 'artifact_sha256', 'promotion_attempts',
                'url_env_added', 'anon_env_added', 'ownership', 'unknown_ownership', 'return_ownership_known',
                'production', 'promoted_url', 'readiness_count'):
        need(receipt[key] == parent[key], 'Access successor changed parent identity/consumption')
    need(receipt['artifact_sha256'] == ARTIFACT_SHA and receipt['readiness_count'] >= 1, 'Frozen artifact/READY provenance differs')
    if recovery_sha is not None: need(receipt['runtime_recovery_sha256'] == recovery_sha, 'Access original recovery differs')
    artifact = json.loads(bound(receipt['artifact_ref'], read_bytes, hashes))
    need(receipt['artifact_ref']['sha256'] == ARTIFACT_SHA and artifact['source_manifest_count'] == 104
         and len(artifact['current_static_hashes']) == 7, 'Access frozen manifest differs')
    config = json.loads(bound(receipt['config_ref'], read_bytes, hashes))
    need(receipt['config_ref']['sha256'] == artifact['output_hashes']['config.json'], 'Access frozen config differs')
    expected_headers = config['routes'][0]['headers']
    projections = []
    for group in ('provider_before', 'provider_after'):
        raw = {key: json.loads(bound(ref, read_bytes, hashes)) for key, ref in receipt[group].items()}
        for primary in raw.values(): need(start <= stamp(primary['observed_at']) <= end, 'Provider observation outside access window')
        projection = provider_projection({key: api_payload(primary) for key, primary in raw.items()})
        need(projection == receipt[group+'_projection'], 'Claimed access policy projection differs from raw GETs')
        projections.append(projection)
    need(projections[0] == projections[1] and projections[1]['production_id'] == receipt['production_deployment_id'],
         'Protection/production changed during bounded verification')
    expected = {'/': artifact['current_static_hashes']['static/index.html'],
                '/memory-next?recovery=1': artifact['current_static_hashes']['static/index.html']}
    expected.update({'/'+name.removeprefix('static/'): digest for name, digest in artifact['current_static_hashes'].items()
                     if name.startswith('static/assets/')})
    need(set(receipt['public_primaries']) == set(expected) and len(expected) == 6, 'Six positive public observations required')
    for route, ref in receipt['public_primaries'].items():
        raw = json.loads(bound(ref, read_bytes, hashes));body = base64.b64decode(raw['body_b64'], validate=True)
        url = 'https://'+PRIMARY+route
        need(raw['requested_url'] == raw['final_url'] == url and raw['redirects'] == []
             and raw['credentials_sent'] is False and raw['request_headers'] == {}
             and start <= stamp(raw['observed_at']) <= end and raw['status'] == 200
             and sha(body) == expected[route], 'Public app bytes/URL/anonymous access unproven')
        if route in ('/', '/memory-next?recovery=1'):
            headers = {key.lower(): value for key, value in raw['headers']}
            need(all(headers.get(key.lower()) == value for key, value in expected_headers.items()), 'Public app exact headers differ')
    secondary = json.loads(bound(receipt['secondary_primary'], read_bytes, hashes))
    headers = {key.lower(): value for key, value in secondary['headers']}
    final = urllib.parse.urlsplit(secondary['final_url'])
    body = base64.b64decode(secondary['body_b64'], validate=True)
    need(secondary['requested_url'] == 'https://'+SECONDARY+'/' and secondary['credentials_sent'] is False
         and secondary['request_headers'] == {} and secondary['redirects'] and secondary['status'] == 200
         and final.scheme == 'https' and final.hostname == 'vercel.com' and final.path == '/login'
         and headers.get('x-matched-path') == '/login' and b'<title>Login' in body
         and start <= stamp(secondary['observed_at']) <= end, 'Positive protected secondary observation absent')
    need(receipt['historical_protection_configuration'] == 'UNKNOWN'
         and receipt['secondary_classification'] == 'EXISTING_SSO_PROTECTED_AUTOMATIC_ALIAS'
         and receipt['primary_alias'] == PRIMARY and receipt['secondary_alias'] == SECONDARY,
         'Access exception classification differs')
    if current_provider is not None:
        need(provider_projection(current_provider) == projections[1], 'Current access policy/production differs from historical static acceptance')
    return receipt['production_deployment_id']


def save(directory, name, value):
    body = value if isinstance(value, bytes) else (json.dumps(value, indent=2)+'\n').encode()
    path = directory/name;fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(body);stream.flush();os.fsync(stream.fileno())
    return {'path': str(path), 'sha256': sha(body)}


def collect(parent_ref, run, output):
    directory = Path(output);need(directory.is_absolute() and not directory.exists(), 'New private access output required')
    directory.mkdir(mode=0o700);need(parent_ref['sha256']==PARENT_SHA, 'Exact original STOPPED parent required')
    parent = json.loads(bound(parent_ref, local_read));need(parent['status']=='STOPPED_NO_RETRY','Original stopped parent required')
    started = dt.datetime.now(dt.timezone.utc).isoformat();identity = parent['production_deployment_id']
    artifact_ref = {'path': str(OPS/'frontend-target-artifact.json'), 'sha256': ARTIFACT_SHA}
    artifact = json.loads(bound(artifact_ref, local_read));config_path = Path(artifact['build_path'])/'.vercel/output/config.json'
    config_ref = {'path': str(config_path), 'sha256': artifact['output_hashes']['config.json']}
    paths = {'project': '/v9/projects/team-dashboard', 'deployment': '/v13/deployments/'+identity,
             'alias-primary': '/v4/aliases/'+PRIMARY, 'alias-secondary': '/v4/aliases/'+SECONDARY}
    def provider(group):
        def get(item):
            name, endpoint = item;args = ['api', endpoint, '--method', 'GET', '--raw', '--scope', 'glebkomzin-dels-projects']
            result = subprocess.run(['vercel', *args], cwd=artifact['build_path'], capture_output=True, timeout=90)
            raw = {'args': args, 'exit_code': result.returncode, 'stdout_b64': base64.b64encode(result.stdout).decode(),
                   'stderr_b64': base64.b64encode(result.stderr).decode(), 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat()}
            ref = save(directory, group+'-'+name+'-primary-private.json', raw)
            return name, ref, api_payload(raw)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: values = list(pool.map(get, paths.items()))
        return {n: ref for n, ref, value in values}, {n: value for n, ref, value in values}
    class Redirects(urllib.request.HTTPRedirectHandler):
        def __init__(self): self.history = []
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            self.history.append({'requested_url': req.full_url, 'status': code, 'location': newurl})
            return super().redirect_request(req, fp, code, msg, headers, newurl)
    def public(route, alias, name):
        redirects = Redirects();opener = urllib.request.build_opener(redirects)
        url = 'https://'+alias+route
        with opener.open(urllib.request.Request(url), timeout=45) as response:
            raw = {'requested_url': url, 'final_url': response.geturl(), 'status': response.status,
                   'headers': list(response.headers.items()), 'body_b64': base64.b64encode(response.read()).decode(),
                   'redirects': redirects.history, 'request_headers': {}, 'credentials_sent': False,
                   'observed_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        return save(directory, name+'-http-primary-private.json', raw)
    try:
        before_refs, before = provider('before');provider_projection(before)
        routes = ['/', '/memory-next?recovery=1']+['/'+n.removeprefix('static/') for n in artifact['current_static_hashes'] if n.startswith('static/assets/')]
        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool:
            tasks = {route: pool.submit(public, route, PRIMARY, 'public-'+str(i)) for i, route in enumerate(routes)}
            secondary_task = pool.submit(public, '/', SECONDARY, 'secondary')
            public_refs = {route: task.result() for route, task in tasks.items()};secondary = secondary_task.result()
        after_refs, after = provider('after')
        receipt = {key: parent[key] for key in ('production_deployment_id', 'runtime_recovery_sha256', 'artifact_sha256',
                   'promotion_attempts', 'url_env_added', 'anon_env_added', 'ownership', 'unknown_ownership',
                   'return_ownership_known', 'production', 'promoted_url', 'readiness_count')}
        receipt.update(schema=SCHEMA, status='READONLY_VERIFIED', phase=PHASE, problem_id=PROBLEM, run_dir=run,
             operational_go=False, parent_receipt=parent_ref, artifact_ref=artifact_ref, config_ref=config_ref,
             window_started_at=started, observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
             provider_before=before_refs, provider_after=after_refs, provider_before_projection=provider_projection(before),
             provider_after_projection=provider_projection(after), public_primaries=public_refs, secondary_primary=secondary,
             historical_protection_configuration='UNKNOWN', secondary_classification='EXISTING_SSO_PROTECTED_AUTOMATIC_ALIAS',
             primary_alias=PRIMARY, secondary_alias=SECONDARY, static_acceptance='HISTORICAL_DEPLOYMENT_BOUND_BYTES',
             later_current_operational_facts_required=True)
        validate(receipt, run=run, recovery_sha=parent['runtime_recovery_sha256'])
        return save(directory, 'frontend-access-successor-receipt.json', receipt)
    except Exception as error:
        save(directory, 'failure-private.json', {'status': 'DENIED_NO_SUCCESSOR', 'type': type(error).__name__, 'cause': str(error), 'retry': False})
        raise


def main():
    p = argparse.ArgumentParser();p.add_argument('--parent', required=True);p.add_argument('--parent-sha256', required=True)
    p.add_argument('--run-dir', required=True);p.add_argument('--output', required=True);a = p.parse_args();os.umask(0o077)
    print(json.dumps({'candidate': collect({'path': a.parent, 'sha256': a.parent_sha256}, a.run_dir, a.output),
                      'operational_go': False, 'production_mutations': 0}))


if __name__ == '__main__': main()
