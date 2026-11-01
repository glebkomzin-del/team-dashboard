import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ArrowRight, CheckCircle2, ExternalLink, History, LoaderCircle, MessageCircle, Plus, RotateCcw, Sparkles, TriangleAlert } from 'lucide-react'
import { getSession } from '@/auth'
import { navigate } from './planning'
import { dateLabel } from './types'
import {
  citationIsNavigable,
  isCitation,
  isCoverage,
  memoryActionState,
  parseConversationDetail,
  parseCreatedConversation,
  parseConversationList,
  receiptText,
  type Citation,
  type ConversationDetail,
  type ConversationMessage,
  type ConversationSummary,
  type Coverage,
  type MemoryAction,
} from './notes-chat-context'
import './notes-chat.css'

type QuestionRequest = { request_id: string; question: string; conversation_id: string; as_of?: string }
type QuestionResponse = { request_id: string; answer: string; as_of: string; revision: number; archive_revision: number; repeated: boolean; conversation_id?: string; message_id?: string; citations: Citation[]; coverage: Coverage; memory_actions: MemoryAction[] }
type QuestionFailure = { message: string; status: number; code?: string; retryable?: boolean }

const starters = [
  'Welche Entscheidungen sind aktuell festgehalten?',
  'Welche offenen Zusagen und Abhängigkeiten gibt es?',
  'Was hat sich zuletzt geändert?',
]
const newRequestId = () => crypto.randomUUID()
const dateTime = new Intl.DateTimeFormat('de-DE', { dateStyle: 'medium', timeStyle: 'short' })

function AnswerText({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*\n]+\*\*)/g).map((part, index) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={index}>{part.slice(2, -2)}</strong> : part)}</>
}

function errorMessage(status: number, body: unknown): QuestionFailure {
  const value = body && typeof body === 'object' ? body as Record<string, unknown> : {}
  const code = typeof value.code === 'string' ? value.code : undefined
  const retryable = typeof value.retryable === 'boolean' ? value.retryable : undefined
  const message = code === 'provider_outcome_unknown' ? 'Der Ausgang dieser Anfrage ist noch unklar. Sie wird nicht erneut gesendet.'
    : code === 'questions_unavailable' ? 'Die Antwort ist gerade nicht verfügbar. Du kannst dieselbe Anfrage erneut versuchen.'
      : code === 'conversation_not_found' ? 'Dieses Gespräch ist nicht mehr verfügbar. Lade die Gesprächsliste neu.'
        : code === 'conversation_conflict' ? 'Das Gespräch wurde zwischenzeitlich geändert. Lade den aktuellen Stand und versuche es erneut.'
          : code === 'answer_unverified' ? 'Die Antwort konnte nicht ausreichend mit deinen Notizen belegt werden.'
            : code === 'invalid_question' ? 'Die Anfrage konnte nicht verarbeitet werden.'
            : status === 401 || status === 403 ? 'Deine Anmeldung ist nicht mehr gültig. Bitte melde dich erneut an.'
              : status === 405 ? 'Notizen fragen ist für diesen Arbeitsbereich noch nicht eingerichtet.'
                : status === 429 ? 'Das Fragen-Limit für diesen Zeitraum ist erreicht. Bitte versuche es später erneut.'
                  : 'Die Antwort ist gerade nicht verfügbar. Bitte versuche es erneut.'
  return { message, status, code, retryable }
}

function isMemoryAction(value: unknown): value is MemoryAction {
  if (!value || typeof value !== 'object') return false
  const action = value as Record<string, unknown>
  return typeof action.action_id === 'string' && typeof action.kind === 'string' && typeof action.status === 'string'
    && (action.error === undefined || typeof action.error === 'string')
}

function parseQuestionResponse(value: unknown): QuestionResponse | undefined {
  if (!value || typeof value !== 'object') return
  const response = value as Record<string, unknown>
  if (typeof response.request_id !== 'string' || typeof response.answer !== 'string' || typeof response.as_of !== 'string'
    || typeof response.revision !== 'number' || typeof response.archive_revision !== 'number' || typeof response.repeated !== 'boolean'
    || !Array.isArray(response.citations) || !response.citations.every(isCitation) || !isCoverage(response.coverage)
    || (response.memory_actions !== undefined && (!Array.isArray(response.memory_actions) || !response.memory_actions.every(isMemoryAction)))) return
  return { ...response, citations: response.citations, coverage: response.coverage, memory_actions: response.memory_actions || [] } as QuestionResponse
}

