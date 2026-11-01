"""Build the portable, inactive n8n read test from the tested pure contracts."""
import argparse
import json
from pathlib import Path
args_parser=argparse.ArgumentParser()
args_parser.add_argument('--archive',action='store_true',help='Read all current scoped originals, without model/intake nodes')
args=args_parser.parse_args()
ROOT=Path(__file__).parent
contract=(ROOT/'drive-contract.mjs').read_text().replace('export function ', 'function ')
folders=['1xUMHw3Z3zcvHE96mczw4e9HFZpUJyMoE','1QAYD0wNVy28ApPq_Jr6WbECmKNr8TWz-']
config={'folderIds':folders,'selectedIds':['11SyC3yxc1cPr2aFlg46UfTu1kMbR3VdZ3Pi_GSreEgg'],'maxFiles':5000}
if args.archive: config['selectedIds']=None
fields='id,name,mimeType,modifiedTime,version,parents,trashed,size,md5Checksum'
def node(id,name,type,version,pos,parameters,**extra):return dict(id=id,name=name,type='n8n-nodes-base.'+type,typeVersion=version,position=pos,parameters=parameters,**extra)
def http(id,name,x,parameters):
 return node(id,name,'httpRequest',4.2,[x,0],{'method':'GET','authentication':'genericCredentialType','genericAuthType':'oAuth2Api',**parameters},retryOnFail=True,maxTries=3,waitBetweenTries=1000)
list_node=http('list','Alle Dateiseiten lesen',260,{
 'url':'https://www.googleapis.com/drive/v3/files','sendQuery':True,'queryParameters':{'parameters':[
 {'name':'q','value':"trashed = false and ("+' or '.join("'"+f+"' in parents" for f in folders)+')'},
 {'name':'fields','value':'nextPageToken,incompleteSearch,files('+fields+')'},
 {'name':'pageSize','value':'1000'},{'name':'spaces','value':'drive'},{'name':'corpora','value':'user'},
 {'name':'orderBy','value':'name'}]},
 'options':{'timeout':30000,'response':{'response':{'responseFormat':'json'}},'pagination':{'pagination':{
 'paginationMode':'updateAParameterInEachRequest','parameters':{'parameters':[{'type':'qs','name':'pageToken','value':'={{ $response.body.nextPageToken || "" }}'}]},
 'paginationCompleteWhen':'other','completeExpression':'={{ !$response.body.nextPageToken }}','limitPagesFetched':True,'maxRequests':100,'requestInterval':200}}}})
select_node=node('select','Originale auswählen','code',2,[520,0],{'jsCode':contract+'\nconst config = '+json.dumps(config)+';\nconst pages = $input.all().map(item => item.json);\nreturn prepareInventory(pages, config).map(file => ({json:file, pairedItem:{item:file.intake_page_index}}));'})
read_node=http('read','Original vollständig lesen',780,{
 'url':'={{ "https://www.googleapis.com/drive/v3/files/" + encodeURIComponent($json.id) + ($json.mimeType === "application/vnd.google-apps.document" ? "/export?mimeType=text%2Fplain" : "?alt=media") }}',
 'options':{'timeout':60000,'response':{'response':{'responseFormat':'text','outputPropertyName':'transcript'}}}})
verify_node=http('verify','Version nach Lesen prüfen',1040,{
 'url':'={{ "https://www.googleapis.com/drive/v3/files/" + encodeURIComponent($("Originale auswählen").item.json.id) }}',
 'sendQuery':True,'queryParameters':{'parameters':[{'name':'fields','value':fields}]},
 'options':{'timeout':30000,'response':{'response':{'responseFormat':'json'}}}})
assemble_node=node('assemble','Geprüftes Original ausgeben','code',2,[1300,0],{'mode':'runOnceForEachItem','jsCode':contract+'\nreturn {json:assembleOriginal($("Originale auswählen").item.json, $json, $("Original vollständig lesen").item.json.transcript)};'})
nodes=[node('manual','Manueller Lesetest','manualTrigger',1,[0,0],{}),list_node,select_node,read_node,verify_node,assemble_node,
 node('note','Lesetest und Grenze','stickyNote',1,[250,-290],{'content':'## Isolierter Drive-Lesetest\nAlle Seiten der Inbox/Processed-Inventur. Anschließend nur die explizit ausgewählte Finance-Quelle vom 15.07. lesen.\n\nVor Ausführung an allen drei HTTP-Nodes dasselbe Google-OAuth2-Credential mit drive.readonly wählen. Keine Drive-Schreiboperationen, keine Modellaufrufe, keine Aufgabenübernahme. Das letzte Ergebnis bedeutet nur: Original vollständig gelesen und Version kontrolliert.','height':240,'width':1000})]
flow={'name':'Dashboard Job – Drive-Originale im Lesetest','nodes':nodes,'connections':{},'settings':{'executionOrder':'v1'}}
for a,b in zip(nodes[:5],nodes[1:6]):flow['connections'][a['name']]={'main':[[{'node':b['name'],'type':'main','index':0}]]}
if args.archive:
 flow['name']='Dashboard Job – Drive-Archiv im Lesetest'
 assemble_node['parameters']['jsCode']=contract+'\nreturn {json:assembleOriginal($("Originale auswählen").item.json, $json, $("Original vollständig lesen").item.json.transcript, {maxCharacters:4000000})};'
 nodes[-1]['parameters']['content']='## Getrennte Originalsicherung\nAlle aktuellen Google-Docs/Textdateien aus Inbox und Processed vollständig lesen. Metadaten vor/nach jedem Export vergleichen. Bis 4 Millionen Zeichen je Original; größere Dateien führen zum Abbruch.\n\nAusschließlich GET. Keine Modelle, keine Aufgaben, keine Dateiänderungen. Ausgabe ist noch kein Import. Vollständige Originale privat sichern; größere Texte brauchen vor fachlicher Verarbeitung eine eigene Kontextstrategie.'
filename='drive-archive-read-test.json' if args.archive else 'drive-read-test.json'
(ROOT/filename).write_text(json.dumps(flow,ensure_ascii=False,indent=2)+'\n')
print('Portable workflow generated:',filename,'; no credential material included')
