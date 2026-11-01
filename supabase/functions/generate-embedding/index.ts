import "jsr:@supabase/functions-js/edge-runtime.d.ts";
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const OPENAI_API_KEY = Deno.env.get("OPENAI_API_KEY")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const INTERNAL_FUNCTION_SECRET = Deno.env.get("INTERNAL_FUNCTION_SECRET")!;

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
  if (!res.ok) throw new Error(`OpenAI error: ${await res.text()}`);
  return (await res.json()).data[0].embedding;
}

function buildContent(entityType: string, entity: any): string {
  switch (entityType) {
    case "todo":
      return `Todo: ${entity.title}. ${entity.description || ""}. Zuständig: ${entity.assignee}. Priorität: ${entity.priority}. Status: ${entity.status}.${entity.due_date ? " Fällig: " + entity.due_date : ""}`;
    case "blocker":
      return `Blocker: ${entity.title}. ${entity.description || ""}. Gemeldet von: ${entity.reported_by}. Status: ${entity.status}.`;
    case "open_item":
      return `Open Item: ${entity.title}. ${entity.description || ""}. Zuständig: ${entity.owner}. Kategorie: ${entity.category}. Status: ${entity.status}.`;
    case "meeting":
      return `Meeting: ${entity.title}. Datum: ${entity.meeting_date || ""}. Themen: ${(entity.topics || []).join(", ")}. Teilnehmer: ${(entity.participants || []).join(", ")}. Zusammenfassung: ${entity.ai_summary || ""}. Entscheidungen: ${(entity.key_decisions || []).join(", ")}.${entity.raw_transcript ? " Transkript: " + entity.raw_transcript.substring(0, 2000) : ""}`;
    case "decision":
      return `Entscheidung: ${entity.title}. ${entity.description || ""}. Entschieden von: ${entity.decided_by || "unbekannt"}. Status: ${entity.status}.`;
    case "project":
      return `Projekt: ${entity.name}. ${entity.description || ""}. Status: ${entity.status}.`;
    case "activity":
      const typeLabel: Record<string, string> = { todo: "Todo", blocker: "Blocker", open_item: "Open Item", meeting: "Meeting", decision: "Entscheidung" };
      const actionLabel: Record<string, string> = { created: "erstellt", status_changed: "Status geändert", updated: "bearbeitet", deleted: "gelöscht" };
      return `Änderung am ${new Date(entity.created_at).toLocaleDateString("de-DE")}: ${typeLabel[entity.entity_type] || entity.entity_type} wurde ${actionLabel[entity.action] || entity.action}.${entity.note ? " Titel: " + entity.note : ""}${entity.field_changed ? " Feld: " + entity.field_changed : ""}${entity.old_value ? " Von: " + entity.old_value : ""}${entity.new_value ? " Auf: " + entity.new_value : ""}`;
    default:
      return JSON.stringify(entity);
  }
}

function buildMetadata(entityType: string, entity: any): Record<string, any> {
  switch (entityType) {
    case "todo":
      return {
        assignee: entity.assignee,
        status: entity.status,
        priority: entity.priority,
        due_date: entity.due_date,
        created_at: entity.created_at,
        updated_at: entity.updated_at,
        meeting_id: entity.meeting_id,
        project_id: entity.project_id,
      };
    case "blocker":
      return {
        reported_by: entity.reported_by,
        status: entity.status,
        resolved_at: entity.resolved_at,
        created_at: entity.created_at,
        updated_at: entity.updated_at,
        meeting_id: entity.meeting_id,
        project_id: entity.project_id,
      };
    case "open_item":
      return {
        owner: entity.owner,
        status: entity.status,
        category: entity.category,
        created_at: entity.created_at,
        updated_at: entity.updated_at,
        meeting_id: entity.meeting_id,
        project_id: entity.project_id,
      };
    case "meeting":
      return {
        meeting_date: entity.meeting_date,
        topics: entity.topics,
        participants: entity.participants,
        key_decisions: entity.key_decisions,
        created_at: entity.created_at,
      };
    case "activity":
      return {
        action: entity.action,
        source_entity_type: entity.entity_type,
        source_entity_id: entity.entity_id,
        field_changed: entity.field_changed,
        old_value: entity.old_value,
        new_value: entity.new_value,
        changed_by: entity.changed_by,
        created_at: entity.created_at,
        meeting_id: entity.meeting_id,
      };
    case "decision":
      return {
        decided_by: entity.decided_by,
        status: entity.status,
        meeting_id: entity.meeting_id,
        project_id: entity.project_id,
        created_at: entity.created_at,
      };
    case "project":
      return {
        status: entity.status,
        created_at: entity.created_at,
        updated_at: entity.updated_at,
      };
    default:
      return {};
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (!INTERNAL_FUNCTION_SECRET || req.headers.get("x-internal-secret") !== INTERNAL_FUNCTION_SECRET) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { ...corsHeaders, "Content-Type": "application/json" } });
  }

  try {
    const { entity_type, entity_id, action } = await req.json();
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    if (action === "deleted" || action === "DELETE") {
      await supabase.from("embeddings").delete().eq("entity_type", entity_type).eq("entity_id", entity_id);
      return new Response(JSON.stringify({ success: true, action: "deleted" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // activity_log excluded from embeddings: high volume, low signal
    if (entity_type === "activity_log" || entity_type === "activity") {
      return new Response(JSON.stringify({ skipped: true, reason: "activity_log excluded from embeddings" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    let table: string;
    if (entity_type === "open_item") table = "open_items";
    else if (entity_type === "activity") table = "activity_log";
    else table = entity_type + "s";

    const { data: entity, error } = await supabase.from(table).select("*").eq("id", entity_id).single();
    if (error || !entity) {
      return new Response(JSON.stringify({ error: "Entity not found" }), {
        status: 404, headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const content = buildContent(entity_type, entity);
    const metadata = buildMetadata(entity_type, entity);
    const embedding = await getEmbedding(content);

    const { error: upsertError } = await supabase.from("embeddings").upsert({
      entity_type, entity_id, content, metadata,
      embedding: JSON.stringify(embedding),
      updated_at: new Date().toISOString(),
    }, { onConflict: "entity_type,entity_id" });

    if (upsertError) throw upsertError;

    return new Response(JSON.stringify({ success: true, content_length: content.length }), {
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }), {
      status: 500, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
});
