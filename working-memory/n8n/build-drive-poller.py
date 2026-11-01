"""Build an inactive future intake workflow; credentials are attached on n8n only."""
from pathlib import Path
import json,copy
root=Path(__file__).parent;base=json.loads((root/'drive-archive-read-test.json').read_text())
contract=(root/'drive-contract.mjs').read_text().replace('export function ','function ')
docx=(root/'teams-docx.mjs').read_text().replace("import { inflateRawSync } from 'node:zlib';", "const { inflateRawSync } = require('zlib');").replace('export function ','function ')
base['name']='Dashboard Job – neue Originale und Arbeitsgedächtnis'
nodes=[n for n in base['nodes'] if n['type']!='n8n-nodes-base.stickyNote'];by={n['name']:n for n in nodes}
manual=by['Manueller Lesetest'];manual['name']='Manuell prüfen'
for i,n in enumerate(nodes):n['position']=[i*260+260,0]
manifest={'id':'manifest','name':'Bekannte Versionen lesen','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,'position':[260,0],
 'parameters':{'method':'GET','url':'https://178-105-167-26.nip.io/dashboard-memory-draft/drive-manifest','authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','options':{'timeout':60000,'response':{'response':{'responseFormat':'json'}}}},'retryOnFail':True,'maxTries':3,'waitBetweenTries':2000}
manual['position']=[0,0];schedule={'id':'schedule','name':'Alle zehn Minuten prüfen','type':'n8n-nodes-base.scheduleTrigger','typeVersion':1.2,'position':[0,180],'parameters':{'rule':{'interval':[{'field':'minutes','minutesInterval':10}]}}}
inbox='1BFIu-ukqXgQu5143cmUaJvsaqLfmxLw2';processed='1gB3Yy_rh-OdR89LVUUckekjbqUzfPbQT'
listing=by['Alle Dateiseiten lesen']
listing['parameters']['queryParameters']['parameters'][0]['value']=f"trashed = false and '{inbox}' in parents"
select=by['Originale auswählen'];config={'folderIds':[inbox],'selectedIds':None,'maxFiles':5000}
select['parameters']['jsCode']=contract+'\nconst config = '+json.dumps(config)+';\nconst pages = $input.all().map(item=>item.json);\nconst selected=selectUnarchived(prepareInventory(pages,config),$("Bekannte Versionen lesen").first().json);\nreturn selected.map(file=>({json:file,pairedItem:{item:file.intake_page_index}}));'
# The Inbox now contains Microsoft Word files. Download them as binary and parse
# the WordprocessingML with the built-in zlib module; no external service sees it.
read=by['Original vollständig lesen']
read['parameters']['url']='={{ "https://www.googleapis.com/drive/v3/files/" + encodeURIComponent($json.id) + "?alt=media" }}'
read['parameters']['options']['response']['response']={'responseFormat':'file','outputPropertyName':'data'}
parse={'id':'parse-docx','name':'DOCX-Transkript normalisieren','type':'n8n-nodes-base.code','typeVersion':2,'position':[1300,0],
 'parameters':{'mode':'runOnceForAllItems','jsCode':docx+'\nconst items=$input.all();const out=[];\nfor(let i=0;i<items.length;i++){const buffer=await this.helpers.getBinaryDataBuffer(i,"data");const transcript=normalizeTeamsTranscript(extractDocxText(buffer));out.push({json:{transcript},pairedItem:{item:i}});}\nreturn out;'}}
# Native n8n per-item linkage carries the correct pre-read metadata through
# download, parsing and verification. A changing listing aborts the full run.
assemble=by['Geprüftes Original ausgeben'];assemble['parameters']['jsCode']=contract+'\nreturn {json:assembleOriginal($("Originale auswählen").item.json,$json,$("DOCX-Transkript normalisieren").item.json.transcript,{maxCharacters:2500000})};'
submit={'id':'persist','name':'Original sichern und einreihen','type':'n8n-nodes-base.httpRequest','typeVersion':4.2,'position':[1820,0],
 'parameters':{'method':'POST','url':'https://178-105-167-26.nip.io/dashboard-memory-draft/drive-sources','authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','sendBody':True,'specifyBody':'json','jsonBody':'={{ { original: $json } }}','options':{'timeout':120000,'response':{'response':{'responseFormat':'json'}}}},'retryOnFail':True,'maxTries':3,'waitBetweenTries':2000}
sequence=[manual,manifest,listing,select,read,parse,by['Version nach Lesen prüfen'],assemble,submit]
for i,n in enumerate(sequence):n['position']=[i*260,0]
base['nodes']=sequence+[schedule,{'id':'boundary','name':'Betriebsgrenze','type':'n8n-nodes-base.stickyNote','typeVersion':1,'position':[260,-340],'parameters':{'content':f'## Teams-Transkripte aus Inbox · GPT-5.6 Terra\nAlle zehn Minuten ausschließlich {inbox} prüfen. Microsoft-Word-Transkripte werden lokal in n8n gelesen, Sprecherzeilen normalisiert und erst nach einer erneuten Versionsprüfung an den kanonischen Eingang übergeben.\n\nDer Server archiviert zuerst und reiht neue Quellen einmalig ein. Geänderte Quellen brauchen Prüfung. Der vorbereitete Ordner Processed ({processed}) bleibt vorerst leer; dieser Nur-Lese-Workflow verschiebt keine Dateien in Drive.','width':1450,'height':300}}]
base['connections']={}
for a,b in zip(sequence,sequence[1:]):base['connections'][a['name']]={'main':[[{'node':b['name'],'type':'main','index':0}]]}
base['connections'][schedule['name']]={'main':[[{'node':manifest['name'],'type':'main','index':0}]]}
base['settings']={'executionOrder':'v1','executionTimeout':1800,'saveDataSuccessExecution':'none','saveDataErrorExecution':'all','saveManualExecutions':False,'saveExecutionProgress':False,'timezone':'Europe/Berlin'}
(root/'drive-poller.json').write_text(json.dumps(base,ensure_ascii=False,indent=2)+'\n')
print('Inactive workflow generated; no credentials, no activation, no model calls')
