import test from 'node:test';
import assert from 'node:assert/strict';
import {plannedMove,driveV2Metadata,verifyMove} from './drive-move.mjs';
const receipt = {ready_to_move:true,file_id:'file',version:'7',md5_checksum:'a'.repeat(32),
  source_folders:['inbox'],destination_folder:'processed'};
const current = {id:'file',version:'7',md5Checksum:'a'.repeat(32),parents:['inbox','unrelated']};
test('only a published, unchanged file can move; other parents remain',()=>{
  assert.deepEqual(plannedMove(receipt,current,'"etag"'), {file_id:'file',addParents:'processed',removeParents:'inbox',ifMatch:'"etag"',md5_checksum:receipt.md5_checksum});
  assert.equal(plannedMove({ready_to_move:false},current,'"etag"'),null);
});
test('v2 metadata supplies the conditional-write ETag and a checked move receipt',()=>{
  const body={...current,etag:'"v2"',parents:[{id:'inbox'}],labels:{trashed:false}};
  const normalized=driveV2Metadata(body);
  const plan=plannedMove(receipt,normalized,body.etag);
  assert.equal(plan.ifMatch,'"v2"');
  assert.deepEqual(verifyMove(plan,{...body,version:'8',parents:[{id:'processed'}]}),
    {file_id:'file',moved:true,version:'8'});
  assert.throws(()=>verifyMove(plan,body));
  assert.throws(()=>verifyMove(plan,{...body,parents:[{id:'processed'}],md5Checksum:'b'.repeat(32)}));
  assert.throws(()=>driveV2Metadata({...body,labels:{}}));
});
test('ten entries and duplicate delivery produce the same idempotent move plans',()=>{
  const plans=Array.from({length:10},(_,i)=>plannedMove({...receipt,file_id:'f'+i},{...current,id:'f'+i},'"etag"'));
  assert.equal(new Set(plans.map(p=>p.file_id)).size,10);
  assert.deepEqual(plannedMove(receipt,current,'"etag"'),plannedMove(receipt,current,'"etag"'));
  assert.equal(plannedMove(receipt,{...current,version:'8',parents:['processed']},'"etag2"'),null);
});
test('changed content, older version or identity, missing ETag and trashed files stop',()=>{
  for(const patch of [{version:'6'},{version:'invalid'},{md5Checksum:'b'.repeat(32)},{id:'foreign'},{trashed:true},{parents:[]}])
    assert.throws(()=>plannedMove(receipt,{...current,...patch},'"etag"'));
  assert.throws(()=>plannedMove(receipt,current,null));
});

test('metadata-only version advances retain the published content and fresh ETag guard',()=>{
  const plan=plannedMove(receipt,{...current,version:'8'},'\"fresh-etag\"');
  assert.equal(plan.ifMatch,'\"fresh-etag\"');
  assert.throws(()=>plannedMove(receipt,{...current,version:'8',md5Checksum:'b'.repeat(32)},'\"fresh-etag\"'));
});

test('provider denials retain an actionable error instead of a success receipt',()=>{assert.throws(()=>verifyMove(plannedMove(receipt,current,'\"etag\"'),{error:{status:403}}),/HTTP 403/);});
