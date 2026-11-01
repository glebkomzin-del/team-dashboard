import assert from 'node:assert/strict'
import { test } from 'node:test'
import fs from 'node:fs'
import ts from 'typescript'

// Actual MemoryShell JSX; deterministic hooks, route/preferences and inert effects
// isolate its status derivation. No auth, API, browser storage or provider executes.
let source=fs.readFileSync(new URL('../src/pages/MemoryApp.tsx',import.meta.url),'utf8')
const iconNames=source.match(/import \{ ([^}]+) \} from 'lucide-react'/)[1]
source=source.replace(/^import .*\n/gm,'')
source=`import {isolationMessage,operationsStatus,processingFence,processingReason} from '../src/features/working-memory/processing-status.ts';
let hook=0;
const useEffect=()=>{};const useRef=value=>({current:value});
const useState=()=>[[false,'',{},null,'',0,globalThis.__shellOperations][hook++ % 7],()=>{}];
const useRoute=()=>({page:'uebersicht'});const usePreferences=()=>({density:'normal'});
const pageNames=new Proxy({},{get:(_,key)=>String(key)});const numberLabel=String;const SUPABASE_URL='fixture.invalid';
const ${iconNames.split(',').map(name=>name.trim()+'=()=>null').join(',')};
const ProductivityPage=()=>null,NotesChat=()=>null,ArchivePage=()=>null,SettingsPage=()=>null;
`+source
const generated=new URL('.memory-shell-status-test.mjs',import.meta.url)
fs.writeFileSync(generated,ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,jsx:ts.JsxEmit.ReactJSX}}).outputText)
const {MemoryShell}=await import(generated.href)
process.on('exit',()=>fs.unlinkSync(generated))
const walk=node=>!node||typeof node!=='object'?[]:Array.isArray(node)?node.flatMap(walk):[node,...walk(node.props?.children)]
const text=node=>node==null||typeof node==='boolean'?'':typeof node!=='object'?String(node):Array.isArray(node)?node.map(text).join(' '):text(node.props?.children)
const fixture=()=>({mode:'production',worker:{state:'paused',reason:'transport_failed',job_id:'previous-source'},processing:{config:{enabled:true},accounted_micro_usd:0,pending_count:44,isolated_count:13,blocking_job:null,jobs:[...Array.from({length:13},(_,i)=>({id:`isolated-${i}`,title:`Isolated source ${i}`,event_date:'2026-09-08',state:'review',reason:'validation_failed',technical_isolation:true})),{id:'new-source',title:'Current lease',event_date:'2026-09-09',state:'running',reason:null,technical_isolation:false,lease_until:'2027-02-28T13:10:00Z'},...Array.from({length:30},(_,i)=>({id:`queued-${i}`,state:'queued',reason:null,technical_isolation:false}))]}})
const banner=data=>{globalThis.__shellOperations={data,checkedAt:'2027-01-01T12:00:00Z'};const nodes=walk(MemoryShell({}));return nodes.find(node=>node.type==='section'&&node.props['aria-label']==='Verarbeitungsstatus')}

test('actual global banner uses the isolated job ledger reason when a proved active lease supersedes old worker transport failure',()=>{
 const originalNow=Date.now;Date.now=()=>Date.parse('2027-01-01T12:00:00Z')
 try {
  const data=fixture(), rendered=text(banner(data))
  assert.match(rendered,/Beim letzten Abruf war eine Quelle zur Verarbeitung belegt/)
  assert.match(rendered,/Isolated source 0/)
  assert.match(rendered,/validation_failed/)
  assert.match(rendered,/Ergebnis hat die Prüfung nicht bestanden/)
  assert.doesNotMatch(rendered,/transport_failed|Speicherbestätigung fehlt/)
  assert.match(rendered,/44\s+Quellen noch unvollständig/)
  assert.match(rendered,/13 Quellen sind technisch isoliert und noch nicht vollständig übernommen/)
  // Even if old worker job_id still matches an isolated ledger row, its own
  // validation reason must win over the stale worker transport reason.
  data.worker.job_id='isolated-0'
  assert.doesNotMatch(text(banner(data)),/transport_failed/)
 } finally {Date.now=originalNow}
})

test('global banner only suppresses stale reason with positive lease proof; invalid dates and unavailable remain guarded',()=>{
 const originalNow=Date.now;Date.now=()=>Date.parse('2027-01-01T12:00:00Z')
 try {
  const data=fixture();data.processing.jobs[13].lease_until='2027-02-30T13:10:00Z'
  assert.match(text(banner(data)),/Automatische Verarbeitung ist angehalten/)
  assert.match(text(banner(data)),/transport_failed/)
  data.processing.jobs[13].lease_until='2028-02-29T13:10:00.123456+02:00'
  data.worker={state:'unavailable',reason:'storage_unavailable'}
  assert.match(text(banner(data)),/unbekannt/)
  assert.match(text(banner(data)),/storage_unavailable/)
  assert.doesNotMatch(text(banner(data)),/Beim letzten Abruf war eine Quelle zur Verarbeitung belegt/)
 } finally {Date.now=originalNow}
})