async function authHeaders() {
  const session = await getSession()
  return { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}) }
}

async function readJson(response: Response) {
  return response.headers.get('content-type')?.includes('application/json') ? response.json() : undefined
}

function CoverageDetails({ coverage }: { coverage: Coverage }) {
  const isComplete = coverage.mode === 'structured_tasks' || coverage.mode === 'planned_tasks'
  const isWrite = coverage.mode === 'memory_write'
  return <details className="notes-chat__coverage">
    <summary><span>{isComplete ? 'Vollständiger Bereich' : isWrite ? 'Änderungsprüfung' : 'Recherche'}</span><span>{coverage.is_latest ? 'Aktueller Stand' : `Stand bis ${dateLabel(coverage.as_of)}`}</span></summary>
    <div>
      <p>{isComplete
        ? `Alle ${coverage.task_total} Aufgaben wurden geprüft; ${coverage.matched_tasks ?? 0} passen zur Anfrage${coverage.output_truncated ? '. Die Anzahl ist vollständig, die angezeigte Liste wurde gekürzt' : ''}.`
        : isWrite ? 'Der Änderungsauftrag wurde gegen den aktuellen Arbeitsstand geprüft. Die Speicherbestätigung steht direkt über diesem Abschnitt.'
          : `${coverage.retrieval?.hits_returned ?? 0} relevante Treffer aus ${coverage.retrieval?.documents_considered ?? 0} durchsuchten Dokumentteilen in ${coverage.retrieval?.search_rounds ?? 0} Suchrunden${coverage.retrieval?.limited ? '. Das ist eine begrenzte Auswahl, keine vollständige Auflistung' : ''}.`}</p>
      <p>{coverage.is_latest ? `Neuester verfügbarer Ereignistag: ${dateLabel(coverage.as_of)}.` : `Neuester verfügbarer Ereignistag: ${dateLabel(coverage.latest_available_as_of)}.`} {coverage.working_sources} Quellen liegen im Arbeitsstand vor{coverage.archived_only_sources ? `; ${coverage.archived_only_sources} weitere nur im Archiv` : ''}{coverage.pending_jobs ? `; ${coverage.pending_jobs} Quellen werden noch verarbeitet` : ''}.</p>
    </div>
  </details>
}

function ActionReceipt({ action }: { action: MemoryAction }) {
  const state = memoryActionState(action)
  const text = receiptText(action.receipt)
  return <div className={`notes-chat__receipt is-${state}`} role={state === 'failed' ? 'alert' : 'status'}>
    {state === 'confirmed' ? <CheckCircle2 size={18} aria-hidden="true" /> : <TriangleAlert size={18} aria-hidden="true" />}
    <div><strong>{state === 'confirmed' ? 'Änderung gespeichert' : state === 'failed' ? 'Änderung nicht gespeichert' : 'Änderung wird verarbeitet'}</strong><p>{action.error || text || (state === 'confirmed' ? 'Der Arbeitsstand enthält die bestätigte Änderung.' : 'Der endgültige Speicherstand wird noch bestätigt.')}</p></div>
  </div>
}

function Sources({ citations }: { citations: Citation[] }) {
  return <details className="notes-chat__sources"><summary>Quellen zu dieser Antwort · {citations.length}</summary>{citations.length ? <ul>{citations.map(citation => {
    const content = <><span className="notes-chat__citation-id">[{citation.id}]</span><span><strong>{citation.label}</strong>{citation.kind === 'user_memory' && <small>Nutzernotiz · ausdrücklich von dir gespeichert</small>}<small>{citation.kind === 'task_set' ? 'Ereignisstand bis' : 'Ereignisdatum'}: {dateLabel(citation.event_date)}</small><small>{citation.quote}</small></span></>
    if (!citationIsNavigable(citation)) return <li key={citation.id}><div className="notes-chat__source-card">{content}</div></li>
    const query = new URLSearchParams(citation.target.params).toString()
    const href = `#${citation.target.page}${query ? `?${query}` : ''}`
    return <li key={citation.id}><a href={href} onClick={event => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      event.preventDefault(); navigate(citation.target.page, new URLSearchParams(citation.target.params))
    }}>{content}<ExternalLink size={15} aria-hidden="true" /></a></li>
  })}</ul> : <p>Für diese Antwort liegen keine verlinkbaren Quellen vor.</p>}</details>
}

