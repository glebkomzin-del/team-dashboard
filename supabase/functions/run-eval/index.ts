// run-eval/index.ts — Sprint 8: Automated Eval Runner
// Runs all (or a subset of) eval_questions against ask-memory (das produktive
// KI-System des Dashboards) and stores scored results in eval_results +
// summary in eval_runs.
// Sprint 10: LLM-Judge (inhaltliche Bewertung statt Stichwort-Zaehlen).
// 2026-07: Umstellung von semantic-search (Legacy) auf ask-memory.
//   - source_hit misst jetzt, ob die von ask-memory BELEGTEN Meeting-IDs
//     die erwarteten Quellen treffen (vorher: Retrieval-Matches).
//   - intent_accuracy entfaellt: ask-memory hat keine Intent-Klassifikation.
//     actual_intent transportiert informativ den retrieval.mode.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

const CORS_HEADERS: Record<string, string> = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const MINI_EVAL_QUESTION_IDS = [4, 5, 6, 7, 8, 9, 10, 11, 12, 14, 15, 18, 19, 20];

const EXPECTED_INTENT_ALIASES: Record<string, string> = {
  meeting_list: "latest_entities",
  meeting_summary: "summarize_notes",
  person_profile: "person_status_query",
};

function normalizeExpectedIntent(intent: string | null | undefined): string | null {
  if (!intent) return null;
  return EXPECTED_INTENT_ALIASES[intent] ?? intent;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body, null, 2), {
    status,
    headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// LLM-Judge: bewertet inhaltliche Korrektheit der Antwort gegen expected_answer,
// nicht Stichwort-Vorkommen. 0=falsch/leer, 1=teilweise, 2=groesstenteils, 3=voll korrekt.
async function judgeAnswer(
  apiKey: string,
  question: string,
  expectedAnswer: string | null,
  answer: string,
  mustNotClaim: string[],
): Promise<{ score: number | null; reason: string; hallucination: boolean | null }> {
  if (!expectedAnswer) return { score: null, reason: "no expected_answer", hallucination: null };
  const sys = `Du bist ein strenger, fairer Bewerter. Bewerte, ob die ANTWORT die ERWARTETE_KERNAUSSAGE inhaltlich trifft. Synonyme und Umschreibungen zaehlen als Treffer (z.B. "SAP-Migration" deckt "S/4HANA" ab). Stichwort-Zaehlen ist NICHT das Kriterium - es geht um inhaltliche Korrektheit und Vollstaendigkeit der Kernaussage.\n\nWenn die ERWARTETE_KERNAUSSAGE besagt, dass etwas NICHT belegbar ist, dann ist die korrekte Antwort eine, die genau das transparent macht (nicht erfindet).\n\nGib NUR JSON zurueck, keine Prosa:\n{\"score\": 0|1|2|3, \"reason\": \"<knapp>\", \"hallucination\": true|false}\nscore: 0=verfehlt/leer, 1=teilweise, 2=groesstenteils korrekt, 3=voll korrekt.\nhallucination=true, wenn die Antwort etwas behauptet, das laut VERBOTENE_CLAIMS nicht behauptet werden darf, oder etwas erkennbar erfindet.`;
  const usr = `FRAGE: ${question}\n\nERWARTETE_KERNAUSSAGE: ${expectedAnswer}\n\nVERBOTENE_CLAIMS (duerfen nicht als Fakt behauptet werden): ${mustNotClaim.length ? mustNotClaim.join(", ") : "(keine)"}\n\nANTWORT:\n${answer.slice(0, 4000)}`;
  try {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": apiKey, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({
        model: "claude-sonnet-4-6",
        max_tokens: 300,
        system: sys,
        messages: [{ role: "user", content: usr }],
      }),
    });
    if (!res.ok) return { score: null, reason: `judge HTTP ${res.status}`, hallucination: null };
    const j = await res.json();
    const txt = (j.content ?? []).filter((b: {type:string}) => b.type === "text").map((b: {text:string}) => b.text).join("");
    const clean = txt.replace(/```json|```/g, "").trim();
    const parsed = JSON.parse(clean);
    return {
      score: typeof parsed.score === "number" ? parsed.score : null,
      reason: String(parsed.reason ?? "").slice(0, 400),
      hallucination: typeof parsed.hallucination === "boolean" ? parsed.hallucination : null,
    };
  } catch (e) {
    return { score: null, reason: `judge parse error: ${String(e).slice(0,120)}`, hallucination: null };
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response("ok", { headers: CORS_HEADERS });
  }
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
  const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
  const SEARCH_URL = `${SUPABASE_URL}/functions/v1/ask-memory`;

  // ask-memory laesst interne Aufrufer nur mit Service-Key passieren
  // (Dashboard-User-JWTs liegen hier nicht vor).
  const callerAuth = `Bearer ${SERVICE_KEY}`;

  const sb = createClient(SUPABASE_URL, SERVICE_KEY);
  const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") ?? "";

  const { question_ids, mini_eval, notes } = await req.json().catch(() => ({}));

  let qQuery = sb.from("eval_questions").select("*").order("id");
  if (Array.isArray(question_ids) && question_ids.length > 0) {
    qQuery = qQuery.in("id", question_ids);
  } else if (mini_eval === true) {
    qQuery = qQuery.in("id", MINI_EVAL_QUESTION_IDS);
  }
  const { data: questions, error: qErr } = await qQuery;
  if (qErr || !questions?.length) {
    return jsonResponse({ error: qErr?.message ?? "No questions found" }, 400);
  }

  const { data: run, error: runErr } = await sb
    .from("eval_runs")
    .insert({ questions_tested: questions.length, notes: notes ?? null })
    .select()
    .single();
  if (runErr || !run) {
    return jsonResponse({ error: runErr?.message ?? "Failed to create run" }, 500);
  }

  const results: Record<string, unknown>[] = [];
  let sourceHits = 0;
  let sourceEvaluable = 0;
  let intentHits = 0;
  let intentEvaluable = 0;
  let mustIncludeHitsTotal = 0;
  let mustIncludeTermsTotal = 0;
  let judgeScoreSum = 0;
  let judgeScoreCount = 0;

  for (const q of questions) {
    const start = Date.now();
    try {
      const resp = await fetch(SEARCH_URL, {
        method: "POST",
        headers: {
          Authorization: callerAuth,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: q.question }),
      });

      const latency = Date.now() - start;

      if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${errText.slice(0, 200)}`);
      }

      const data = await resp.json();
      // Informativ: retrieval.mode von ask-memory (kein Intent-System mehr).
      const actualIntent: string | null = typeof data?.retrieval?.mode === "string"
        ? data.retrieval.mode
        : null;

      const src = data.sources ?? {};
      const sourceIdsReturned: string[] = [...new Set([
        ...((src.meetings ?? []) as Record<string, unknown>[]).map((m) => String(m.id ?? "")),
        ...((src.chunks ?? []) as Record<string, unknown>[]).map((c) => String(c.meeting_id ?? "")),
        ...((src.items ?? []) as Record<string, unknown>[]).map((it) => String(it.meeting_id ?? "")),
      ])].filter(Boolean).slice(0, 20);

      const hasExpected =
        Array.isArray(q.expected_source_ids) && q.expected_source_ids.length > 0;
      const sourceHit: boolean | null = hasExpected
        ? q.expected_source_ids.some((id: string) => sourceIdsReturned.includes(id))
        : null;

      const expectedIntent = normalizeExpectedIntent(q.expected_intent);
      // ask-memory klassifiziert keine Intents — Metrik dauerhaft n/a.
      const intentCorrect: boolean | null = null;

      const answerText: string = data.answer ?? "";

      const judged = await judgeAnswer(
        ANTHROPIC_API_KEY, q.question, q.expected_answer, answerText, q.must_not_claim ?? [],
      );
      if (judged.score !== null) { judgeScoreSum += judged.score; judgeScoreCount++; }

      const mustIncludeHits = (q.must_include ?? []).filter((term: string) =>
        answerText.toLowerCase().includes(term.toLowerCase())
      );
      const mustIncludeMisses = (q.must_include ?? []).filter(
        (term: string) => !answerText.toLowerCase().includes(term.toLowerCase())
      );

      if (sourceHit === true) sourceHits++;
      if (sourceHit !== null) sourceEvaluable++;
      if (intentCorrect === true) intentHits++;
      if (intentCorrect !== null) intentEvaluable++;
      if ((q.must_include ?? []).length > 0) {
        mustIncludeHitsTotal += mustIncludeHits.length;
        mustIncludeTermsTotal += q.must_include.length;
      }

      await sb.from("eval_results").insert({
        run_id: run.id,
        question_id: q.id,
        actual_intent: actualIntent,
        source_ids_returned: sourceIdsReturned,
        source_hit: sourceHit,
        intent_correct: intentCorrect,
        must_include_hits: mustIncludeHits,
        must_include_misses: mustIncludeMisses,
        answer_snippet: answerText.slice(0, 500),
        latency_ms: latency,
        judge_score: judged.score,
        judge_reason: judged.reason,
        hallucination: judged.hallucination,
      });

      results.push({
        id: q.id,
        question: q.question.slice(0, 70),
        expected: expectedIntent,
        expected_raw: q.expected_intent,
        actual: actualIntent,
        source_hit: sourceHit,
        intent_ok: intentCorrect,
        must_misses: mustIncludeMisses,
        judge_score: judged.score,
        judge_reason: judged.reason,
        latency_ms: latency,
      });
    } catch (e) {
      const latency = Date.now() - start;
      await sb.from("eval_results").insert({
        run_id: run.id,
        question_id: q.id,
        actual_intent: null,
        source_ids_returned: [],
        source_hit: null,
        intent_correct: null,
        must_include_hits: [],
        must_include_misses: q.must_include ?? [],
        answer_snippet: `ERROR: ${String(e).slice(0, 490)}`,
        latency_ms: latency,
      });
      results.push({ id: q.id, error: String(e).slice(0, 200) });
    }

    await sleep(1000);
  }

  const sourceHitRate = sourceEvaluable > 0 ? sourceHits / sourceEvaluable : null;
  const intentAccuracy = intentEvaluable > 0 ? intentHits / intentEvaluable : null;
  const mustIncludeHitRate = mustIncludeTermsTotal > 0
    ? mustIncludeHitsTotal / mustIncludeTermsTotal
    : null;
  await sb
    .from("eval_runs")
    .update({ source_hit_rate: sourceHitRate, intent_accuracy: intentAccuracy, must_include_hit_rate: mustIncludeHitRate, avg_judge_score: judgeScoreCount > 0 ? judgeScoreSum / judgeScoreCount : null })
    .eq("id", run.id);

  return jsonResponse({
    run_id: run.id,
    summary: {
      total: questions.length,
      question_ids: questions.map((q: { id: number }) => q.id),
      source_hit_rate: sourceEvaluable > 0
        ? `${sourceHits}/${sourceEvaluable} (${Math.round((sourceHits / sourceEvaluable) * 100)}%)`
        : "n/a (no expected_source_ids set)",
      intent_accuracy: intentEvaluable > 0
        ? `${intentHits}/${intentEvaluable} (${Math.round((intentHits / intentEvaluable) * 100)}%)`
        : "n/a",
      must_include_hit_rate: mustIncludeTermsTotal > 0
        ? `${mustIncludeHitsTotal}/${mustIncludeTermsTotal} (${Math.round((mustIncludeHitsTotal / mustIncludeTermsTotal) * 100)}%)`
        : "n/a",
      avg_judge_score: judgeScoreCount > 0
        ? `${(judgeScoreSum / judgeScoreCount).toFixed(2)}/3 (n=${judgeScoreCount})`
        : "n/a",
      avg_latency_ms: Math.round(
        results.reduce((s, r) => s + ((r.latency_ms as number) ?? 0), 0) / results.length
      ),
    },
    results,
  });
});
