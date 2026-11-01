// index.ts — Main Deno.serve handler for the semantic-search edge function

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";
import { planRetrieval, planWithHaiku } from "./retrieval_planner.ts";
import {
  getLatestMeetings,
  getEntitiesByStatus,
  getEntitiesByProject,
  getEntitiesInTimeRange,
  getActivityDelta,
  getMeetingsInRange,
  getRiskSignals,
  getDecisions,
  getEntityCountsOnly,
  getStatusFilteredCounts,
  searchByTopicAnchor,
  countTable,
  extractDecisionsFromMeetings,
  getMeetingsByPerson,
  getMeetingsMentioningPerson,
  getEntitiesByPersonFlexible,
  getCommitmentsByPerson,
  searchDecisionsByKeywords,
  getOpenLoopsByKeyword,
  type ActivityRow,
  type MeetingRow,
} from "./sql_retriever.ts";
import { getPersonAssigneeVariants } from "./entity_resolver.ts";
import { semanticVectorSearch } from "./vector_search.ts";
import { loadLiveEntities } from "./live_entity_loader.ts";
import {
  rankAndScore,
  inferRelations,
  rawToScoredResults,
  vectorToScoredResults,
  type ScoredResult,
} from "./ranking.ts";
import {
  buildContextPacket,
  computeAggregations,
  buildAudit,
  formatAuditAsMarkdown,
  type RiskSignals,
  type RetrievalAudit,
} from "./context_builder.ts";
import {
  buildSystemPrompt,
  callClaude,
  streamClaudeResponse,
  type ChatMessage,
} from "./claude_client.ts";

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function sseHeaders(): Record<string, string> {
  return {
    ...CORS_HEADERS,
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
  };
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }

  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const {
      query,
      match_threshold = 0.3,
      match_count = 20,
      history = [],
      stream = false,
      prev_audit = null,
    } = await req.json();

    if (!query || typeof query !== "string") {
      return jsonResponse({ error: "Missing or invalid 'query' field" }, 400);
    }

    // Warm-ping guard — no LLM, no DB, no Embedding
    if (query === "ping" || query === "__warmup__") {
      return new Response(
        JSON.stringify({ status: "warm", timestamp: Date.now() }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      );
    }

    const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
    const supabaseKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const sb = createClient(supabaseUrl, supabaseKey);

    const now = new Date();

    // Step 1: Plan the retrieval (Haiku LLM planner with regex fallback)
    // supabase client passed for dynamic person lexicon loading (cached 5 min)
    const intent = await planWithHaiku(query, history, now, sb);
    console.log(`[semantic-search] intent=${intent.intent} mode=${intent.retrievalMode} people=[${intent.persons}] anchors=[${intent.topic_anchors}] flags=${JSON.stringify(intent.retrieval_flags)}`);

    // ── Short-circuit: source_audit — return prev_audit without DB query ──
    if (intent.intent === "source_audit") {
      const answer = prev_audit
        ? formatAuditAsMarkdown(prev_audit as RetrievalAudit)
        : "Kein vorheriger Abruf verfügbar. Stelle zuerst eine inhaltliche Frage, dann kann ich dir zeigen, welche Daten ich verwendet habe.";

      if (stream) {
        const encoder = new TextEncoder();
        const sseStream = new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "matches", data: [] })}\n\n`));
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "delta", text: answer })}\n\n`));
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "done" })}\n\n`));
            controller.close();
          },
        });
        return new Response(sseStream, { headers: sseHeaders() });
      } else {
        return jsonResponse({ matches: [], answer, intent: "source_audit", retrievalMode: "source_audit" });
      }
    }

    // ── Short-circuit: count_query — run status-filtered COUNT queries only ──
    if (intent.intent === "count_query") {
      const statusCounts = await getStatusFilteredCounts(sb);

      const fmtStatusBlock = (label: string, statuses: Record<string, number>): string => {
        const parts = Object.entries(statuses)
          .filter(([, n]) => n > 0)
          .map(([s, n]) => `${n} ${s}`);
        return parts.length > 0 ? `${label}: ${parts.join(", ")}` : `${label}: keine Einträge`;
      };

      const countLines = [
        fmtStatusBlock("Todos", statusCounts.todos),
        fmtStatusBlock("Blocker", statusCounts.blockers),
        fmtStatusBlock("Offene Punkte (open_loops)", statusCounts.open_loops),
        `Meetings: ${statusCounts.meetings_last_7_days} letzte 7 Tage, ${statusCounts.meetings_last_30_days} letzte 30 Tage, ${statusCounts.meetings_total} gesamt`,
      ].join("\n");

      const countContext = `=== ANZAHL ALLER EINTRÄGE ===\n${countLines}\n\nHeutiges Datum: ${now.toISOString().substring(0, 10)}`;

      const flatCounts: Record<string, number> = {
        todos: Object.values(statusCounts.todos).reduce((s, n) => s + n, 0),
        blockers: Object.values(statusCounts.blockers).reduce((s, n) => s + n, 0),
        open_loops: Object.values(statusCounts.open_loops).reduce((s, n) => s + n, 0),
        meetings: statusCounts.meetings_total,
      };

      const chatMessages: ChatMessage[] = [];
      for (const msg of history) {
        const content = msg.content ?? msg.text ?? "";
        if ((msg.role === "user" || msg.role === "assistant") && content.trim().length > 0) {
          chatMessages.push({ role: msg.role, content });
        }
      }
      chatMessages.push({ role: "user", content: query });

      const simplePrompt = `Du bist ein Projektmanagement-Assistent. Antworte NUR auf Basis der bereitgestellten Zahlen. Keine Emojis.\n\nDATEN:\n${countContext}`;

      const countAudit: RetrievalAudit = buildAudit(
        intent,
        ["meetings", "todos", "blockers", "open_loops"],
        flatCounts,
        0, 0, 0,
        false,
        [],
        [],
      );

      if (stream) {
        const encoder = new TextEncoder();
        const claudeStream = streamClaudeResponse(simplePrompt, chatMessages, "count_query");
        const reader = claudeStream.getReader();

        const outputStream = new ReadableStream({
          async start(controller) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "matches", data: [] })}\n\n`));
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "audit", audit: countAudit })}\n\n`));
            try {
              while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                controller.enqueue(value);
              }
            } catch (err) {
              controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "error", error: String(err) })}\n\n`));
            }
            controller.close();
          },
        });
        return new Response(outputStream, { headers: sseHeaders() });
      } else {
        const answer = await callClaude(simplePrompt, chatMessages, "count_query");
        return jsonResponse({ matches: [], answer, intent: "count_query", audit: countAudit });
      }
    }

    // ── Main retrieval path ──
    let sqlResults: ScoredResult[] = [];
    let vectorResults: ScoredResult[] = [];
    let activityDelta: ActivityRow[] = [];
    let riskSignals: RiskSignals | null = null;
    const warnings: string[] = [];
    const fallbackUsed: string[] = [];
    const tablesQueried: string[] = [];
    const returnedCounts: Record<string, number> = {};
    let vectorSearchUsed = false;

    // Check for empty key tables upfront (parallel)
    const [projectCount, decisionCount] = await Promise.all([
      countTable(sb, "projects"),
      countTable(sb, "decisions"),
    ]);
    if (projectCount === 0) {
      warnings.push("projects_table_empty: Keine Projekte definiert");
    }

    // Step 2: Retrieve data based on routing
    switch (intent.retrievalMode) {
      case "sql_direct": {
        const sqlGroups = await executeSqlRetrieval(sb, intent, tablesQueried, returnedCounts);
        sqlResults = rawToScoredResults(sqlGroups);
        break;
      }

      case "semantic_hybrid": {
        const [vectorMatches, sqlGroups] = await Promise.all([
          semanticVectorSearch(sb, intent.semantic_query || query, match_threshold, match_count),
          executeSqlRetrieval(sb, intent, tablesQueried, returnedCounts),
        ]);

        vectorSearchUsed = true;
        // Lücke 3 fix: activity_log-Embeddings rausfiltern — 67% des Vektorraums,
        // aber nur ~94 Zeichen Inhalt ("Status geändert von X auf Y") — rauschen nur.
        const filteredMatches = vectorMatches.filter(
          (vm) => vm.entity_type !== "activity_log" && vm.entity_type !== "activity",
        );
        if (filteredMatches.length > 0) {
          const refs = filteredMatches.map((vm) => ({
            entity_type: vm.entity_type,
            entity_id: vm.entity_id,
          }));
          const liveData = await loadLiveEntities(sb, refs);
          vectorResults = vectorToScoredResults(filteredMatches, liveData);
        }

        sqlResults = rawToScoredResults(sqlGroups);
        break;
      }

      case "delta_report": {
        const timeRange = intent.time_range ?? {
          from: new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000).toISOString(),
          to: now.toISOString(),
        };

        const [delta, meetings, risks] = await Promise.all([
          getActivityDelta(sb, timeRange.from, timeRange.to),
          getMeetingsInRange(sb, timeRange.from, timeRange.to),
          getRiskSignals(sb),
        ]);

        activityDelta = delta;
        riskSignals = formatRiskSignals(risks);
        tablesQueried.push("activity_log", "meetings");
        returnedCounts["activity_log"] = delta.length;
        returnedCounts["meetings"] = meetings.length;

        const entityGroups = await getEntitiesInTimeRange(sb, timeRange.from, timeRange.to);
        sqlResults = rawToScoredResults(entityGroups);
        for (const g of entityGroups) {
          tablesQueried.push(g.type);
          returnedCounts[g.type] = (returnedCounts[g.type] ?? 0) + g.data.length;
        }

        if (meetings.length > 0) {
          sqlResults.push(...rawToScoredResults([{ type: "meetings", data: meetings }]));
        }

        // Decisions: try DB first, fall back to meeting key_decisions
        const meetingIds = meetings.map((m) => m.id);
        let decisions = meetingIds.length > 0 ? await getDecisions(sb, meetingIds) : [];
        tablesQueried.push("decisions");

        if (decisions.length === 0 && meetings.length > 0) {
          const syntheticDecisions = extractDecisionsFromMeetings(meetings);
          if (syntheticDecisions.length > 0) {
            decisions = syntheticDecisions as typeof decisions;
            fallbackUsed.push("decisions_from_meetings");
            warnings.push("decisions_table_empty: Entscheidungen aus Meeting-Notizen extrahiert");
          }
        }
        returnedCounts["decisions"] = decisions.length;
        if (decisions.length > 0) {
          sqlResults.push(...rawToScoredResults([{ type: "decisions", data: decisions }]));
        }
        break;
      }

      case "relation": {
        vectorSearchUsed = true;
        const vectorMatches = await semanticVectorSearch(sb, intent.semantic_query || query, match_threshold, match_count);
        if (vectorMatches.length > 0) {
          const refs = vectorMatches.map((vm) => ({
            entity_type: vm.entity_type,
            entity_id: vm.entity_id,
          }));
          const liveData = await loadLiveEntities(sb, refs);
          vectorResults = vectorToScoredResults(vectorMatches, liveData);
        }
        break;
      }
    }

    // Step 3: Topic anchor fallback
    // Lücke 1 fix: threshold < 5 entfernt. Anchor-Suche läuft immer wenn topic_anchors
    // vorhanden und projects leer — damit konzeptuelle Queries nicht leer ausgehen.
    const isConceptualIntent = ["project_query", "topic_query"].includes(intent.intent);
    if (
      intent.topic_anchors.length > 0 &&
      (projectCount === 0 || isConceptualIntent)
    ) {
      console.log(`[semantic-search] Topic anchor search for: ${intent.topic_anchors}`);
      const anchorGroups = await searchByTopicAnchor(sb, intent.topic_anchors);
      if (anchorGroups.length > 0) {
        sqlResults.push(...rawToScoredResults(anchorGroups));
        if (!fallbackUsed.includes("topic_anchor_search")) fallbackUsed.push("topic_anchor_search");
        for (const g of anchorGroups) {
          if (!tablesQueried.includes(g.type)) tablesQueried.push(g.type);
          returnedCounts[g.type] = (returnedCounts[g.type] ?? 0) + g.data.length;
        }
      }
    }

    // Step 3b: Supplemental semantic search — Lücke 2 fix.
    // Läuft für SQL-only Pfade wenn Intent konzeptuell ist oder SQL wenig liefert.
    // activity_log immer ausschließen (Noise).
    const CONCEPTUAL_INTENTS = new Set(["project_query", "topic_query", "semantic_search", "unknown"]);
    const needsVectorSupplement =
      !vectorSearchUsed &&
      intent.intent !== "count_query" &&
      intent.intent !== "source_audit" &&
      intent.intent !== "management_update" &&
      (sqlResults.length < 5 || CONCEPTUAL_INTENTS.has(intent.intent));

    if (needsVectorSupplement) {
      try {
        const supplementCount = sqlResults.length >= 5 ? 8 : 15;
        const vectorMatches = await semanticVectorSearch(
          sb, intent.semantic_query || query, 0.25, supplementCount,
        );
        const filtered = vectorMatches.filter(
          (vm) => vm.entity_type !== "activity_log" && vm.entity_type !== "activity",
        );
        if (filtered.length > 0) {
          const refs = filtered.map((vm) => ({ entity_type: vm.entity_type, entity_id: vm.entity_id }));
          const liveData = await loadLiveEntities(sb, refs);
          // SQL-Pfad ist führend → Vector-Ähnlichkeit skalieren damit SQL-Treffer dominieren
          const scale = sqlResults.length >= 5 ? 0.6 : 1.0;
          const supVec = vectorToScoredResults(filtered, liveData)
            .map((r) => ({ ...r, similarity: r.similarity * scale }));
          vectorResults.push(...supVec);
          vectorSearchUsed = true;
          fallbackUsed.push("vector_supplement");
        }
      } catch (err) {
        warnings.push(`vector_supplement_failed: ${String(err).slice(0, 100)}`);
      }
    }

    // Step 3c: Keyword search — Sprint 3. Names, acronyms, exact terms.
    // Non-fatal: failures are logged as warnings, vector path continues unaffected.
    const keywordTerms = (intent.topic_anchors.length > 0
      ? intent.topic_anchors.join(" ")
      : intent.semantic_query || query
    ).replace(/-/g, " "); // normalize hyphens so FTS can match individual tokens
    let keywordChunks: { speaker: string; content: string; chunk_index: number; meeting_id: string }[] = [];

    if (keywordTerms.trim().length >= 2 && intent.intent !== "count_query" && intent.intent !== "source_audit") {
      try {
        const { data: kwData, error: kwError } = await sb.rpc("keyword_search", {
          search_query: keywordTerms,
          result_limit: 20,
        });
        if (!kwError && kwData && kwData.length > 0) {
          const existingIds = new Set(sqlResults.map((r) => r.entity_id));
          const kwMeetings: ScoredResult[] = (kwData as Array<{
            source: string; id: string; meeting_title: string; content: string;
            meeting_date: string; rank_score: number;
          }>)
            .filter((r) => r.source === "meeting" && !existingIds.has(r.id))
            .map((r) => ({
              entity_type: "meetings",
              entity_id: r.id,
              title: r.meeting_title || "",
              content_excerpt: (r.content || "").slice(0, 600),
              date: r.meeting_date ? String(r.meeting_date).slice(0, 10) : undefined,
              similarity: r.rank_score * 0.7,
              score: r.rank_score * 0.7,
              match_reason: ["keyword_match"],
              source: "keyword",
            }));
          if (kwMeetings.length > 0) {
            sqlResults.push(...kwMeetings);
            if (!fallbackUsed.includes("keyword_search")) fallbackUsed.push("keyword_search");
          }
          keywordChunks = (kwData as Array<{
            source: string; speaker: string; content: string; meeting_id: string;
          }>)
            .filter((r) => r.source === "chunk")
            .slice(0, 6)
            .map((r) => ({
              speaker: r.speaker || "",
              content: (r.content || "").slice(0, 600),
              chunk_index: -1,
              meeting_id: r.meeting_id,
            }));
          console.log(`[semantic-search] keyword_search terms="${keywordTerms}" meetings=${kwMeetings.length} chunks=${keywordChunks.length}`);
        }
      } catch (err) {
        warnings.push(`keyword_search_failed: ${String(err).slice(0, 80)}`);
      }
    }

    // Step 3d: Keyword-triggered fetch for decisions and open_loops.
    // Runs when the query explicitly mentions decision/open-loop language
    // and these tables weren't already pulled in by the main retrieval path.
    const DECISION_KW = /entscheid|beschloss|beschluss|festgelegt|decision|entscheidung/i;
    const OPEN_LOOP_KW = /ungekl[äa]rt|offene?\s+frag|open.?loop|noch\s+kl[äa]ren|unklar|offen\s+geblieben/i;

    if ((DECISION_KW.test(query) || intent.retrieval_flags.include_decisions) && !tablesQueried.includes("decisions")) {
      try {
        const terms = intent.topic_anchors.length > 0 ? intent.topic_anchors : [query.slice(0, 60)];
        const decisionRows = await searchDecisionsByKeywords(sb, terms);
        if (decisionRows.length > 0) {
          sqlResults.push(...rawToScoredResults([{ type: "decisions", data: decisionRows }]));
          if (!tablesQueried.includes("decisions")) tablesQueried.push("decisions");
          returnedCounts["decisions"] = (returnedCounts["decisions"] ?? 0) + decisionRows.length;
          if (!fallbackUsed.includes("decision_keyword_search")) fallbackUsed.push("decision_keyword_search");
        }
      } catch (err) {
        warnings.push(`decision_keyword_search_failed: ${String(err).slice(0, 80)}`);
      }
    }

    if ((OPEN_LOOP_KW.test(query) || intent.retrieval_flags.include_open_loops) && !tablesQueried.includes("open_loops")) {
      try {
        const terms = intent.topic_anchors.length > 0 ? intent.topic_anchors : undefined;
        const loopRows = await getOpenLoopsByKeyword(sb, terms);
        if (loopRows.length > 0) {
          sqlResults.push(...rawToScoredResults([{ type: "open_loops", data: loopRows }]));
          tablesQueried.push("open_loops");
          returnedCounts["open_loops"] = loopRows.length;
          if (!fallbackUsed.includes("open_loop_keyword_search")) fallbackUsed.push("open_loop_keyword_search");
        }
      } catch (err) {
        warnings.push(`open_loop_keyword_search_failed: ${String(err).slice(0, 80)}`);
      }
    }

    // Step 4: Decisions fallback — when decisions table was not queried yet and is empty
    if (
      decisionCount === 0 &&
      !fallbackUsed.includes("decisions_from_meetings") &&
      !tablesQueried.includes("decisions")
    ) {
      // Get recent meetings and extract key_decisions
      const recentMeetings = await getLatestMeetings(sb, 5);
      if (recentMeetings.length > 0) {
        const syntheticDecisions = extractDecisionsFromMeetings(recentMeetings);
        if (syntheticDecisions.length > 0) {
          sqlResults.push(...rawToScoredResults([{ type: "decisions", data: syntheticDecisions }]));
          fallbackUsed.push("decisions_from_meetings");
          warnings.push("decisions_table_empty: Entscheidungen aus Meeting-Notizen extrahiert");
          tablesQueried.push("decisions");
          returnedCounts["decisions"] = syntheticDecisions.length;
        }
      }
    }

    // Step 5: Risk signals for risk/management questions
    if ((intent.isRiskQuestion || intent.isChefUpdate) && !riskSignals) {
      const risks = await getRiskSignals(sb);
      riskSignals = formatRiskSignals(risks);
    }

    // Step 6: Tag sources and fuse with RRF
    // sql results: tag by entity_type so decisions/commitments/open_loops form own RRF lists
    const taggedSql = sqlResults.map((r) => ({
      ...r,
      source: r.source ?? (
        r.entity_type === "decisions" ? "decisions" :
        r.entity_type === "commitments" ? "commitments" :
        r.entity_type === "open_loops" ? "open_loops" : "sql"
      ),
    }));
    const taggedVector = vectorResults.map((r) => ({ ...r, source: r.source ?? "vector" }));
    // RRF handles deduplication: same item from multiple sources accumulates score
    const ranked = rankAndScore([...taggedSql, ...taggedVector], intent);
    const withRelations = inferRelations(ranked);

    // Step 6b: Transcript chunk retrieval — driven by needs_raw_evidence flag.
    // Removed: replaced by needs_raw_evidence flag (Sprint 1)
    let transcriptExcerpts: { speaker: string; content: string; chunk_index: number; meeting_id: string }[] = [];
    let transcriptChunkCount = 0;

    if (intent.needs_raw_evidence) {
      try {
        const embRes = await fetch("https://api.openai.com/v1/embeddings", {
          method: "POST",
          headers: {
            Authorization: `Bearer ${Deno.env.get("OPENAI_API_KEY")}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ model: "text-embedding-3-small", input: intent.semantic_query || query }),
        });
        if (embRes.ok) {
          const embJson = await embRes.json();
          const queryEmbedding = embJson.data[0].embedding;
          const { data: chunks } = await sb.rpc("match_transcript_chunks", {
            query_embedding: queryEmbedding,
            match_threshold: 0.45,
            match_count: 8,
            filter_meeting_id: null,
          });
          if (chunks && chunks.length > 0) {
            transcriptChunkCount = chunks.length;
            transcriptExcerpts = chunks.map((c: {
              speaker: string; content: string; chunk_index: number; meeting_id: string;
            }) => ({
              speaker: c.speaker,
              content: c.content.slice(0, 600),
              chunk_index: c.chunk_index,
              meeting_id: c.meeting_id,
            }));
          }
        }
      } catch (err) {
        warnings.push(`transcript_chunk_lookup_failed: ${String(err).slice(0, 80)}`);
      }
    }

    // Merge keyword chunks into transcript excerpts (Sprint 3)
    if (keywordChunks.length > 0 && intent.needs_raw_evidence) {
      const seenMeetingIds = new Set(transcriptExcerpts.map((c) => c.meeting_id));
      for (const kc of keywordChunks) {
        if (!seenMeetingIds.has(kc.meeting_id)) {
          transcriptExcerpts.push(kc);
          transcriptChunkCount++;
          seenMeetingIds.add(kc.meeting_id);
        }
      }
    }

    // Evidence windows (Sprint 5): for top-3 vector-hit chunks load chunk-1 and chunk+1.
    // Gives the LLM conversational flow instead of isolated sentences.
    if (intent.needs_raw_evidence && transcriptExcerpts.length > 0) {
      try {
        const topHits = transcriptExcerpts.filter((c) => c.chunk_index >= 0).slice(0, 3);
        const seenIds = new Set(transcriptExcerpts.map((c) => `${c.meeting_id}:${c.chunk_index}`));
        const windowChunks: typeof transcriptExcerpts = [];

        await Promise.all(topHits.map(async (hit) => {
          const { data: neighbors } = await sb
            .from("transcript_chunks")
            .select("chunk_index, speaker, content, meeting_id")
            .eq("meeting_id", hit.meeting_id)
            .gte("chunk_index", hit.chunk_index - 1)
            .lte("chunk_index", hit.chunk_index + 1)
            .neq("chunk_index", hit.chunk_index)
            .neq("speaker", "__meta__")
            .order("chunk_index", { ascending: true });

          for (const n of neighbors ?? []) {
            const key = `${n.meeting_id}:${n.chunk_index}`;
            if (!seenIds.has(key)) {
              seenIds.add(key);
              windowChunks.push({
                speaker: n.speaker,
                content: (n.content ?? "").slice(0, 600),
                chunk_index: n.chunk_index,
                meeting_id: n.meeting_id,
              });
            }
          }
        }));

        if (windowChunks.length > 0) {
          transcriptExcerpts = [...transcriptExcerpts, ...windowChunks]
            .sort((a, b) => {
              if (a.meeting_id !== b.meeting_id) return a.meeting_id.localeCompare(b.meeting_id);
              return (a.chunk_index ?? 0) - (b.chunk_index ?? 0);
            });
          transcriptChunkCount += windowChunks.length;
          fallbackUsed.push("evidence_windows");
        }
      } catch (err) {
        warnings.push(`evidence_windows_failed: ${String(err).slice(0, 80)}`);
      }
    }

    console.log(`[semantic-search] intent=${intent.intent} needs_raw_evidence=${intent.needs_raw_evidence} transcript_chunks=${transcriptChunkCount}`);

    // Step 7: Build context with budget
    const aggregations = computeAggregations(withRelations);
    const { context, fullDetailCount, compactCount, aggregatedCount } = buildContextPacket(
      intent,
      withRelations,
      aggregations,
      riskSignals,
      warnings,
      activityDelta.length > 0 ? activityDelta : undefined,
      transcriptExcerpts.length > 0 ? transcriptExcerpts : undefined,
    );

    // Step 8: Build audit
    const audit = buildAudit(
      intent,
      tablesQueried,
      returnedCounts,
      fullDetailCount,
      compactCount,
      aggregatedCount,
      vectorSearchUsed,
      fallbackUsed,
      warnings,
    );

    // Step 9: Build messages for Claude
    const chatMessages: ChatMessage[] = [];
    for (const msg of history) {
      const content = msg.content ?? msg.text ?? "";
      if ((msg.role === "user" || msg.role === "assistant") && typeof content === "string" && content.trim().length > 0) {
        chatMessages.push({ role: msg.role, content });
      }
    }
    chatMessages.push({ role: "user", content: query });

    const systemPrompt = buildSystemPrompt(context, intent, audit);

    // Prepare matches payload
    const matchesPayload = withRelations.slice(0, 50).map((r) => ({
      entity_type: r.entity_type,
      entity_id: r.entity_id,
      title: r.title,
      content: r.title || r.content_excerpt || "",
      status: r.status,
      priority: r.priority,
      assignee: r.assignee,
      project_id: r.project_id,
      date: r.date,
      content_excerpt: r.content_excerpt,
      match_reason: r.match_reason,
      score: r.score,
      rrf_score: r.rrf_score,
      retrieval_sources: r.retrieval_sources,
      boost_reasons: r.boost_reasons,
      similarity: r.similarity,
      inferred_relation: r.inferred_relation,
    }));

    // Step 10: Generate response
    if (stream) {
      const encoder = new TextEncoder();
      const claudeStream = streamClaudeResponse(systemPrompt, chatMessages, intent.intent);
      const reader = claudeStream.getReader();

      const outputStream = new ReadableStream({
        async start(controller) {
          // Send matches event
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "matches", data: matchesPayload })}\n\n`));
          // Send audit event (before text starts)
          controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "audit", audit })}\n\n`));

          // Forward Claude stream events
          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              controller.enqueue(value);
            }
          } catch (err) {
            controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: "error", error: String(err) })}\n\n`));
          }
          controller.close();
        },
      });

      return new Response(outputStream, { headers: sseHeaders() });
    } else {
      const answer = await callClaude(systemPrompt, chatMessages, intent.intent);
      return jsonResponse({
        matches: matchesPayload,
        answer,
        intent: intent.intent,
        retrievalMode: intent.retrievalMode,
        audit,
      });
    }
  } catch (err) {
    console.error("[semantic-search] Error:", err);
    return jsonResponse({ error: String(err) }, 500);
  }
});

