import assert from 'node:assert/strict'
import { test } from 'node:test'
import fs from 'node:fs'
import ts from 'typescript'

// Render the actual panel JSX with deterministic loaded state. Dependencies that
// access auth, HTTP or browser dialogs are inert; no recovery write is executed.
let source = fs.readFileSync(new URL('../src/features/working-memory/ProcessingPanel.tsx', import.meta.url), 'utf8')
source = source.replace("import { useEffect, useState } from 'react'", `
let hook = 0;
const useEffect = () => {};
const useState = () => {
  const value = [true, 0, undefined, {attempt: 0, data: globalThis.__panelData, checkedAt: '2026-10-06T12:00:00Z'}][hook++ % 4];
  return [value, id => {globalThis.__selectedJob = id}];
};`)
source = source.replace("import { dateLabel, getMemory, numberLabel } from './types'", "const dateLabel = value => value; const getMemory = () => { throw new Error('HTTP must never run in this test') }; const numberLabel = String;")
source = source.replace("import { RecoveryDialog } from './RecoveryDialog'", 'const RecoveryDialog = () => null;')
source = source.replace("import { GenerationReviews } from './GenerationReviews'", 'const GenerationReviews = () => null;')
source = source.replaceAll("from './processing-status'", "from '../src/features/working-memory/processing-status.ts'")
const generated = new URL('.processing-panel-test.mjs', import.meta.url)
fs.writeFileSync(generated, ts.transpileModule(source, {compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.ReactJSX}}).outputText)
const { ProcessingPanel } = await import(generated.href)
process.on('exit', () => fs.unlinkSync(generated))
const walk = node => !node || typeof node !== 'object' ? [] : Array.isArray(node) ? node.flatMap(walk) : [node, ...walk(node.props?.children)]
const text = node => node == null || typeof node === 'boolean' ? '' : typeof node !== 'object' ? String(node) : Array.isArray(node) ? node.map(text).join(' ') : text(node.props?.children)
const blocker = { id:'global-blocker', title:'Kurze Abstimmung', event_date:'2026-09-09', state:'review', reason:'transport_failed', technical_isolation:false }
const isolated = Array.from({length:13}, (_,i) => ({id:`isolated-${i}`, title:`Isolated ${i}`, event_date:'2026-09-08', state:'review', reason:'validation_failed', technical_isolation:true}))
const queued = Array.from({length:30}, (_,i) => ({id:`queued-${i}`, title:`Queued ${i}`, event_date:'2026-09-10', state:'queued', reason:null, technical_isolation:false}))
const fixture = () => ({mode:'production', worker:{state:'paused', reason:'transport_failed'}, processing:{config:{enabled:true, automatic_from:null, budget_micro_usd:null}, accounted_micro_usd:0, pending_count:44, isolated_count:13, jobs:[...isolated,blocker,...queued], blocking_job:{...blocker, source_id:'source-blocker'}}})
const render = data => {globalThis.__panelData=data;globalThis.__selectedJob=undefined;return walk(ProcessingPanel({}))}
const rows = nodes => nodes.filter(node => node.type === 'article')
const recoveryButtons = nodes => nodes.filter(node => node.type === 'button' && text(node).includes('Verarbeitung prüfen / wiederaufnehmen'))

test('actual JSX shows full blocker first with date, state, reason and the existing ID-bound recovery CTA; all44 remain', () => {
 const data=fixture(), nodes=render(data), articles=rows(nodes)
 assert.equal(articles.length,44)
 assert.match(text(articles[0]), /Kurze Abstimmung/)
 assert.match(text(articles[0]), /Blockiert weitere Verarbeitung ·\s+2026-09-09/)
 assert.match(text(articles[0]), /Verarbeitung wartet auf Klärung/)
 assert.match(text(articles[0]), /transport_failed/)
 recoveryButtons(walk(articles[0]))[0].props.onClick()
 assert.equal(globalThis.__selectedJob, blocker.id)
 assert.deepEqual(articles.slice(1,4).map(row=>text(walk(row).find(node=>node.type==='h3'))), isolated.slice(0,3).map(job=>job.title))
 assert.deepEqual(articles.slice(1).map(row=>text(walk(row).find(node=>node.type==='h3'))), [...isolated,...queued].map(job=>job.title))
 assert.match(text(nodes), /13 Quellen sind technisch isoliert und noch nicht vollständig übernommen/)
})

test('missing full job displays known blocker safely without a synthetic recovery CTA', () => {
 const data=fixture();data.processing.jobs=data.processing.jobs.filter(job=>job.id!==blocker.id)
 const articles=rows(render(data))
 assert.match(text(articles[0]), /Kurze Abstimmung/)
 assert.match(text(articles[0]), /Verarbeitungsprüfung ist noch nicht verfügbar/)
 assert.equal(recoveryButtons(walk(articles[0])).length,0)
 assert.equal(articles.length,44)
})

test('owner read-only stays guarded; explicit no-blocker preserves chronological list and stale disabled stays unknown', () => {
 const data=fixture();data.read_only=true
 assert.equal(recoveryButtons(render(data)).length,0)
 data.processing.blocking_job=null
 data.worker={state:'disabled'}
 const nodes=render(data)
 assert.match(text(nodes), /bestätigt den aktuellen Verarbeitungsstand nicht|Lesemodus ausgeschaltet/)
 assert.doesNotMatch(text(nodes), /Blockiert weitere Verarbeitung/)
 assert.match(text(rows(nodes)[0]), /Isolated 0/)
 delete data.read_only
 assert.match(text(render(data)), /bestätigt den aktuellen Verarbeitungsstand nicht/)
})


test('a current running lease replaces old paused banner/reason while preserving the44 rows and owner guards', () => {
 const realNow=Date.now;Date.now=()=>Date.parse('2026-10-06T13:00:00Z')
 try {
  const data=fixture();data.processing.blocking_job=null
  Object.assign(data.processing.jobs[13],{state:'running',reason:null,lease_until:'2026-10-06T13:10:00Z'})
  const nodes=render(data)
  assert.match(text(nodes),/Beim letzten Abruf war eine Quelle zur Verarbeitung belegt/)
  assert.doesNotMatch(text(nodes),/Automatische Verarbeitung ist angehalten|transport_failed|Speicherbestätigung fehlt/)
  assert.equal(rows(nodes).length,44)
  assert.deepEqual(rows(nodes).slice(0,3).map(row=>text(walk(row).find(node=>node.type==='h3'))),isolated.slice(0,3).map(job=>job.title))
  data.processing.jobs[13].lease_until='2026-10-06T12:59:59Z'
  assert.match(text(render(data)),/Automatische Verarbeitung ist angehalten/)
  data.processing.jobs[13].lease_until='2026-10-06T13:10:00Z'
  data.read_only=true
  assert.equal(recoveryButtons(render(data)).length,0)
  assert.doesNotMatch(text(render(data)),/Beim letzten Abruf war eine Quelle zur Verarbeitung belegt/)
 } finally {Date.now=realNow}
})
