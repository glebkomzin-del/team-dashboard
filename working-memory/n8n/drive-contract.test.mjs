import test from 'node:test';
import assert from 'node:assert/strict';
import { prepareInventory, assembleOriginal } from './drive-contract.mjs';
const DOCX='application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const file = (id='one', changes={}) => ({id,name:'2026-09-08 Finance.docx',mimeType:DOCX,version:'2',modifiedTime:'2026-09-08T09:00:00Z',parents:['inbox'],trashed:false,...changes});
const config = {folderIds:['inbox']};
const page = files => ({files,incompleteSearch:false});
test('all pages including empty intermediate pages, chronological order', () => {
 const result=prepareInventory([{...page([file()]),nextPageToken:'a'},{...page([]),nextPageToken:'b'},page([file('two',{name:'2026-06-18 Earlier.txt'})])],config);
 assert.deepEqual(result.map(f=>f.id),['two','one']); assert.equal(result[1].source_id,'drive:one');
});
test('incomplete, capped, cyclic and duplicate inventories fail closed', () => {
 for(const pages of [[{...page([]),incompleteSearch:true}],[{...page([file()]),nextPageToken:'a'}],[{...page([]),nextPageToken:'a'},{...page([]),nextPageToken:'a'},page([])],[{...page([file()]),nextPageToken:'a'},page([file()])],[page([]),page([])]]) assert.throws(()=>prepareInventory(pages,config));
 assert.throws(()=>prepareInventory([page([file(),file('two')])],{...config,maxFiles:1}));
});
test('explicit scope cannot silently fall back to another source', () => {
 assert.throws(()=>prepareInventory([page([file()])],{...config,selectedIds:['missing']}));
 assert.throws(()=>prepareInventory([page([file()])],{...config,selectedIds:[]}));
 assert.throws(()=>prepareInventory([page([file('one',{parents:['other']})])],config));
 assert.equal(prepareInventory([page([file(),file('two')])],{...config,selectedIds:['two']})[0].id,'two');
});
test('only observed date prefix, DOCX and versioned metadata', () => {
 for(const changes of [{name:'Finance without date.docx'},{name:'2026-02-30 Finance.docx'},{mimeType:'application/pdf'},{mimeType:'text/plain'},{version:null},{modifiedTime:'unknown'},{trashed:true}]) assert.throws(()=>prepareInventory([page([file('one',changes)])],config));
 const doc=prepareInventory([page([file('doc')])],config)[0];assert.equal(doc.title,'Finance');
});
test('verbatim text with line endings retained; no model or import implied', () => {
 const before=prepareInventory([page([file()])],config)[0]; const text='00:01 Gleb: Beispiel.\r\n\r\n';
 const result=assembleOriginal(before,file(),text);assert.equal(result.transcript,text);assert.equal(result.intake_status,'read_verified_not_imported');assert.equal(result.drive_metadata.version,'2');
});
test('changed version, title, owner folder or MIME during read is rejected', () => {
 const before=prepareInventory([page([file()])],config)[0];
 for(const changes of [{version:'3'},{name:'2026-09-08 Renamed.docx'},{modifiedTime:'2026-09-09T10:00:00Z'},{parents:['other']},{trashed:true},{mimeType:'application/pdf'}]) assert.throws(()=>assembleOriginal(before,file('one',changes),'Original'));
});
test('empty, excessive or damaged decoding fails without truncating', () => {
 const before=prepareInventory([page([file()])],config)[0];for(const text of ['', '  ', 'x'.repeat(140001),'bad\uFFFD','bad\uD800']) assert.throws(()=>assembleOriginal(before,file(),text));
});
test('same names with different IDs stay separate; modified versions remain visible', () => {
 const result=prepareInventory([page([file(),file('two')])],config); assert.equal(result.length,2);assert.notEqual(result[0].source_id,result[1].source_id);
 assert.equal(prepareInventory([page([file('one',{version:'3'})])],config)[0].version,'3');
});

test('observed names without date separator retain their exact title and date', () => {
 for (const name of ['2026-06-29Kennenlernen DatenSpezialisten','2026-06-30Abstimmung','2026-06-30JF Group Controlling']) {
  const result=prepareInventory([page([file('one',{name})])],config)[0];
  assert.equal(result.event_date,name.slice(0,10)); assert.equal(result.title,name.slice(10));
 }
 assert.throws(()=>prepareInventory([page([file('one',{name:'2026-06-30'})])],config));
});
test('archive read limit is explicit and never relaxes the default model intake limit', () => {
 const before=prepareInventory([page([file()])],config)[0]; const text='x'.repeat(140001);
 assert.throws(()=>assembleOriginal(before,file(),text));
 assert.equal(assembleOriginal(before,file(),text,{maxCharacters:4000000}).transcript,text);
 for (const maxCharacters of [0,-1,4000001,NaN,1.5]) assert.throws(()=>assembleOriginal(before,file(),'x',{maxCharacters}));
});
