import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY")!;
const OPENAI_API_KEY = Deno.env.get("OPENAI_API_KEY")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const INTERNAL_FUNCTION_SECRET = Deno.env.get("INTERNAL_FUNCTION_SECRET")!;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-internal-secret",
};

type TargetTable = "todos" | "blockers" | "open_items" | "inbox_items";
type EntityType = "todo" | "blocker" | "open_item";
type EvidenceSource = "summary" | "chunk";
type SupabaseAny = any;

interface Candidate {
  entity_type: EntityType;
  target_table: TargetTable;
  id: string;
  title: string;
  description: string | null;
  status: string;
  created_at: string | null;
  meeting_id: string | null;
  meeting_source: string | null;
  similarity?: number;
  lexical_score?: number;
  evidence_snippets: { source: EvidenceSource; text: string }[];
}

interface ResolutionLlmResult {
  target_id: string;
  proposed_status: "done" | "resolved" | "closed" | "rejected";
  evidence_quote: string;
  resolution_reason?: string;
  evidence_source: EvidenceSource;
  confidence: "high" | "medium";
}

interface DuplicateCandidate {
  kind: "bestand" | "inbox";
  table: TargetTable | "inbox_items";
  id: string;
  title: string;
  content: string;
  similarity: number;
}

interface DuplicateLlmResult {
  inbox_item_id: string;
  duplicate_of: {
    kind: "bestand" | "inbox";
    table: TargetTable | "inbox_items";
    id: string;
    title: string;
    reason: string;
  } | null;
}

const FINAL_STATUSES: Record<TargetTable, string[]> = {
  todos: ["done", "cancelled"],
  blockers: ["resolved"],
  open_items: ["closed"],
  inbox_items: ["approved", "rejected"],
};

const PROPOSED_STATUS: Record<TargetTable, "done" | "resolved" | "closed" | "rejected"> = {
  todos: "done",
  blockers: "resolved",
  open_items: "closed",
  inbox_items: "rejected",
};

const STOPWORDS = new Set([
  "der", "die", "das", "und", "oder", "für", "mit", "von", "zur", "zum", "auf", "aus", "dem", "den", "des",
  "ein", "eine", "einer", "eines", "im", "in", "am", "an", "ist", "sind", "wird", "werden", "wurde", "wurden",
  "noch", "dann", "dazu", "über", "unter", "nach", "vor", "bei", "als", "bis", "nicht", "kein", "keine",
  "todo", "blocker", "open", "item", "punkt", "punkte", "thema", "klären", "prüfen",
]);

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function normalizeText(text: string) {
  return text.toLowerCase().normalize("NFKC").replace(/\s+/g, " ").trim();
}

function isQuoteInText(quote: string, texts: string[]) {
  const q = normalizeText(quote);
  if (!q || q.length < 20) return false;
  return texts.some((text) => normalizeText(text).includes(q));
}

function hasCompletionCue(quote: string) {
  const q = normalizeText(quote);
  const explicitNegative = [
    "nicht abgeschlossen", "noch nicht abgeschlossen", "nicht erledigt", "noch nicht erledigt",
    "nicht gelöst", "noch nicht gelöst", "nicht geklärt", "noch nicht geklärt",
    "nicht umgesetzt", "noch nicht umgesetzt", "nicht fertig", "noch offen",
    "weiter offen", "steht noch aus", "stehen noch aus", "nicht finalisiert",
  ];
  if (explicitNegative.some((cue) => q.includes(cue))) return false;
  const positive = [
    "erledigt", "abgeschlossen", "geschlossen", "gelöst", "geklärt", "umgesetzt", "freigegeben",
    "entfallen", "obsolet", "fertig", "finalisiert", "abgenommen", "ist durch", "wurde gelöst",
    "wurde geklärt", "wurde umgesetzt", "wurde abgeschlossen", "wurde erledigt", "ist abgeschlossen",
    "ist erledigt", "ist gelöst", "ist geklärt", "ist umgesetzt",
  ];
  const negative = [
    "wird", "werden", "soll", "sollen", "muss", "müssen", "offen", "in arbeit", "weiter", "später",
    "wenn", "falls", "wäre", "würde", "geplant", "todo", "prüfen", "klären",
  ];
  return positive.some((cue) => q.includes(cue)) && !negative.some((cue) => q.includes(cue));
}

