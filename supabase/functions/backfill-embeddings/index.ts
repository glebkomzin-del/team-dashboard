import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const OPENAI_API_KEY = Deno.env.get("OPENAI_API_KEY")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

async function getEmbedding(text: string): Promise<number[]> {
  const res = await fetch("https://api.openai.com/v1/embeddings", {
    method: "POST",
    headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: "text-embedding-3-small", input: text }),
  });
  if (!res.ok) throw new Error(`OpenAI: ${await res.text()}`);
  return (await res.json()).data[0].embedding;
}

function buildContent(type: string, e: any): string {
  switch (type) {
    case "todo": return `Todo: ${e.title}. ${e.description || ""}. Zuständig: ${e.assignee}. Priorität: ${e.priority}. Status: ${e.status}.${e.due_date ? " Fällig: " + e.due_date : ""}`;
    case "blocker": return `Blocker: ${e.title}. ${e.description || ""}. Gemeldet von: ${e.reported_by}. Status: ${e.status}.`;
    case "open_item": return `Open Item: ${e.title}. ${e.description || ""}. Zuständig: ${e.owner}. Kategorie: ${e.category}. Status: ${e.status}.`;
    case "meeting": return `Meeting: ${e.title}. Datum: ${e.meeting_date || ""}. Themen: ${(e.topics || []).join(", ")}. Teilnehmer: ${(e.participants || []).join(", ")}. Zusammenfassung: ${e.ai_summary || ""}. Entscheidungen: ${(e.key_decisions || []).join(", ")}.${e.raw_transcript ? " Transkript: " + e.raw_transcript.substring(0, 2000) : ""}`;
    case "decision": return `Entscheidung: ${e.title}. ${e.description || ""}. Status: ${e.status}.`;
    case "project": return `Projekt: ${e.name}. ${e.description || ""}. Status: ${e.status}.`;
    case "activity": {
      const tl: Record<string, string> = { todo: "Todo", blocker: "Blocker", open_item: "Open Item", meeting: "Meeting", decision: "Entscheidung" };
      const al: Record<string, string> = { created: "erstellt", status_changed: "Status geändert", updated: "bearbeitet", deleted: "gelöscht" };
      return `Änderung am ${new Date(e.created_at).toLocaleDateString("de-DE")}: ${tl[e.entity_type] || e.entity_type} wurde ${al[e.action] || e.action}.${e.note ? " Titel: " + e.note : ""}${e.field_changed ? " Feld: " + e.field_changed : ""}${e.old_value ? " Von: " + e.old_value : ""}${e.new_value ? " Auf: " + e.new_value : ""}`;
    }
    default: return JSON.stringify(e);
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });

  try {
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);
    const tables = [
      { type: "todo", table: "todos" },
      { type: "blocker", table: "blockers" },
      { type: "open_item", table: "open_items" },
      { type: "meeting", table: "meetings" },
      { type: "decision", table: "decisions" },
      { type: "project", table: "projects" },
      // activity_log excluded: high volume, low signal, filtered out in semantic-search anyway
    ];

    let total = 0;
    let errors = 0;

    for (const { type, table } of tables) {
      const { data: rows } = await supabase.from(table).select("*");
      if (!rows) continue;

      for (const row of rows) {
        const { data: existing } = await supabase
          .from("embeddings")
          .select("id")
          .eq("entity_type", type)
          .eq("entity_id", row.id)
          .maybeSingle();
        if (existing) continue;

        try {
          const content = buildContent(type, row);
          const embedding = await getEmbedding(content);
          await supabase.from("embeddings").upsert({
            entity_type: type,
            entity_id: row.id,
            content,
            embedding: JSON.stringify(embedding),
          }, { onConflict: "entity_type,entity_id" });
          total++;
          await new Promise(r => setTimeout(r, 350));
        } catch {
          errors++;
        }
      }
    }

    return new Response(JSON.stringify({ success: true, embedded: total, errors }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err.message }), {
      status: 500,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
