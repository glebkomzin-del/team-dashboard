import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';
import {selectUnarchived} from './drive-contract.mjs';
const file={id:'fictional',source_id:'drive:fictional',name:'2026-09-07 Test',version:'2',modifiedTime:'2026-09-07T12:00:00Z',mimeType:'text/plain',parents:['one','two']};
const row={source_id:file.source_id,drive_metadata:{id:file.id,name:file.name,version:file.version,modified_time:file.modifiedTime,mime_type:file.mimeType,parents:['two','one'],md5_checksum:null}};
test('exact saved version is skipped; changed or unqueued source is retried',()=>{
 const active={...row,intake_blocked:false};
 assert.deepEqual(selectUnarchived([file],{documents:[active]}),[]);
 assert.deepEqual(selectUnarchived([file],{documents:[row]}),[]); // pre-migration response
 assert.deepEqual(selectUnarchived([file],{documents:[]}),[file]);
 for(const [key,value] of Object.entries({version:'3',name:'2026-09-07 Renamed',modifiedTime:'2026-09-07T13:00:00Z',parents:['one']})){
  const changed={...file,[key]:value};assert.deepEqual(selectUnarchived([changed],{documents:[active]}),[changed]);
 }
});
test('missing or inconsistent receipt never becomes an empty archive',()=>{
 for(const manifest of [null,{}, {documents:null},{documents:[{}]}, {documents:[row,row]},{documents:[{...row,intake_blocked:'true'}]}])assert.throws(()=>selectUnarchived([file],manifest));
});
test('deleted source identity stays blocked when Drive metadata changes',()=>{
 const blocked={...row,intake_blocked:true};
 assert.deepEqual(selectUnarchived([file],{documents:[blocked]}),[]);
 for(const [key,value] of Object.entries({version:'3',name:'2026-09-07 Renamed',modifiedTime:'2026-09-07T13:00:00Z',parents:['one']})){
  assert.deepEqual(selectUnarchived([{...file,[key]:value}],{documents:[blocked]}),[]);
 }
});
test('generated polling workflow embeds the tombstone selector',()=>{
 const workflow=JSON.parse(readFileSync(new URL('./drive-poller.json',import.meta.url),'utf8'));
 for(const name of ['Originale auswählen','Geprüftes Original ausgeben']){
  const node=workflow.nodes.find(item=>item.name===name);
  assert.match(node?.parameters?.jsCode||'',/if \(prior\.intakeBlocked\) return false;/);
 }
});