function tokenize(text: string) {
  return Array.from(new Set(
    normalizeText(text)
      .replace(/[^a-z0-9äöüß\s-]/gi, " ")
      .split(/\s+/)
      .map((t) => t.trim())
      .filter((t) => t.length >= 4 && !STOPWORDS.has(t)),
  ));
}

function cosine(a: number[], b: number[]) {
  let dot = 0;
  let an = 0;
  let bn = 0;
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    dot += a[i] * b[i];
    an += a[i] * a[i];
    bn += b[i] * b[i];
  }
  return an && bn ? dot / (Math.sqrt(an) * Math.sqrt(bn)) : 0;
}

function vectorLiteral(vec: number[]) {
  return `[${vec.join(",")}]`;
}

function tableForEntity(entityType: string): TargetTable | null {
  if (entityType === "todo") return "todos";
  if (entityType === "blocker") return "blockers";
  if (entityType === "open_item") return "open_items";
  return null;
}

function entityForTable(table: TargetTable): EntityType {
  if (table === "todos") return "todo";
  if (table === "blockers") return "blocker";
  return "open_item";
}

function titleOfPayload(entityType: EntityType, payload: Record<string, unknown>) {
  return String(payload.title || payload.question_text || payload.commitment_text || `${entityType} ohne Titel`);
}

function buildContent(entityType: EntityType, entity: Record<string, unknown>) {
  switch (entityType) {
    case "todo":
      return `Todo: ${entity.title}. ${entity.description || ""}. Zuständig: ${entity.assignee || "Nicht zugeordnet"}. Priorität: ${entity.priority || "medium"}. Status: ${entity.status || "open"}.${entity.due_date ? " Fällig: " + entity.due_date : ""}`;
    case "blocker":
      return `Blocker: ${entity.title}. ${entity.description || ""}. Gemeldet von: ${entity.reported_by || "Nicht zugeordnet"}. Status: ${entity.status || "active"}.`;
    case "open_item":
      return `Open Item: ${entity.title}. ${entity.description || ""}. Zuständig: ${entity.owner || "Nicht zugeordnet"}. Kategorie: ${entity.category || "general"}. Status: ${entity.status || "open"}.`;
  }
}

async function getEmbeddings(inputs: string[]): Promise<number[][]> {
  if (inputs.length === 0) return [];
  const res = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "text-embedding-3-small", input: inputs }),
  });
  if (!res.ok) throw new Error(`OpenAI embeddings failed: ${await res.text()}`);
  const json = await res.json();
  return json.data.map((row: { embedding: number[] }) => row.embedding);
}

async function callClaude(system: string, user: string, maxTokens = 3000) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-haiku-4-5-20251001",
      max_tokens: maxTokens,
      system,
      messages: [{ role: "user", content: user }],
    }),
  });
  if (!res.ok) throw new Error(`Anthropic failed: ${await res.text()}`);
  const json = await res.json();
  const raw = json.content?.[0]?.text ?? "[]";
  const cleaned = raw.replace(/```json|```/g, "").trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    const start = cleaned.indexOf("[");
    const end = cleaned.lastIndexOf("]");
    if (start >= 0 && end > start) return JSON.parse(cleaned.slice(start, end + 1));
    throw new Error(`Claude returned non-JSON: ${cleaned.slice(0, 300)}`);
  }
}

