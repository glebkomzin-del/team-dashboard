"""Build reviewable n8n push/renewal/move workflows; never deploy automatically.

Private configuration: header_credential_id, channel_token. The generated watch
workflow contains the channel token; write only to a private deployment folder.
"""
import copy
import json
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).parent
BASE_URL = 'https://178-105-167-26.nip.io'


def node(name, kind, parameters, *, credentials=None, version=2):
    value = {'id': str(uuid4()), 'name': name, 'type': 'n8n-nodes-base.'+kind,
             'typeVersion': version, 'position': [0, 0], 'parameters': parameters}
    if credentials:
        value['credentials'] = credentials
    return value


def connect(workflow, names):
    for i, name in enumerate(names[:-1]):
        workflow['connections'][name] = {'main': [[{'node': names[i+1], 'type': 'main', 'index': 0}]]}


def build(base, config):
    base = copy.deepcopy(base)
    header = {'httpHeaderAuth': {'id': config['header_credential_id'], 'name': 'Dashboard Drive Push'}}
    google = next(n['credentials'] for n in base['nodes'] if n['name'] == 'Alle Dateiseiten lesen')
    mover = {'oAuth2Api': {'id': config.get('move_credential_id', 'dashboardDriveMetadataMove'),
                          'name': 'Dashboard Job – Google Drive verschieben'}}
    common = {'executionOrder': 'v1', 'saveDataSuccessExecution': 'none',
              'saveDataErrorExecution': 'all', 'executionTimeout': 1800, 'timezone': 'Europe/Berlin'}
    webhook = node('Drive meldet eine Änderung', 'webhook',
                   {'httpMethod': 'POST', 'path': 'dashboard-drive-events', 'authentication': 'headerAuth',
                    'responseMode': 'onReceived', 'options': {}}, credentials=header, version=2)
    webhook['webhookId'] = str(uuid4())
    base['nodes'] = [n for n in base['nodes'] if n['name'] != webhook['name']]+[webhook]
    connect(base, [webhook['name'], 'Bekannte Versionen lesen'])
    for n in base['nodes']:
        if n['type'].endswith('stickyNote'):
            n['parameters']['content'] = '## Drive Push + Sicherheitsabgleich\nGoogle meldet Änderungen sofort. Die bestehende Zehn-Minuten-Prüfung holt verpasste Ereignisse nach. Dateien werden hier nur gesichert/eingereiht; der separate Processed-Flow verschiebt ausschließlich veröffentlichte, unveränderte Quellen.'
    base['settings'].update(common)
    base['active'] = False  # Publication is a separate deliberate operation.
    start = node('Manuell registrieren', 'manualTrigger', {}, version=1)
    scheduled = node('Ablauf täglich prüfen', 'scheduleTrigger',
                     {'rule': {'interval': [{'field': 'hours', 'hoursInterval': 24}]}}, version=1.2)
    renewal = node('Erneuerung erforderlich', 'code', {'jsCode': "const d=$getWorkflowStaticData('global'); if(d.channel && Number(d.channel.expiration)>Date.now()+2*86400000)return []; return [{json:{channelId:'dashboard-drive-'+Date.now()+'-'+Math.random().toString(16).slice(2)}}];"})
    token = node('Startposition lesen', 'httpRequest', {'url': 'https://www.googleapis.com/drive/v3/changes/startPageToken',
                 'authentication': 'genericCredentialType', 'genericAuthType': 'oAuth2Api', 'options': {}}, credentials=google, version=4.2)
    watch = node('Google Push registrieren', 'httpRequest', {
        'method': 'POST', 'url': 'https://www.googleapis.com/drive/v3/changes/watch',
        'authentication': 'genericCredentialType', 'genericAuthType': 'oAuth2Api',
        'sendQuery': True, 'queryParameters': {'parameters': [{'name': 'pageToken', 'value': '={{ $json.startPageToken }}'}]},
        'sendBody': True, 'specifyBody': 'json',
        'jsonBody': '={{ JSON.stringify({id: $("Erneuerung erforderlich").first().json.channelId, type:"web_hook", address:'+json.dumps(BASE_URL+'/webhook/dashboard-drive-events')+', token:'+json.dumps(config['channel_token'])+', expiration:String(Date.now()+6*86400000)}) }}',
        'options': {}}, credentials=google, version=4.2)
    saved = node('Neuen Kanal merken', 'code', {'jsCode': "const d=$getWorkflowStaticData('global'); const c=$input.first().json; if(!c.id||!c.resourceId||!c.expiration)throw new Error('Incomplete Drive channel'); const old=d.channel; d.channel={id:c.id,resourceId:c.resourceId,expiration:c.expiration}; return old?[{json:old}]:[];"})
    stop = node('Alten Kanal beenden', 'httpRequest', {'method': 'POST', 'url': 'https://www.googleapis.com/drive/v3/channels/stop',
                'authentication': 'genericCredentialType', 'genericAuthType': 'oAuth2Api',
                'sendBody': True, 'specifyBody': 'json', 'jsonBody': '={{ JSON.stringify({id:$json.id,resourceId:$json.resourceId}) }}',
                'options': {}}, credentials=google, version=4.2)
    stop['onError'] = 'continueRegularOutput'
    renew = {'id': 'dashboardDriveWatch', 'name': 'Dashboard Job – Drive Push erneuern', 'active': False,
             'nodes': [start, scheduled, renewal, token, watch, saved, stop], 'connections': {}, 'settings': common}
    connect(renew, [start['name'], renewal['name'], token['name'], watch['name'], saved['name'], stop['name']])
    connect(renew, [scheduled['name'], renewal['name']])
    # Reuse proven complete Drive pagination and the existing service credential.
    manifest = copy.deepcopy(next(n for n in base['nodes'] if n['name'] == 'Bekannte Versionen lesen'))
    listing = copy.deepcopy(next(n for n in base['nodes'] if n['name'] == 'Alle Dateiseiten lesen'))
    choose = node('Bekannte Inbox-Dateien', 'code', {'jsCode': "const known=$('Bekannte Versionen lesen').first().json.documents; if(!Array.isArray(known))throw new Error('Missing manifest'); const files=$input.all().flatMap(i=>i.json.files||[]); const ids=new Set(files.map(f=>f.id)); return known.filter(d=>ids.has(d.drive_metadata?.id)).map(d=>({json:{document_id:d.document_id}}));"})
    check = copy.deepcopy(manifest)
    check.update(id=str(uuid4()), name='Veröffentlichung prüfen')
    endpoint = manifest['parameters']['url'].removesuffix('/drive-manifest')+'/drive-completion/'
    check['parameters']['url'] = '={{ '+json.dumps(endpoint)+' + $json.document_id }}'
    ready = node('Nur veröffentlichte', 'code', {'jsCode': 'return $input.all().filter(i=>i.json.ready_to_move===true);'})
    fresh = node('Dateiversion vor Verschieben lesen', 'httpRequest', {
        'url': '={{ "https://www.googleapis.com/drive/v2/files/" + $json.file_id }}',
        'authentication': 'genericCredentialType', 'genericAuthType': 'oAuth2Api',
        'sendQuery': True, 'queryParameters': {'parameters': [{'name': 'fields', 'value': 'id,etag,version,md5Checksum,parents,labels(trashed)'}]},
        'options': {'response': {'response': {'fullResponse': True}}}}, credentials=google, version=4.2)
    guard_source = (ROOT/'drive-move.mjs').read_text().replace('export function ', 'function ')
    fresh['onError'] = 'continueRegularOutput'
    guard = node('Unveränderte Datei freigeben', 'code', {'jsCode': guard_source+"\nconst receipts=$('Nur veröffentlichte').all(); return $input.all().flatMap((item,i)=>{try{const body=item.json.body; const move=plannedMove(receipts[i].json,driveV2Metadata(body),body.etag); return move?[{json:move}]:[];}catch(e){return [{json:{blocked:true,file_id:receipts[i].json.file_id,reason:e.message}}];}});"})
    safe = node('Nur freigegebene Verschiebungen', 'code', {'jsCode': 'return $input.all().filter(i=>i.json.blocked!==true);'})
    move = node('Nach Processed verschieben', 'httpRequest', {
        'method': 'PATCH', 'url': '={{ "https://www.googleapis.com/drive/v2/files/" + $json.file_id }}',
        'authentication': 'genericCredentialType', 'genericAuthType': 'oAuth2Api',
        'sendQuery': True, 'queryParameters': {'parameters': [
            {'name': 'addParents', 'value': '={{ $json.addParents }}'}, {'name': 'removeParents', 'value': '={{ $json.removeParents }}'},
            {'name': 'modifiedDateBehavior', 'value': 'noChange'}, {'name': 'updateViewedDate', 'value': 'false'},
            {'name': 'fields', 'value': 'id,parents,version,md5Checksum,labels(trashed)'}]},
        'sendHeaders': True, 'headerParameters': {'parameters': [{'name': 'If-Match', 'value': '={{ $json.ifMatch }}'}]},
        'sendBody': True, 'specifyBody': 'json', 'jsonBody': '{}', 'options': {}}, credentials=mover, version=4.2)
    move_start = node('Manuell prüfen', 'manualTrigger', {}, version=1)
    move_schedule = node('Veröffentlichungen prüfen', 'scheduleTrigger', {'rule': {'interval': [{'field': 'minutes', 'minutesInterval': 1}]}}, version=1.2)
    move['onError'] = 'continueRegularOutput'
    verified = node('Verschiebung bestätigen', 'code', {'jsCode': guard_source+"\nconst plans=$('Nur freigegebene Verschiebungen').all(); const results=$input.all().map((item,i)=>{try{return {json:verifyMove(plans[i].json,item.json)}}catch(e){return {json:{file_id:plans[i].json.file_id,moved:false,reason:e.message}}}}); const failed=results.filter(i=>!i.json.moved); if(failed.length)throw new Error(failed.length+' Datei(en) nicht verschoben: '+failed.map(i=>i.json.reason).join('; ')); return results;"})
    moves = {'id': 'dashboardDriveMove', 'name': 'Dashboard Job – veröffentlichte Originale nach Processed', 'active': False,
             'nodes': [move_start, move_schedule, manifest, listing, choose, check, ready, fresh, guard, safe, move, verified],
             'connections': {}, 'settings': {**common, 'saveDataSuccessExecution': 'all'}}
    connect(moves, [n['name'] for n in [move_start, manifest, listing, choose, check, ready, fresh, guard, safe, move, verified]])
    connect(moves, [move_schedule['name'], manifest['name']])
    for workflow in (base, renew, moves):
        for i, n in enumerate(workflow['nodes']):
            n['position'] = [i*250, 0]
    return base, renew, moves


if __name__ == '__main__':
    original = json.loads(Path(sys.argv[1]).read_text())
    if isinstance(original, list): original = original[0]
    config = json.loads(Path(sys.argv[2]).read_text())
    directory = Path(sys.argv[3]); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, workflow in zip(('intake-push', 'renew-push', 'move-processed'), build(original, config)):
        path = directory/(name+'.json'); path.write_text(json.dumps(workflow, ensure_ascii=False, indent=2)); path.chmod(0o600)
