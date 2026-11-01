// live_entity_loader.ts — Batch-load full current records from source tables

import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

// deno-lint-ignore no-explicit-any
type SB = SupabaseClient<any, any, any>;

export interface EntityRef {
  entity_type: string;
  entity_id: string;
}

// deno-lint-ignore no-explicit-any
export type LiveEntity = Record<string, any>;

const ENTITY_TABLE_MAP: Record<string, string> = {
  meetings: "meetings",
  meeting: "meetings",
  todos: "todos",
  todo: "todos",
  blockers: "blockers",
  blocker: "blockers",
  open_items: "open_items",
  open_item: "open_items",
  decisions: "decisions",
  decision: "decisions",
  projects: "projects",
  project: "projects",
};

/**
 * Load full current records from source tables for a batch of entity references.
 * Groups refs by entity_type, performs one query per type.
 */
export async function loadLiveEntities(
  sb: SB,
  refs: EntityRef[],
): Promise<Map<string, LiveEntity>> {
  if (refs.length === 0) return new Map();

  // Group by entity_type
  const grouped = new Map<string, string[]>();
  for (const ref of refs) {
    const table = ENTITY_TABLE_MAP[ref.entity_type];
    if (!table) {
      console.warn(`Unknown entity_type: ${ref.entity_type}`);
      continue;
    }
    const ids = grouped.get(table) ?? [];
    ids.push(ref.entity_id);
    grouped.set(table, ids);
  }

  const result = new Map<string, LiveEntity>();

  // Batch-load from each table
  const promises = Array.from(grouped.entries()).map(async ([table, ids]) => {
    const uniqueIds = [...new Set(ids)];
    const { data, error } = await sb
      .from(table)
      .select("*")
      .in("id", uniqueIds);

    if (error) {
      console.error(`loadLiveEntities(${table}): ${error.message}`);
      return;
    }
    for (const row of data ?? []) {
      // Key: "entityType:entityId"
      result.set(`${table}:${row.id}`, row);
    }
  });

  await Promise.all(promises);
  return result;
}

/**
 * Format a live entity into a structured text representation suitable for context.
 */
// deno-lint-ignore no-explicit-any
export function formatEntityForContext(entity: Record<string, any>, entityType: string): string {
  const lines: string[] = [];
  const type = ENTITY_TABLE_MAP[entityType] ?? entityType;

  switch (type) {
    case "meetings": {
      lines.push(`[Meeting] ${entity.title ?? "Unbenannt"}`);
      if (entity.meeting_date) lines.push(`  Datum: ${entity.meeting_date.substring(0, 10)}`);
      if (entity.participants?.length) lines.push(`  Teilnehmer: ${entity.participants.join(", ")}`);
      if (entity.topics?.length) lines.push(`  Themen: ${entity.topics.join(", ")}`);
      if (entity.executive_summary) lines.push(`  Executive Summary: ${entity.executive_summary}`);
      else if (entity.ai_summary) lines.push(`  Zusammenfassung: ${entity.ai_summary.substring(0, 500)}`);
      if (entity.key_decisions?.length) lines.push(`  Entscheidungen: ${entity.key_decisions.join("; ")}`);
      break;
    }
    case "todos": {
      lines.push(`[Todo] ${entity.title ?? "Unbenannt"}`);
      if (entity.status) lines.push(`  Status: ${entity.status}`);
      if (entity.priority) lines.push(`  Priorität: ${entity.priority}`);
      if (entity.assignee) lines.push(`  Zuständig: ${entity.assignee}`);
      if (entity.due_date) lines.push(`  Fällig: ${entity.due_date}`);
      if (entity.start_date) lines.push(`  Start: ${entity.start_date}`);
      if (entity.description) lines.push(`  Beschreibung: ${entity.description.substring(0, 300)}`);
      if (entity.project_id) lines.push(`  Projekt-ID: ${entity.project_id}`);
      if (entity.depends_on?.length) lines.push(`  Abhängig von: ${entity.depends_on.join(", ")}`);
      break;
    }
    case "blockers": {
      lines.push(`[Blocker] ${entity.title ?? "Unbenannt"}`);
      if (entity.status) lines.push(`  Status: ${entity.status}`);
      if (entity.reported_by) lines.push(`  Gemeldet von: ${entity.reported_by}`);
      if (entity.description) lines.push(`  Beschreibung: ${entity.description.substring(0, 300)}`);
      if (entity.resolution_note) lines.push(`  Lösung: ${entity.resolution_note}`);
      if (entity.project_id) lines.push(`  Projekt-ID: ${entity.project_id}`);
      break;
    }
    case "open_items": {
      lines.push(`[Open Item] ${entity.title ?? "Unbenannt"}`);
      if (entity.status) lines.push(`  Status: ${entity.status}`);
      if (entity.owner) lines.push(`  Owner: ${entity.owner}`);
      if (entity.category) lines.push(`  Kategorie: ${entity.category}`);
      if (entity.description) lines.push(`  Beschreibung: ${entity.description.substring(0, 300)}`);
      if (entity.project_id) lines.push(`  Projekt-ID: ${entity.project_id}`);
      break;
    }
    case "decisions": {
      lines.push(`[Entscheidung] ${entity.title ?? "Unbenannt"}`);
      if (entity.status) lines.push(`  Status: ${entity.status}`);
      if (entity.decided_by) lines.push(`  Entschieden von: ${entity.decided_by}`);
      if (entity.description) lines.push(`  Beschreibung: ${entity.description.substring(0, 300)}`);
      if (entity.project_id) lines.push(`  Projekt-ID: ${entity.project_id}`);
      break;
    }
    case "projects": {
      lines.push(`[Projekt] ${entity.name ?? "Unbenannt"}`);
      if (entity.status) lines.push(`  Status: ${entity.status}`);
      if (entity.description) lines.push(`  Beschreibung: ${entity.description.substring(0, 300)}`);
      break;
    }
    default: {
      lines.push(`[${entityType}] ${entity.title ?? entity.name ?? entity.id}`);
    }
  }

  if (entity.created_at) lines.push(`  Erstellt: ${entity.created_at.substring(0, 10)}`);

  return lines.join("\n");
}