async function loadMeetingCorpus(supabase: SupabaseAny, meetingId: string) {
  const { data: meeting, error: meetingError } = await supabase
    .from("meetings")
    .select("id,title,meeting_date,executive_summary,ai_summary,source_file")
    .eq("id", meetingId)
    .maybeSingle();
  if (meetingError) throw meetingError;
  if (!meeting) throw new Error(`Meeting nicht gefunden: ${meetingId}`);

  const [{ data: topics, error: topicsError }, { data: chunks, error: chunksError }] = await Promise.all([
    supabase.from("meeting_topics").select("summary").eq("meeting_id", meetingId).order("sequence", { ascending: true }),
    supabase.from("transcript_chunks").select("id,content,chunk_index").eq("meeting_id", meetingId).order("chunk_index", { ascending: true }),
  ]);
  if (topicsError) throw topicsError;
  if (chunksError) throw chunksError;

  const summaryParts = [
    meeting.executive_summary ? `Executive Summary: ${meeting.executive_summary}` : "",
    meeting.ai_summary ? `AI Summary: ${meeting.ai_summary}` : "",
    ...(topics ?? []).map((t: { summary: string | null }) => t.summary ? `Thema: ${t.summary}` : ""),
  ].filter(Boolean);

  const meetingRow = meeting as Record<string, any>;
  return {
    meeting: meetingRow,
    summaryText: summaryParts.join("\n\n"),
    summaryTexts: summaryParts,
    chunks: (chunks ?? []) as { id: string; content: string; chunk_index: number }[],
  };
}

async function loadOpenTargets(supabase: SupabaseAny, meetingId: string, meetingSource: string | null) {
  const [todos, blockers, openItems] = await Promise.all([
    supabase.from("todos").select("*").not("status", "in", `(${FINAL_STATUSES.todos.join(",")})`),
    supabase.from("blockers").select("*").not("status", "in", `(${FINAL_STATUSES.blockers.join(",")})`),
    supabase.from("open_items").select("*").not("status", "in", `(${FINAL_STATUSES.open_items.join(",")})`),
  ]);
  for (const result of [todos, blockers, openItems]) if (result.error) throw result.error;

  const rows = [
    ...((todos.data ?? []) as Record<string, unknown>[]).map((row) => ({ table: "todos" as const, entity_type: "todo" as const, row })),
    ...((blockers.data ?? []) as Record<string, unknown>[]).map((row) => ({ table: "blockers" as const, entity_type: "blocker" as const, row })),
    ...((openItems.data ?? []) as Record<string, unknown>[]).map((row) => ({ table: "open_items" as const, entity_type: "open_item" as const, row })),
  ];

  const dashboardTargets = rows
    .filter(({ row }) => row.meeting_id !== meetingId && (!meetingSource || row.meeting_source !== meetingSource))
    .map(({ table, entity_type, row }) => ({
      entity_type,
      target_table: table,
      id: String(row.id),
      title: String(row.title),
      description: row.description ? String(row.description) : null,
      status: String(row.status),
      created_at: row.created_at ? String(row.created_at) : null,
      meeting_id: row.meeting_id ? String(row.meeting_id) : null,
      meeting_source: row.meeting_source ? String(row.meeting_source) : null,
      evidence_snippets: [],
    })) as Candidate[];

  return dashboardTargets;
}

function bestSnippetsForCandidate(candidate: Candidate, summaryText: string, chunks: { content: string }[]) {
  const titleTokens = tokenize(`${candidate.title} ${candidate.description ?? ""}`);
  const summaryTokens = new Set(tokenize(summaryText));
  const summaryHits = titleTokens.filter((token) => summaryTokens.has(token)).length;
  const snippets: { source: EvidenceSource; text: string }[] = [];
  if (summaryHits >= Math.min(2, titleTokens.length)) snippets.push({ source: "summary", text: summaryText.slice(0, 1800) });

  if (titleTokens.length >= 2) {
    const chunkMatches = chunks
      .map((chunk) => {
        const tokens = new Set(tokenize(chunk.content));
        const hits = titleTokens.filter((token) => tokens.has(token)).length;
        return { chunk, hits };
      })
      .filter((entry) => entry.hits >= 2)
      .sort((a, b) => b.hits - a.hits)
      .slice(0, 2);
    snippets.push(...chunkMatches.map((entry) => ({ source: "chunk" as const, text: entry.chunk.content.slice(0, 1200) })));
  }
  return snippets;
}

