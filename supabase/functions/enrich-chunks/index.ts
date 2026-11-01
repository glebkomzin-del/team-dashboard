import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const OPENAI_API_KEY = Deno.env.get("OPENAI_API_KEY")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const INTERNAL_FUNCTION_SECRET = Deno.env.get("INTERNAL_FUNCTION_SECRET")!;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

// deno-lint-ignore no-explicit-any
function buildContextualContent(chunk: any, meeting: any): string {
  const dateStr = meeting.meeting_date
    ? new Date(meeting.meeting_date).toLocaleDateString("de-DE", {
        year: "numeric",
        month: "long",
        day: "numeric",
      })
    : "Datum unbekannt";

  const topics: string[] = meeting.topics ?? [];
  const topicStr = topics.length > 0 ? topics.slice(0, 3).join(", ") : "";
  const summarySnippet = meeting.ai_summary
    ? meeting.ai_summary.slice(0, 200).replace(/\n/g, " ")
    : "";

  const headerParts = [
    `Meeting: ${meeting.title}`,
    `Datum: ${dateStr}`,
    topicStr ? `Themen: ${topicStr}` : null,
    summarySnippet ? `Kontext: ${summarySnippet}` : null,
    chunk.speaker ? `Sprecher: ${chunk.speaker}` : null,
    "---",
  ];

  const header = headerParts.filter(Boolean).join("\n");
  return `${header}\n${chunk.content}`;
}

async function generateEmbedding(text: string): Promise<number[]> {
  const response = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "text-embedding-3-small",
      input: text.slice(0, 8000),
    }),
  });
  if (!response.ok) throw new Error(`OpenAI error: ${await response.text()}`);
  const data = await response.json();
  return data.data[0].embedding;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (!INTERNAL_FUNCTION_SECRET || req.headers.get("x-internal-secret") !== INTERNAL_FUNCTION_SECRET) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } });
  }

  try {
    const { batch_size = 50, dry_run = false } = await req.json().catch(() => ({}));
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // Load content chunks that haven't been contextually embedded yet.
    // Exclude __meta__ chunks (chunk_index=-1, speaker='__meta__') — they already
    // embed meeting context and are used by match_transcript_chunks for summary retrieval.
    const { data: chunks, error } = await supabase
      .from("transcript_chunks")
      .select("id, meeting_id, chunk_index, speaker, content")
      .is("context_embedded_at", null)
      .neq("speaker", "__meta__")
      .order("meeting_id", { ascending: true })
      .order("chunk_index", { ascending: true })
      .limit(batch_size);

    if (error) throw error;
    if (!chunks?.length) {
      return new Response(
        JSON.stringify({ done: true, message: "Alle Chunks bereits angereichert" }),
        { headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
      );
    }

    // Bulk-load meeting data for all affected meetings (title, date, topics, summary)
    const meetingIds = [...new Set(chunks.map((c) => c.meeting_id))];
    const { data: meetings } = await supabase
      .from("meetings")
      .select("id, title, meeting_date, topics, ai_summary")
      .in("id", meetingIds);

    // deno-lint-ignore no-explicit-any
    const meetingMap: Record<string, any> = Object.fromEntries(
      (meetings ?? []).map((m) => [m.id, m]),
    );

    // deno-lint-ignore no-explicit-any
    const results: any[] = [];
    let processed = 0;
    let errors = 0;

    for (const chunk of chunks) {
      try {
        const meeting = meetingMap[chunk.meeting_id];
        if (!meeting) {
          results.push({ id: chunk.id, skipped: true, reason: "meeting not found" });
          continue;
        }

        const contextualContent = buildContextualContent(chunk, meeting);

        if (dry_run) {
          results.push({
            id: chunk.id,
            chunk_index: chunk.chunk_index,
            speaker: chunk.speaker,
            meeting_title: meeting.title,
            preview: contextualContent.slice(0, 400),
            length_before: chunk.content.length,
            length_after: contextualContent.length,
          });
          continue;
        }

        const embedding = await generateEmbedding(contextualContent);

        // Update transcript_chunks: store contextual_content + new embedding in-place.
        // The match_transcript_chunks RPC reads transcript_chunks.embedding directly —
        // that column is the single source of truth for chunk vector search.
        const { error: updateError } = await supabase
          .from("transcript_chunks")
          .update({
            contextual_content: contextualContent,
            embedding: JSON.stringify(embedding),
            context_embedded_at: new Date().toISOString(),
          })
          .eq("id", chunk.id);

        if (updateError) throw updateError;

        processed++;
        results.push({ id: chunk.id, ok: true });

        await new Promise((r) => setTimeout(r, 100));
      } catch (e) {
        errors++;
        results.push({ id: chunk.id, error: String(e).slice(0, 120) });
      }
    }

    // Report remaining
    const { count: remaining } = await supabase
      .from("transcript_chunks")
      .select("*", { count: "exact", head: true })
      .is("context_embedded_at", null)
      .neq("speaker", "__meta__");

    return new Response(
      JSON.stringify({
        processed,
        errors,
        remaining: remaining ?? 0,
        batch_results: dry_run ? results : `${processed} OK, ${errors} errors`,
      }),
      { headers: { ...CORS_HEADERS, "Content-Type": "application/json" } },
    );
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }
});