// --- Helper functions ---

/**
 * Execute SQL retrieval based on intent classification.
 * Tracks tables_queried and returned_counts.
 */
async function executeSqlRetrieval(
  // deno-lint-ignore no-explicit-any
  sb: any,
  intent: ReturnType<typeof planRetrieval>,
  tablesQueried: string[],
  returnedCounts: Record<string, number>,
  // deno-lint-ignore no-explicit-any
): Promise<{ type: string; data: any[] }[]> {
  // deno-lint-ignore no-explicit-any
  const results: { type: string; data: any[] }[] = [];

  const addResult = (type: string, data: unknown[]) => {
    if (!tablesQueried.includes(type)) tablesQueried.push(type);
    returnedCounts[type] = (returnedCounts[type] ?? 0) + data.length;
    if (data.length > 0) results.push({ type, data });
  };

  switch (intent.intent) {
    case "latest_entities": {
      if (intent.isLatestMeeting) {
        const meetings = await getLatestMeetings(sb, intent.meeting_count);
        addResult("meetings", meetings);
        if (meetings.length > 0) {
          const meetingIds = meetings.map((m: MeetingRow) => m.id);
          const decisions = await getDecisions(sb, meetingIds);
          addResult("decisions", decisions);
        }
      }
      break;
    }

    case "summarize_notes": {
      // Get latest meetings with full summaries
      const meetings = await getLatestMeetings(sb, intent.meeting_count || 3);
      addResult("meetings", meetings);
      if (meetings.length > 0) {
        const meetingIds = meetings.map((m: MeetingRow) => m.id);
        const decisions = await getDecisions(sb, meetingIds);
        addResult("decisions", decisions);
      }
      break;
    }

    case "person_meetings_query": {
      // Primary: meetings where person is a participant (ILIKE on participants::text)
      // Secondary: todos/open_items/blockers assigned to this person + commitments made by them
      for (const person of intent.people) {
        const nameVariants = getPersonAssigneeVariants(person);
        const [meetings, mentionedIn, entityResults, commitments] = await Promise.all([
          getMeetingsByPerson(sb, person, 20),
          getMeetingsMentioningPerson(sb, person, 10),
          getEntitiesByPersonFlexible(sb, person, intent.statuses[0] ?? undefined),
          getCommitmentsByPerson(sb, nameVariants),
        ]);

        // Merge meetings, dedup by id
        const seenMeetingIds = new Set<string>();
        for (const m of [...meetings, ...mentionedIn]) {
          if (!seenMeetingIds.has(m.id)) {
            seenMeetingIds.add(m.id);
            addResult("meetings", [m]);
          }
        }
        for (const g of entityResults) addResult(g.type, g.data);
        if (commitments.length > 0) addResult("commitments", commitments);
      }
      break;
    }

    case "person_status_query": {
      // Primary: todos/open_items/blockers for this person (all name variants)
      // Secondary: recent meetings with this person + commitments made by them
      for (const person of intent.people) {
        const entityTypes = intent.primary_tables.filter(
          (t) => t !== "meetings" && t !== "decisions",
        );
        const nameVariants = getPersonAssigneeVariants(person);
        const [entityResults, meetings, commitments] = await Promise.all([
          getEntitiesByPersonFlexible(
            sb, person,
            intent.statuses[0] ?? undefined,
            entityTypes.length > 0 ? entityTypes : undefined,
          ),
          getMeetingsByPerson(sb, person, 5),
          getCommitmentsByPerson(sb, nameVariants),
        ]);
        for (const g of entityResults) addResult(g.type, g.data);
        if (meetings.length > 0) addResult("meetings", meetings);
        if (commitments.length > 0) addResult("commitments", commitments);
      }

      // Also handle pure status queries (no person) using statuses filter
      if (intent.people.length === 0 && intent.statuses.length > 0) {
        for (const status of intent.statuses) {
          const entityTypes = intent.primary_tables.length > 0 ? intent.primary_tables : undefined;
          const statusResults = await getEntitiesByStatus(sb, status, entityTypes);
          for (const g of statusResults) addResult(g.type, g.data);
        }
      }
      break;
    }

    case "project_query": {
      // Strukturierte Suche wenn Projekte aufgelöst wurden
      for (const project of intent.projects) {
        const projectResults = await getEntitiesByProject(sb, project.project_id);
        for (const g of projectResults) addResult(g.type, g.data);
      }
      // Lücke 1 fix: immer auch Anchor-Suche — deckt den häufigen Fall ab,
      // dass projects-Tabelle leer ist oder der Begriff keinem Projekt-Datensatz entspricht.
      if (intent.topic_anchors.length > 0) {
        const anchorGroups = await searchByTopicAnchor(sb, intent.topic_anchors);
        for (const g of anchorGroups) addResult(g.type, g.data);
      }
      break;
    }

    case "topic_query": {
      if (intent.topic_anchors.length > 0) {
        const anchorGroups = await searchByTopicAnchor(sb, intent.topic_anchors);
        for (const g of anchorGroups) addResult(g.type, g.data);
      }
      break;
    }

    case "time_range_query": {
      if (intent.time_range) {
        const entityTypes = intent.primary_tables.length > 0 ? intent.primary_tables : undefined;
        const timeResults = await getEntitiesInTimeRange(sb, intent.time_range.from, intent.time_range.to, entityTypes);
        for (const g of timeResults) addResult(g.type, g.data);

        const meetings = await getMeetingsInRange(sb, intent.time_range.from, intent.time_range.to);
        addResult("meetings", meetings);
      }
      break;
    }

    case "risk_analysis": {
      const risks = await getRiskSignals(sb);
      addResult("todos", risks.highPrioOpenTodos);
      addResult("blockers", risks.activeBlockers);
      // Avoid duplicate todos
      const overdueNew = risks.overdueTodos.filter(
        (t) => !risks.highPrioOpenTodos.some((h) => h.id === t.id),
      );
      if (overdueNew.length > 0) addResult("todos", overdueNew);
      addResult("open_items", risks.staleOpenItems);
      break;
    }

    default:
      break;
  }

  return results;
}