async function detectResolutionSuggestions(supabase: SupabaseAny, meetingId: string) {
  const corpus = await loadMeetingCorpus(supabase, meetingId);
  const meetingSource = corpus.meeting.source_file || null;
  const targets = await loadOpenTargets(supabase, meetingId, meetingSource);
  if (targets.length === 0) return { inserted: 0, candidates: 0 };

  const corpusText = [
    `Meeting: ${corpus.meeting.title}. Datum: ${corpus.meeting.meeting_date}.`,
    corpus.summaryText,
    corpus.chunks.slice(0, 8).map((chunk) => chunk.content.slice(0, 1200)).join("\n"),
  ].join("\n").slice(0, 12000);
  const [corpusEmbedding] = await getEmbeddings([`Meeting: ${corpusText}`]);
  const { data: embeddingMatches, error: matchError } = await supabase.rpc("match_embeddings", {
    query_embedding: vectorLiteral(corpusEmbedding),
    match_threshold: 0.72,
    match_count: 80,
  });
  if (matchError) throw matchError;

  const targetByKey = new Map(targets.map((target) => [`${target.entity_type}:${target.id}`, target]));
  const selected = new Map<string, Candidate>();
  for (const match of (embeddingMatches ?? []) as Array<Record<string, any>>) {
    const key = `${match.entity_type}:${match.entity_id}`;
    const candidate = targetByKey.get(key);
    if (!candidate) continue;
    selected.set(candidate.id, { ...candidate, similarity: match.similarity });
  }

  const corpusTokens = new Set(tokenize(corpusText));
  for (const target of targets) {
    const tokens = tokenize(`${target.title} ${target.description ?? ""}`);
    const overlap = tokens.filter((token) => corpusTokens.has(token)).length;
    if (overlap >= 2) {
      const previous = selected.get(target.id);
      selected.set(target.id, { ...(previous ?? target), lexical_score: overlap / Math.max(tokens.length, 1) });
    }
  }

  const candidates = Array.from(selected.values())
    .map((candidate) => ({
      ...candidate,
      evidence_snippets: bestSnippetsForCandidate(candidate, corpus.summaryText, corpus.chunks),
    }))
    .filter((candidate) => candidate.evidence_snippets.length > 0)
    .sort((a, b) => (b.similarity ?? 0) - (a.similarity ?? 0) || (b.lexical_score ?? 0) - (a.lexical_score ?? 0))
    .slice(0, 20);

  if (candidates.length === 0) return { inserted: 0, candidates: 0 };

  const system = [
    "Du prüfst Meeting-Belege gegen bestehende offene Einträge.",
    "Entscheide nur positiv, wenn das Meeting den konkreten Eintrag behandelt UND dessen Abschluss belegt.",
    "Abschluss meint erledigt, abgeschlossen, gelöst, geklärt, umgesetzt, freigegeben, entfallen oder obsolet.",
    "Nur mit wörtlichem zitierbarem Satz aus den Belegen antworten. 'In Arbeit', 'wird weiter besprochen' oder bloße Erwähnung ist kein Abschluss.",
    "Chunk-Belege sind maximal medium. Summary-Belege sind high. Bedingungen/Konjunktive aus Chunks nicht als Abschluss werten.",
    "Für target_table=inbox_items bedeutet ein bestätigter Abschluss: das pending Inbox-Item soll nicht mehr freigegeben werden; proposed_status ist rejected.",
    "Gib in resolution_reason vollständig und konkret auf Deutsch an, warum genau der Ziel-Eintrag abgeschlossen/gelöst/geschlossen ist.",
    "Antworte nur als JSON-Array mit target_id, proposed_status, evidence_quote, resolution_reason, evidence_source, confidence.",
  ].join(" ");

  const user = JSON.stringify({
    meeting: { id: meetingId, date: corpus.meeting.meeting_date, title: corpus.meeting.title },
    candidates: candidates.map((candidate) => ({
      target_id: candidate.id,
      target_table: candidate.target_table,
      target_title: candidate.title,
      target_description: candidate.description,
      target_entity_type: candidate.entity_type,
      target_created_at: candidate.created_at,
      proposed_status: PROPOSED_STATUS[candidate.target_table],
      evidence: candidate.evidence_snippets,
    })),
  });

  let llmResults: ResolutionLlmResult[] = [];
  try {
    llmResults = await callClaude(system, user, 6000);
  } catch (error) {
    console.error("resolution llm failed", error);
    return { inserted: 0, candidates: candidates.length, llm_error: String(error) };
  }

  const allSummaryTexts = [corpus.summaryText, ...corpus.summaryTexts].filter(Boolean);
  const allChunkTexts = corpus.chunks.map((chunk) => chunk.content);
  let inserted = 0;
  for (const result of llmResults) {
    const candidate = candidates.find((entry) => entry.id === result.target_id);
    if (!candidate) continue;
    const quoteTexts = result.evidence_source === "summary" ? allSummaryTexts : allChunkTexts;
    if (!isQuoteInText(result.evidence_quote, quoteTexts)) continue;
    if (!hasCompletionCue(result.evidence_quote)) continue;

    const { data: existing, error: existingError } = await supabase
      .from("inbox_items")
      .select("id,status,payload")
      .eq("entity_type", "resolution")
      .eq("payload->>target_id", candidate.id);
    if (existingError) throw existingError;
    const alreadyPending = (existing ?? []).some((item: { status: string }) => item.status === "pending");
    const alreadyForMeeting = (existing ?? []).some((item: { payload: Record<string, unknown> }) => item.payload?.evidence_meeting_id === meetingId);
    if (alreadyPending || alreadyForMeeting) continue;

    // Payload schema:
    // { target_table, target_id, target_title, proposed_status, evidence_meeting_id,
    //   evidence_meeting_date, evidence_quote, evidence_source, confidence }
    const { error: insertError } = await supabase.from("inbox_items").insert({
      entity_type: "resolution",
      status: "pending",
      source: corpus.meeting.source_file || corpus.meeting.title || "meeting",
      payload: {
        target_table: candidate.target_table,
        target_entity_type: candidate.entity_type,
        target_id: candidate.id,
        target_title: candidate.title,
        target_created_at: candidate.created_at,
        proposed_status: result.proposed_status || PROPOSED_STATUS[candidate.target_table],
        evidence_meeting_id: meetingId,
        evidence_meeting_date: String(corpus.meeting.meeting_date).split("T")[0],
        evidence_quote: result.evidence_quote,
        resolution_reason: result.resolution_reason || result.evidence_quote,
        evidence_source: result.evidence_source,
        confidence: result.evidence_source === "chunk" ? "medium" : result.confidence === "high" ? "high" : "medium",
      },
    });
    if (insertError) throw insertError;
    inserted++;
  }

  return { inserted, candidates: candidates.length };
}