export function NotesChat() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([])
  const [activeId, setActiveId] = useState('')
  const [detail, setDetail] = useState<ConversationDetail>()
  const [question, setQuestion] = useState('')
  const [asOf, setAsOf] = useState('')
  const [loadingList, setLoadingList] = useState(true)
  const [loadingConversation, setLoadingConversation] = useState(false)
  const [creating, setCreating] = useState(false)
  const [pending, setPending] = useState(false)
  const [failure, setFailure] = useState<QuestionFailure>()
  const request = useRef<QuestionRequest | undefined>(undefined)
  const creationId = useRef<string | undefined>(undefined)
  const creationForQuestion = useRef(false)
  const sending = useRef(false)
  const questionRef = useRef<HTMLTextAreaElement>(null)
  const isDisabled = failure?.code === 'questions_disabled' || failure?.status === 405
  const outcomeUnknown = failure?.code === 'provider_outcome_unknown'

  async function fetchList(signal?: AbortSignal) {
    const response = await fetch('/api/working-memory/conversations', { credentials: 'same-origin', cache: 'no-store', headers: await authHeaders(), signal })
    const body = await readJson(response)
    if (!response.ok) throw errorMessage(response.status, body)
    const list = parseConversationList(body)
    if (!list) throw { message: 'Die Gesprächsliste konnte nicht sicher gelesen werden.', status: 503, code: 'questions_unavailable', retryable: true } satisfies QuestionFailure
    setConversations(list)
    setActiveId(current => current && list.some(item => item.conversation_id === current) ? current : list[0]?.conversation_id || '')
    return list
  }

  async function fetchConversation(conversationId: string, signal?: AbortSignal) {
    const response = await fetch(`/api/working-memory/conversations/${encodeURIComponent(conversationId)}`, { credentials: 'same-origin', cache: 'no-store', headers: await authHeaders(), signal })
    const body = await readJson(response)
    if (!response.ok) throw errorMessage(response.status, body)
    const next = parseConversationDetail(body)
    if (!next) throw { message: 'Das Gespräch konnte nicht sicher gelesen werden.', status: 503, code: 'questions_unavailable', retryable: true } satisfies QuestionFailure
    setDetail(next)
    return next
  }

  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      try { await fetchList(controller.signal) }
      catch (error) { if (!controller.signal.aborted) setFailure(error as QuestionFailure) }
      finally { if (!controller.signal.aborted) setLoadingList(false) }
    }
    void load()
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!activeId) return
    const controller = new AbortController()
    async function load() {
      setLoadingConversation(true); setFailure(undefined)
      try { await fetchConversation(activeId, controller.signal) }
      catch (error) { if (!controller.signal.aborted) setFailure(error as QuestionFailure) }
      finally { if (!controller.signal.aborted) setLoadingConversation(false) }
    }
    void load()
    return () => controller.abort()
  }, [activeId])

  async function createConversation(forQuestion = false) {
    if (creating || pending) return
    creationForQuestion.current = forQuestion
    setCreating(true); setFailure(undefined)
    try {
      const conversationId = creationId.current || crypto.randomUUID()
      creationId.current = conversationId
      const response = await fetch('/api/working-memory/conversations', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: await authHeaders(), body: JSON.stringify({ conversation_id: conversationId }) })
      const body = await readJson(response)
      if (!response.ok) throw errorMessage(response.status, body)
      const conversation = parseCreatedConversation(body, conversationId)
      if (!conversation) throw { message: 'Das neue Gespräch konnte nicht sicher angelegt werden.', status: 503, code: 'questions_unavailable', retryable: true } satisfies QuestionFailure
      await fetchList()
      creationId.current = undefined
      setActiveId(conversation.conversation_id)
      setDetail({ conversation, messages: [] })
      setQuestion(''); setAsOf(''); request.current = undefined
      window.setTimeout(() => questionRef.current?.focus(), 0)
      return conversation.conversation_id
    } catch (error) {
      setFailure(error as QuestionFailure)
    } finally { setCreating(false) }
  }

  async function retryLoading() {
    setFailure(undefined)
    setLoadingList(true)
    if (activeId) setLoadingConversation(true)
    try {
      const list = await fetchList()
      if (activeId && list.some(conversation => conversation.conversation_id === activeId)) await fetchConversation(activeId)
    } catch (error) {
      setFailure(error as QuestionFailure)
    } finally {
      setLoadingList(false)
      setLoadingConversation(false)
    }
  }

  async function submit(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const text = question.trim()
    if (!text || pending || sending.current || isDisabled || outcomeUnknown) return
    let conversationId = activeId
    if (!conversationId) conversationId = await createConversation(true) || ''
    if (!conversationId) return
    const existing = request.current
    const payload = existing && existing.question === text && existing.as_of === (asOf || undefined) && existing.conversation_id === conversationId
      ? existing : { request_id: newRequestId(), question: text, conversation_id: conversationId, ...(asOf ? { as_of: asOf } : {}) }
    request.current = payload; sending.current = true; setPending(true); setFailure(undefined)
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 15 * 60_000)
    try {
      let body: unknown
      while (true) {
        const response = await fetch('/api/working-memory/questions', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: await authHeaders(), body: JSON.stringify(payload), signal: controller.signal })
        body = await readJson(response)
        if (!response.ok) throw errorMessage(response.status, body)
        if (response.status !== 202) break
        if (!body || typeof body !== 'object' || (body as Record<string, unknown>).state !== 'processing' || (body as Record<string, unknown>).request_id !== payload.request_id) {
          throw { message: 'Der Verarbeitungsstand konnte nicht sicher zugeordnet werden.', status: 503, code: 'questions_unavailable', retryable: true } satisfies QuestionFailure
        }
        await new Promise<void>((resolve, reject) => {
          const aborted = () => { window.clearTimeout(wait); reject(new DOMException('Aborted', 'AbortError')) }
          const wait = window.setTimeout(() => { controller.signal.removeEventListener('abort', aborted); resolve() }, 1500)
          controller.signal.addEventListener('abort', aborted, { once: true })
        })
      }
      const answer = parseQuestionResponse(body)
      if (!answer || answer.request_id !== payload.request_id || (answer.conversation_id && answer.conversation_id !== conversationId)) throw { message: 'Die Antwort konnte nicht sicher zu dieser Anfrage zugeordnet werden. Bitte versuche dieselbe Anfrage erneut.', status: 503, code: 'questions_unavailable', retryable: true } satisfies QuestionFailure
      await Promise.all([fetchConversation(conversationId, controller.signal), fetchList(controller.signal)])
      setQuestion(''); request.current = undefined
    } catch (error) {
      const next = typeof error === 'object' && error !== null && 'message' in error && 'status' in error ? error as QuestionFailure
        : controller.signal.aborted ? { message: 'Die Antwort wird noch vorbereitet. Du kannst dieselbe Anfrage weiterführen.', status: 503, code: 'questions_unavailable', retryable: true }
          : { message: 'Die Verbindung ist unterbrochen. Bitte versuche es erneut.', status: 0, retryable: true }
      setFailure(next)
      if ([404, 409].includes(next.status)) request.current = undefined
    } finally { window.clearTimeout(timeout); sending.current = false; setPending(false) }
  }

  function chooseConversation(conversationId: string) {
    if (pending || conversationId === activeId) return
    setActiveId(conversationId); setQuestion(''); setAsOf(''); setFailure(undefined); request.current = undefined
  }

  function chooseStarter(starter: string) {
    setQuestion(starter); setFailure(undefined); request.current = undefined
    window.setTimeout(() => questionRef.current?.focus(), 0)
  }

  const messages: ConversationMessage[] = detail?.messages || []
  return <section className="notes-chat" aria-labelledby="notes-chat-title">
    <header className="notes-chat__header"><div><span className="notes-chat__eyebrow"><Sparkles size={15} aria-hidden="true" /> Arbeitsgedächtnis</span><h1 id="notes-chat-title">Notizen fragen</h1><p>Führe belegte Gespräche über deinen Arbeitsstand. Klare Änderungsaufträge werden nur mit sichtbarer Speicherbestätigung übernommen.</p></div><button className="px-button" type="button" onClick={() => void createConversation()} disabled={creating || pending}><Plus size={16} aria-hidden="true" />{creating ? 'Wird angelegt…' : 'Neues Gespräch'}</button></header>
    {isDisabled ? <div className="notes-chat__state" role="status"><MessageCircle size={24} aria-hidden="true" /><h2>Noch nicht eingerichtet</h2><p>Diese Abfrage ist für deinen Arbeitsbereich noch nicht freigeschaltet.</p></div> : <div className="notes-chat__layout">
      <aside className="notes-chat__history" aria-label="Gespräche"><div><History size={16} aria-hidden="true" /><h2>Gespräche</h2></div>{loadingList ? <p role="status">Gespräche werden geladen…</p> : conversations.length ? <ul>{conversations.map(conversation => <li key={conversation.conversation_id}><button type="button" aria-current={activeId === conversation.conversation_id ? 'true' : undefined} onClick={() => chooseConversation(conversation.conversation_id)} disabled={pending}><strong>{conversation.title || 'Neues Gespräch'}</strong><span>{conversation.last_message_preview || 'Noch keine Beiträge'}</span><small>{conversation.message_count} Beiträge · {dateTime.format(new Date(conversation.updated_at))}</small></button></li>)}</ul> : <p>Noch kein gespeichertes Gespräch.</p>}</aside>
      <div className="notes-chat__main">
        {loadingConversation ? <div className="notes-chat__state" role="status"><LoaderCircle className="notes-chat__spinner" size={22} aria-hidden="true" /><p>Gespräch wird geladen…</p></div> : messages.length ? <article className="notes-chat__answer" aria-live="polite"><div className="notes-chat__answer-heading"><MessageCircle size={18} aria-hidden="true" /><div><h2>{detail?.conversation.title || 'Gespräch'}</h2><p>Gespeichert und auf anderen angemeldeten Geräten verfügbar.</p></div></div><div className="notes-chat__transcript" aria-label="Gespräch">{messages.map(message => <article className={`notes-chat__message notes-chat__message--${message.role}`} key={message.message_id}><span>{message.role === 'user' ? 'Du' : <>Antwort {message.coverage && <small>· Ereignisse bis {dateLabel(message.coverage.as_of)}</small>}</>}</span><p>{message.role === 'assistant' ? <AnswerText text={message.content} /> : message.content}</p>{message.role === 'assistant' && <>{message.memory_actions.map(action => <ActionReceipt action={action} key={action.action_id} />)}{message.coverage && <CoverageDetails coverage={message.coverage} />}<Sources citations={message.citations} /></>}</article>)}</div></article>
          : <div className="notes-chat__empty"><MessageCircle size={26} aria-hidden="true" /><h2>{activeId ? 'Beginne dieses Gespräch' : 'Was möchtest du aus deinen Notizen wissen?'}</h2><p>Frage weiter, beziehe dich auf frühere Antworten oder formuliere eine klare Änderung, die gespeichert werden soll.</p><div>{starters.map(starter => <button type="button" key={starter} onClick={() => chooseStarter(starter)}>{starter}<ArrowRight size={15} aria-hidden="true" /></button>)}</div></div>}
        {failure && <div className="notes-chat__error" role="alert"><p>{failure.message}</p>{failure.retryable && <button type="button" onClick={() => request.current || (creationId.current && creationForQuestion.current) ? void submit() : creationId.current ? void createConversation() : void retryLoading()} disabled={pending || creating}><RotateCcw size={15} aria-hidden="true" /> Erneut versuchen</button>}</div>}
        <form className="notes-chat__form" onSubmit={event => void submit(event)} aria-busy={pending}>
          <label htmlFor="notes-chat-question">Frage oder klare Änderung</label><textarea ref={questionRef} id="notes-chat-question" name="question" autoComplete="off" value={question} onChange={event => { setQuestion(event.target.value); setFailure(undefined); if (request.current && event.target.value.trim() !== request.current.question) request.current = undefined }} maxLength={4000} rows={4} placeholder="Zum Beispiel: Was wurde zum Zeitplan entschieden?" disabled={pending} />
          <details className="notes-chat__scope"><summary>Optional: früheren Ereignisstand wählen</summary><label htmlFor="notes-chat-as-of"><span>Ereignisse bis</span><input id="notes-chat-as-of" name="as_of" type="date" autoComplete="off" value={asOf} onChange={event => { setAsOf(event.target.value); setFailure(undefined); request.current = undefined }} disabled={pending} /><small>{asOf ? `Ereignisse berücksichtigen bis ${dateLabel(asOf)}` : 'Standardmäßig wird automatisch der neueste verfügbare Ereignistag verwendet.'}</small></label></details>
          <div><small>{question.length}/4.000 Zeichen</small><button className="px-button px-primary" type="submit" disabled={pending || creating || outcomeUnknown || !question.trim()}>{pending ? <><LoaderCircle className="notes-chat__spinner" size={16} aria-hidden="true" /> Antwort wird gesucht…</> : <>Senden <ArrowRight size={16} aria-hidden="true" /></>}</button></div>
        </form>
      </div>
    </div>}
  </section>
}