/**
 * Deduplicate results by entity_id, keeping the one with higher similarity.
 */
function deduplicateResults(results: ScoredResult[]): ScoredResult[] {
  const seen = new Map<string, ScoredResult>();
  for (const r of results) {
    const key = `${r.entity_type}:${r.entity_id}`;
    const existing = seen.get(key);
    if (!existing) {
      seen.set(key, r);
    } else {
      if (r.similarity > existing.similarity) {
        r.match_reason = [...new Set([...existing.match_reason, ...r.match_reason])];
        seen.set(key, r);
      } else {
        existing.match_reason = [...new Set([...existing.match_reason, ...r.match_reason])];
      }
    }
  }
  return Array.from(seen.values());
}

/**
 * Format raw risk signal data into the RiskSignals interface.
 */
function formatRiskSignals(risks: Awaited<ReturnType<typeof getRiskSignals>>): RiskSignals {
  return {
    highPrioOpenTodos: risks.highPrioOpenTodos.map((t) => ({
      title: t.title,
      assignee: t.assignee,
      due_date: t.due_date,
    })),
    activeBlockers: risks.activeBlockers.map((b) => ({
      title: b.title,
      reported_by: b.reported_by,
      status: b.status,
    })),
    overdueTodos: risks.overdueTodos.map((t) => ({
      title: t.title,
      assignee: t.assignee,
      due_date: t.due_date,
    })),
    staleOpenItems: risks.staleOpenItems.map((o) => ({
      title: o.title,
      owner: o.owner,
      created_at: o.created_at,
    })),
  };
}