async function detectPendingCompletionInboxItems(supabase: SupabaseAny, meetingId: string) {
  const corpus = await loadMeetingCorpus(supabase, meetingId);
  const meetingSource = corpus.meeting.source_file || null;
  const { data, error } = await supabase
    .from("inbox_items")
    .select("id,entity_type,payload,source,status,created_at")
    .eq("status", "pending")
    .in("entity_type", ["todo", "blocker", "open_item"]);
  if (error) throw error;

  const pending = ((data ?? []) as Array<{ id: string; entity_type: EntityType; payload: Record<string, unknown>; source: string; created_at: string }>)
    .filter((item) => item.payload?.meeting_id !== meetingId && (!meetingSource || item.source !== meetingSource) && !item.payload?.status_suggestion)
    .map((item) => ({
      item,
      candidate: {
        entity_type: item.entity_type,
        target_table: "inbox_items" as const,
        id: item.id,
        title: titleOfPayload(item.entity_type, item.payload),
        description: item.payload.description ? String(item.payload.description) : null,
        status: "pending",
        created_at: item.created_at ? String(item.created_at) : null,
        meeting_id: item.payload.meeting_id ? String(item.payload.meeting_id) : null,
        meeting_source: item.source || null,
        evidence_snippets: [],
      } as Candidate,
    }));
  if (pending.length === 0) return { updated: 0, candidates: 0 };

  const corpusTokens = new Set(tokenize(corpus.chunks.map((chunk) => chunk.content).join("\n")));
  const candidates = pending
    .map(({ item, candidate }) => {
      const tokens = tokenize(`${candidate.title} ${candidate.description ?? ""}`);
      const overlap = tokens.filter((token) => corpusTokens.has(token)).length;
      const evidence_snippets = bestSnippetsForCandidate(candidate, "", corpus.chunks).filter((snippet) => snippet.source === "chunk");
      return { item, candidate: { ...candidate, lexical_score: overlap / Math.max(tokens.length, 1), evidence_snippets } };
    })
    .filter((entry) => (entry.candidate.lexical_score ?? 0) > 0 && entry.candidate.evidence_snippets.length > 0)
    .sort((a, b) => (b.candidate.lexical_score ?? 0) - (a.candidate.lexical_score ?? 0))
    .slice(0, 20);
  if (candidates.length === 0) return { updated: 0, candidates: 0 };

  const system = [
    "Du prüfst, ob pending Inbox-Einträge durch ein späteres Meeting bereits erledigt sind.",
    "Markiere nur erledigt, wenn ein Transkript-Chunk den konkreten Eintrag behandelt UND den Abschluss belegt.",
    "Bloße Erwähnung, Planung, 'noch offen', 'noch nicht abgeschlossen' oder Fortschritt ohne Abschluss ist kein erledigt.",
    "Gib reason vollständig und konkret auf Deutsch an. evidence_quote muss wörtlich aus einem Chunk stammen.",
    "Antworte nur als JSON-Array mit target_id, evidence_quote, reason, confidence.",
  ].join(" ");
  const user = JSON.stringify({
    meeting: { id: meetingId, date: corpus.meeting.meeting_date, title: corpus.meeting.title },
    candidates: candidates.map(({ candidate }) => ({
      target_id: candidate.id,
      target_entity_type: candidate.entity_type,
      target_title: candidate.title,
      target_description: candidate.description,
      evidence: candidate.evidence_snippets,
    })),
  });

  let results: Array<{ target_id: string; evidence_quote: string; reason: string; confidence: "high" | "medium" }> = [];
  try {
    results = await callClaude(system, user, 4000);
  } catch (error) {
    console.error("pending completion llm failed", error);
    return { updated: 0, candidates: candidates.length, llm_error: String(error) };
  }

  const allChunkTexts = corpus.chunks.map((chunk) => chunk.content);
  let updated = 0;
  for (const result of results) {
    const entry = candidates.find(({ candidate }) => candidate.id === result.target_id);
    if (!entry) continue;
    if (!isQuoteInText(result.evidence_quote, allChunkTexts)) continue;
    if (!hasCompletionCue(result.evidence_quote)) continue;
    const { error: updateError } = await supabase.from("inbox_items").update({
      payload: {
        ...entry.item.payload,
        status_suggestion: {
          kind: "done",
          evidence_meeting_id: meetingId,
          evidence_meeting_date: String(corpus.meeting.meeting_date).split("T")[0],
          evidence_quote: result.evidence_quote,
          evidence_source: "chunk",
          reason: result.reason,
          confidence: result.confidence === "high" ? "high" : "medium",
        },
      },
    }).eq("id", entry.item.id);
    if (updateError) throw updateError;
    updated++;
  }
  return { updated, candidates: candidates.length };
}

async function detectDuplicateInboxItems(supabase: SupabaseAny, meetingId: string) {
  const { data: meeting } = await supabase.from("meetings").select("source_file,title").eq("id", meetingId).maybeSingle();
  const meetingRow = meeting as Record<string, any> | null;
  const sources = [meetingRow?.source_file, meetingRow?.title].filter(Boolean) as string[];

  const baseQuery = () => supabase
    .from("inbox_items")
    .select("*")
    .eq("status", "pending")
    .in("entity_type", ["todo", "blocker", "open_item"]);
  const byMeeting = await baseQuery().eq("payload->>meeting_id", meetingId);
  if (byMeeting.error) throw byMeeting.error;
  const bySource = sources.length > 0 ? await baseQuery().in("source", sources) : { data: [], error: null };
  if (bySource.error) throw bySource.error;
  const inboxItemsById = new Map<string, Record<string, any>>();
  for (const item of [...(byMeeting.data ?? []), ...(bySource.data ?? [])]) inboxItemsById.set(item.id, item);
  const inboxItems = Array.from(inboxItemsById.values());
  const newItems = (inboxItems ?? []).filter((item) => !item.payload?.duplicate_of) as Array<{ id: string; entity_type: EntityType; payload: Record<string, unknown>; created_at: string }>;
  if (newItems.length === 0) return { updated: 0, checked: 0 };

  const newContents = newItems.map((item) =>
    buildContent(item.entity_type, { ...item.payload, title: titleOfPayload(item.entity_type, item.payload) })
  );
  const newEmbeddings = await getEmbeddings(newContents);
  const duplicateJobs: { item: Record<string, unknown>; content: string; candidates: DuplicateCandidate[] }[] = [];

  for (let i = 0; i < newItems.length; i++) {
    const item = newItems[i] as { id: string; entity_type: EntityType; payload: Record<string, unknown>; created_at: string };
    const embedding = newEmbeddings[i];
    const { data: matches, error: matchError } = await supabase.rpc("match_embeddings", {
      query_embedding: vectorLiteral(embedding),
      match_threshold: 0.82,
      match_count: 20,
    });
    if (matchError) throw matchError;

    const candidates: DuplicateCandidate[] = [];
    for (const match of (matches ?? []) as Array<Record<string, any>>) {
      const table = tableForEntity(match.entity_type);
      if (!table) continue;
      const { data: row } = await supabase.from(table).select("*").eq("id", match.entity_id).maybeSingle();
      const targetRow = row as Record<string, any> | null;
      if (!targetRow || FINAL_STATUSES[table].includes(targetRow.status)) continue;
      candidates.push({ kind: "bestand", table, id: targetRow.id, title: targetRow.title, content: match.content, similarity: match.similarity });
    }

    const { data: olderPending, error: olderError } = await supabase
      .from("inbox_items")
      .select("id,entity_type,payload,created_at")
      .eq("status", "pending")
      .in("entity_type", ["todo", "blocker", "open_item"])
      .lt("created_at", item.created_at)
      .limit(80);
    if (olderError) throw olderError;
    const olderContents = (olderPending ?? []).map((old: { entity_type: EntityType; payload: Record<string, unknown> }) =>
      buildContent(old.entity_type, { ...old.payload, title: titleOfPayload(old.entity_type, old.payload) })
    );
    const olderEmbeddings = await getEmbeddings(olderContents);
    (olderPending ?? []).forEach((old: { id: string; entity_type: EntityType; payload: Record<string, unknown> }, idx: number) => {
      const similarity = cosine(embedding, olderEmbeddings[idx]);
      if (similarity >= 0.82) {
        candidates.push({
          kind: "inbox",
          table: "inbox_items",
          id: old.id,
          title: titleOfPayload(old.entity_type, old.payload),
          content: olderContents[idx],
          similarity,
        });
      }
    });

    const topCandidates = candidates.sort((a, b) => b.similarity - a.similarity).slice(0, 5);
    if (topCandidates.length > 0) duplicateJobs.push({ item, content: newContents[i], candidates: topCandidates });
  }

  if (duplicateJobs.length === 0) return { updated: 0, checked: newItems.length };

  const system = [
    "Du prüfst mögliche Dubletten.",
    "Eine Dublette ist dasselbe reale Anliegen, nicht nur dasselbe Projektthema.",
    "Gleiche konkrete Sache und gleicher Zuständigkeitskontext spricht für Dublette; anderes konkretes To-do im selben Thema ist keine Dublette.",
    "Antworte nur als JSON-Array: inbox_item_id und duplicate_of oder null. duplicate_of enthält kind, table, id, title, reason.",
  ].join(" ");
  const user = JSON.stringify({
    items: duplicateJobs.map((job) => ({
      inbox_item_id: job.item.id,
      new_item: job.content,
      candidates: job.candidates,
    })),
  });

  let results: DuplicateLlmResult[] = [];
  try {
    results = await callClaude(system, user, 2500);
  } catch (error) {
    console.error("duplicate llm failed", error);
    return { updated: 0, checked: newItems.length, llm_error: String(error) };
  }

  let updated = 0;
  for (const result of results) {
    if (!result.duplicate_of) continue;
    const job = duplicateJobs.find((entry) => entry.item.id === result.inbox_item_id);
    const match = job?.candidates.find((candidate) => candidate.id === result.duplicate_of?.id && candidate.table === result.duplicate_of?.table);
    if (!job || !match) continue;
    const item = job.item as { id: string; payload: Record<string, unknown> };
    const { error } = await supabase.from("inbox_items").update({
      payload: {
        ...item.payload,
        duplicate_of: {
          kind: match.kind,
          table: match.table,
          id: match.id,
          title: match.title,
          reason: result.duplicate_of.reason,
        },
      },
    }).eq("id", item.id);
    if (error) throw error;
    updated++;
  }

  return { updated, checked: newItems.length };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (!INTERNAL_FUNCTION_SECRET || req.headers.get("x-internal-secret") !== INTERNAL_FUNCTION_SECRET) {
    return jsonResponse({ error: "Unauthorized" }, 401);
  }

  try {
    const { meeting_id, backfill_days } = await req.json();
    const supabase: SupabaseAny = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    let meetingIds: string[] = [];
    if (meeting_id) {
      meetingIds = [meeting_id];
    } else if (backfill_days) {
      const since = new Date(Date.now() - Number(backfill_days) * 24 * 60 * 60 * 1000).toISOString();
      const { data, error } = await supabase.from("meetings").select("id").gte("meeting_date", since).order("meeting_date", { ascending: false });
      if (error) throw error;
      meetingIds = (data ?? []).map((row: { id: string }) => row.id);
    } else {
      return jsonResponse({ error: "meeting_id oder backfill_days erforderlich" }, 400);
    }

    const results = [];
    for (const id of meetingIds) {
      const resolutions = await detectResolutionSuggestions(supabase, id);
      const pendingCompletions = await detectPendingCompletionInboxItems(supabase, id);
      const duplicates = await detectDuplicateInboxItems(supabase, id);
      results.push({ meeting_id: id, resolutions, pendingCompletions, duplicates });
    }

    return jsonResponse({ success: true, results });
  } catch (error) {
    return jsonResponse({ error: error instanceof Error ? error.message : String(error) }, 500);
  }
});
