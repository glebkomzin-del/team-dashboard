// sql_retriever.ts — SQL-based data retrieval from Supabase

import { SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";
import { getStatusDbVariants } from "./lexicon.ts";
import {
  type PersonEntry,
  buildParticipantFilter,
  getPersonAssigneeVariants,
} from "./entity_resolver.ts";

// deno-lint-ignore no-explicit-any
type SB = SupabaseClient<any, any, any>;

export interface MeetingRow {
  id: string;
  title: string;
  meeting_date: string;
  topics: string[] | null;
  participants: string[] | null;
  transcript_url: string | null;
  raw_transcript: string | null;
  ai_summary: string | null;
  key_decisions: string[] | null;
  source_file: string | null;
  processed_at: string | null;
  created_at: string;
  executive_summary: string | null;
}

export interface TodoRow {
  id: string;
  assignee_id: string | null;
  meeting_id: string | null;
  title: string;
  description: string | null;
  status: string | null;
  priority: string | null;
  due_date: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string | null;
  assignee_raw: string | null;
  external_name: string | null;
  assignee: string | null;
  project_id: string | null;
  start_date: string | null;
  depends_on: string[] | null;
  duration_days: number | null;
}

export interface BlockerRow {
  id: string;
  reported_by_id: string | null;
  meeting_id: string | null;
  title: string;
  description: string | null;
  status: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
  created_at: string;
  updated_at: string | null;
  reported_by_raw: string | null;
  external_name: string | null;
  reported_by: string | null;
  project_id: string | null;
}

export interface OpenItemRow {
  id: string;
  owner_id: string | null;
  meeting_id: string | null;
  title: string;
  description: string | null;
  category: string | null;
  status: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string | null;
  owner_raw: string | null;
  external_name: string | null;
  owner: string | null;
  project_id: string | null;
}

export interface DecisionRow {
  id: string;
  meeting_id: string | null;
  project_id: string | null;
  title: string;
  description: string | null;
  decided_by: string | null;
  status: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface CommitmentRow {
  id: string;
  meeting_id: string | null;
  person: string;
  commitment_text: string;
  due_date: string | null;
  confidence: string | null;
  created_at: string;
}

export interface OpenLoopRow {
  id: string;
  meeting_id: string | null;
  question_text: string;
  raised_by: string | null;
  assigned_to: string | null;
  created_at: string;
}

export interface ActivityRow {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  field_changed: string | null;
  old_value: string | null;
  new_value: string | null;
  changed_by: string | null;
  note: string | null;
  created_at: string;
  meeting_id: string | null;
}

// deno-lint-ignore no-explicit-any
export type EntityRow = MeetingRow | TodoRow | BlockerRow | OpenItemRow | DecisionRow | any;

/**
 * Get latest meetings, ordered by meeting_date DESC.
 */
export async function getLatestMeetings(sb: SB, count: number): Promise<MeetingRow[]> {
  const { data, error } = await sb
    .from("meetings")
    .select("*")
    .order("meeting_date", { ascending: false })
    .limit(count * 3);

  if (error) throw new Error(`getLatestMeetings: ${error.message}`);
  if (!data || data.length === 0) return [];

  const seenDays = new Set<string>();
  const result: MeetingRow[] = [];
  for (const row of data) {
    const day = row.meeting_date?.substring(0, 10) ?? "";
    if (!seenDays.has(day)) {
      seenDays.add(day);
      if (seenDays.size > count) break;
    }
    if (seenDays.size <= count) {
      result.push(row);
    }
  }
  return result;
}

/**
 * Get entities assigned to / owned by / reported by a person.
 */
export async function getEntitiesByPerson(
  sb: SB,
  person: string,
  status?: string,
  entityTypes?: string[],
): Promise<{ type: string; data: EntityRow[] }[]> {
  const types = entityTypes ?? ["todos", "open_items", "blockers"];
  const results: { type: string; data: EntityRow[] }[] = [];

  for (const t of types) {
    let query = sb.from(t).select("*");

    if (t === "todos") {
      query = query.eq("assignee", person);
    } else if (t === "blockers") {
      query = query.eq("reported_by", person);
    } else if (t === "open_items") {
      query = query.eq("owner", person);
    } else if (t === "decisions") {
      query = query.eq("decided_by", person);
    } else {
      continue;
    }

    if (status) {
      const variants = getStatusDbVariants(status);
      query = query.in("status", variants);
    }

    query = query.order("created_at", { ascending: false }).limit(50);
    const { data, error } = await query;

    if (error) {
      console.error(`getEntitiesByPerson(${t}): ${error.message}`);
      continue;
    }
    if (data && data.length > 0) {
      results.push({ type: t, data });
    }
  }
  return results;
}

/**
 * Get entities filtered by status.
 */
export async function getEntitiesByStatus(
  sb: SB,
  status: string,
  entityTypes?: string[],
): Promise<{ type: string; data: EntityRow[] }[]> {
  const types = entityTypes ?? ["todos", "open_items", "blockers"];
  const results: { type: string; data: EntityRow[] }[] = [];

  const variants = getStatusDbVariants(status);

  for (const t of types) {
    const { data, error } = await sb
      .from(t)
      .select("*")
      .in("status", variants)
      .order("created_at", { ascending: false })
      .limit(50);

    if (error) {
      console.error(`getEntitiesByStatus(${t}): ${error.message}`);
      continue;
    }
    if (data && data.length > 0) {
      results.push({ type: t, data });
    }
  }
  return results;
}

/**
 * Get entities filtered by project_id.
 */
export async function getEntitiesByProject(
  sb: SB,
  projectId: string,
): Promise<{ type: string; data: EntityRow[] }[]> {
  const tables = ["todos", "open_items", "blockers", "decisions"];
  const results: { type: string; data: EntityRow[] }[] = [];

  for (const t of tables) {
    const { data, error } = await sb
      .from(t)
      .select("*")
      .eq("project_id", projectId)
      .order("created_at", { ascending: false })
      .limit(50);

    if (error) {
      console.error(`getEntitiesByProject(${t}): ${error.message}`);
      continue;
    }
    if (data && data.length > 0) {
      results.push({ type: t, data });
    }
  }
  return results;
}

/**
 * Get entities created or associated with meetings within a time range.
 */
export async function getEntitiesInTimeRange(
  sb: SB,
  from: string,
  to: string,
  entityTypes?: string[],
): Promise<{ type: string; data: EntityRow[] }[]> {
  const types = entityTypes ?? ["todos", "open_items", "blockers", "decisions"];
  const results: { type: string; data: EntityRow[] }[] = [];

  for (const t of types) {
    const { data, error } = await sb
      .from(t)
      .select("*")
      .gte("created_at", from)
      .lte("created_at", to)
      .order("created_at", { ascending: false })
      .limit(100);

    if (error) {
      console.error(`getEntitiesInTimeRange(${t}): ${error.message}`);
      continue;
    }
    if (data && data.length > 0) {
      results.push({ type: t, data });
    }
  }
  return results;
}

/**
 * Get activity log entries within a time range, for delta reports.
 */
export async function getActivityDelta(
  sb: SB,
  from: string,
  to: string,
): Promise<ActivityRow[]> {
  const { data, error } = await sb
    .from("activity_log")
    .select("*")
    .gte("created_at", from)
    .lte("created_at", to)
    .order("created_at", { ascending: false })
    .limit(200);

  if (error) throw new Error(`getActivityDelta: ${error.message}`);
  return data ?? [];
}

/**
 * Get meetings within a time range.
 */
export async function getMeetingsInRange(
  sb: SB,
  from: string,
  to: string,
): Promise<MeetingRow[]> {
  const { data, error } = await sb
    .from("meetings")
    .select("*")
    .gte("meeting_date", from)
    .lte("meeting_date", to)
    .order("meeting_date", { ascending: false })
    .limit(20);

  if (error) throw new Error(`getMeetingsInRange: ${error.message}`);
  return data ?? [];
}

/**
 * Get risk signals: high-prio open todos, active blockers, overdue todos, stale open items.
 */
export async function getRiskSignals(sb: SB): Promise<{
  highPrioOpenTodos: TodoRow[];
  activeBlockers: BlockerRow[];
  overdueTodos: TodoRow[];
  staleOpenItems: OpenItemRow[];
}> {
  const now = new Date().toISOString();
  const fourteenDaysAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();

  const openVariants = getStatusDbVariants("offen");
  const inProgressVariants = getStatusDbVariants("in Arbeit");
  const activeVariants = getStatusDbVariants("aktiv");
  const nonCompletedStatuses = [...new Set([...openVariants, ...inProgressVariants])];
  const openOrActiveStatuses = [...new Set([...openVariants, ...activeVariants])];

  const [highPrio, blockers, overdue, stale] = await Promise.all([
    sb.from("todos")
      .select("*")
      .in("priority", ["hoch", "high"])
      .in("status", nonCompletedStatuses)
      .order("created_at", { ascending: false })
      .limit(20),
    sb.from("blockers")
      .select("*")
      .in("status", openOrActiveStatuses)
      .order("created_at", { ascending: false })
      .limit(20),
    sb.from("todos")
      .select("*")
      .lt("due_date", now.substring(0, 10))
      .in("status", nonCompletedStatuses)
      .order("due_date", { ascending: true })
      .limit(20),
    sb.from("open_items")
      .select("*")
      .in("status", openOrActiveStatuses)
      .lt("created_at", fourteenDaysAgo)
      .order("created_at", { ascending: true })
      .limit(20),
  ]);

  return {
    highPrioOpenTodos: highPrio.data ?? [],
    activeBlockers: blockers.data ?? [],
    overdueTodos: overdue.data ?? [],
    staleOpenItems: stale.data ?? [],
  };
}

/**
 * Get decisions, optionally filtered by meeting IDs.
 */
export async function getDecisions(
  sb: SB,
  meetingIds?: string[],
): Promise<DecisionRow[]> {
  let query = sb.from("decisions").select("*");
  if (meetingIds && meetingIds.length > 0) {
    query = query.in("meeting_id", meetingIds);
  }
  query = query.order("created_at", { ascending: false }).limit(50);
  const { data, error } = await query;

  if (error) throw new Error(`getDecisions: ${error.message}`);
  return data ?? [];
}

/**
 * Count all rows in a table. Returns 0 on error.
 */
export async function countTable(sb: SB, tableName: string): Promise<number> {
  const { count, error } = await sb
    .from(tableName)
    .select("*", { count: "exact", head: true });
  if (error) {
    console.error(`countTable(${tableName}): ${error.message}`);
    return 0;
  }
  return count ?? 0;
}

/**
 * Get entity counts for all main tables. Used for count_query intent.
 */
export async function getEntityCountsOnly(sb: SB): Promise<Record<string, number>> {
  const tables = ["meetings", "todos", "blockers", "open_items", "decisions", "projects"];
  const results = await Promise.all(
    tables.map(async (t) => {
      const { count, error } = await sb
        .from(t)
        .select("*", { count: "exact", head: true });
      return [t, error ? 0 : (count ?? 0)] as [string, number];
    }),
  );
  return Object.fromEntries(results);
}

/**
 * Get status-filtered counts for todos, blockers, open_loops, and meeting counts
 * by time window. Used for count_query intent to give differentiated answers.
 */
export async function getStatusFilteredCounts(sb: SB): Promise<{
  todos: Record<string, number>;
  blockers: Record<string, number>;
  open_loops: Record<string, number>;
  meetings_total: number;
  meetings_last_30_days: number;
  meetings_last_7_days: number;
}> {
  const thirtyDaysAgo = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

  const [todoRows, blockerRows, openLoopRows, meetingsTotal, meetings30, meetings7] = await Promise.all([
    sb.from("todos").select("status"),
    sb.from("blockers").select("status"),
    sb.from("open_loops").select("status"),
    sb.from("meetings").select("*", { count: "exact", head: true }),
    sb.from("meetings").select("*", { count: "exact", head: true }).gte("meeting_date", thirtyDaysAgo),
    sb.from("meetings").select("*", { count: "exact", head: true }).gte("meeting_date", sevenDaysAgo),
  ]);

  const countByStatus = (rows: { status: string | null }[] | null): Record<string, number> => {
    const counts: Record<string, number> = {};
    for (const row of rows ?? []) {
      const s = row.status ?? "unbekannt";
      counts[s] = (counts[s] ?? 0) + 1;
    }
    return counts;
  };

  return {
    todos: countByStatus(todoRows.data),
    blockers: countByStatus(blockerRows.data),
    open_loops: countByStatus(openLoopRows.data),
    meetings_total: meetingsTotal.count ?? 0,
    meetings_last_30_days: meetings30.count ?? 0,
    meetings_last_7_days: meetings7.count ?? 0,
  };
}

/**
 * Search entities by topic anchors using ilike on title/description.
 * Used as fallback when no project match is found or projects table is empty.
 */
export async function searchByTopicAnchor(
  sb: SB,
  anchors: string[],
  entityTypes?: string[],
): Promise<{ type: string; data: EntityRow[] }[]> {
  if (anchors.length === 0) return [];

  const types = entityTypes ?? ["meetings", "todos", "open_items", "blockers", "decisions"];
  const results: { type: string; data: EntityRow[] }[] = [];

  for (const t of types) {
    const allRows: EntityRow[] = [];
    const seenIds = new Set<string>();

    for (const anchor of anchors.slice(0, 5)) { // limit to 5 anchors
      const pattern = `%${anchor}%`;
      let query = sb.from(t).select("*");

      if (t === "meetings") {
        // Search in title only (topics array search requires different approach)
        query = query.ilike("title", pattern);
      } else {
        // title or description
        query = query.or(`title.ilike.${pattern},description.ilike.${pattern}`);
      }

      query = query.order("created_at", { ascending: false }).limit(20);
      const { data, error } = await query;

      if (error) {
        console.error(`searchByTopicAnchor(${t}, ${anchor}): ${error.message}`);
        continue;
      }
      for (const row of (data ?? [])) {
        if (!seenIds.has(row.id)) {
          seenIds.add(row.id);
          allRows.push(row);
        }
      }
    }

    if (allRows.length > 0) {
      results.push({ type: t, data: allRows });
    }
  }

  return results;
}

/**
 * Extract synthetic decision rows from meeting.key_decisions.
 * Used as fallback when the decisions table is empty.
 */
export function extractDecisionsFromMeetings(meetings: MeetingRow[]): Partial<DecisionRow>[] {
  const result: Partial<DecisionRow>[] = [];
  for (const m of meetings) {
    for (const kd of m.key_decisions ?? []) {
      if (kd && kd.trim().length > 0) {
        result.push({
          id: `${m.id}-kd-${result.length}`,
          meeting_id: m.id,
          title: kd.trim(),
          description: null,
          decided_by: null,
          status: "confirmed",
          created_at: m.meeting_date || m.created_at,
          updated_at: null,
        });
      }
    }
  }
  return result;
}

/**
 * Get meetings where a person appears in the participants array.
 * Uses ILIKE on participants::text because participants is a Postgres ARRAY column
 * stored as "Lastname, Firstname" — exact eq() never works for array membership.
 */
export async function getMeetingsByPerson(
  sb: SB,
  person: PersonEntry,
  limit = 20,
): Promise<MeetingRow[]> {
  const filterExpr = buildParticipantFilter(person);
  if (!filterExpr) return [];

  const { data, error } = await sb
    .from("meetings")
    .select("*")
    .or(filterExpr)
    .order("meeting_date", { ascending: false })
    .limit(limit);

  if (error) {
    console.error(`getMeetingsByPerson(${person.canonical_name}): ${error.message}`);
    return [];
  }
  return data ?? [];
}

/**
 * Get meetings where a person is mentioned in title, topics, or ai_summary
 * (but not necessarily listed as a participant).
 * Used as a secondary pass to catch references that didn't make it into participants[].
 */
export async function getMeetingsMentioningPerson(
  sb: SB,
  person: PersonEntry,
  limit = 10,
): Promise<MeetingRow[]> {
  // Build OR filter across title, topics text, and ai_summary
  // Use the person's display_name and last-name patterns
  const namePatterns = person.participant_patterns.map((p) =>
    p.replace(/%/g, "").trim()
  );
  if (namePatterns.length === 0) return [];

  const allRows: MeetingRow[] = [];
  const seenIds = new Set<string>();

  for (const namePart of namePatterns.slice(0, 3)) {
    const pattern = `%${namePart}%`;
    const { data, error } = await sb
      .from("meetings")
      .select("*")
      .or(`title.ilike.${pattern},ai_summary.ilike.${pattern}`)
      .order("meeting_date", { ascending: false })
      .limit(limit);

    if (error) {
      console.error(`getMeetingsMentioningPerson(${person.canonical_name}, ${namePart}): ${error.message}`);
      continue;
    }
    for (const row of (data ?? [])) {
      if (!seenIds.has(row.id)) {
        seenIds.add(row.id);
        allRows.push(row);
      }
    }
  }
  return allRows;
}

/**
 * Get todos/open_items/blockers/decisions for a person, trying ALL known DB name variants.
 * Replaces the old getEntitiesByPerson which only tried a single string and missed records
 * stored as "Lastname, Firstname" vs "Firstname" vs "Full Name".
 */
export async function getEntitiesByPersonFlexible(
  sb: SB,
  person: PersonEntry,
  statusFilter?: string,
  entityTypes?: string[],
): Promise<{ type: string; data: EntityRow[] }[]> {
  const types = entityTypes ?? ["todos", "open_items", "blockers", "decisions"];
  const results: { type: string; data: EntityRow[] }[] = [];
  const nameVariants = getPersonAssigneeVariants(person);

  for (const t of types) {
    let assigneeField: string;
    if (t === "todos") assigneeField = "assignee";
    else if (t === "blockers") assigneeField = "reported_by";
    else if (t === "open_items") assigneeField = "owner";
    else if (t === "decisions") assigneeField = "decided_by";
    else continue;

    const allRows: EntityRow[] = [];
    const seenIds = new Set<string>();

    for (const variant of nameVariants) {
      let query = sb.from(t).select("*").eq(assigneeField, variant);

      if (statusFilter) {
        const variants = getStatusDbVariants(statusFilter);
        query = query.in("status", variants);
      }

      query = query.order("created_at", { ascending: false }).limit(50);
      const { data, error } = await query;

      if (error) {
        console.error(`getEntitiesByPersonFlexible(${t}, ${variant}): ${error.message}`);
        continue;
      }
      for (const row of (data ?? [])) {
        if (!seenIds.has(row.id)) {
          seenIds.add(row.id);
          allRows.push(row);
        }
      }
    }

    if (allRows.length > 0) {
      results.push({ type: t, data: allRows });
    }
  }
  return results;
}

/**
 * Get commitments for a person using ILIKE on all known name variants.
 * Commitments have a free-text `person` field, so exact eq() misses many records.
 */
export async function getCommitmentsByPerson(
  sb: SB,
  nameVariants: string[],
): Promise<CommitmentRow[]> {
  if (nameVariants.length === 0) return [];
  const allRows: CommitmentRow[] = [];
  const seenIds = new Set<string>();

  for (const variant of nameVariants.slice(0, 8)) {
    const { data, error } = await sb
      .from("commitments")
      .select("*")
      .ilike("person", `%${variant}%`)
      .order("created_at", { ascending: false })
      .limit(30);

    if (error) {
      console.error(`getCommitmentsByPerson(${variant}): ${error.message}`);
      continue;
    }
    for (const row of (data ?? [])) {
      if (!seenIds.has(row.id)) {
        seenIds.add(row.id);
        allRows.push(row);
      }
    }
  }
  return allRows;
}

/**
 * Search decisions by keyword terms using ILIKE on title and description.
 */
export async function searchDecisionsByKeywords(
  sb: SB,
  terms: string[],
): Promise<DecisionRow[]> {
  if (terms.length === 0) return [];
  const allRows: DecisionRow[] = [];
  const seenIds = new Set<string>();

  for (const term of terms.slice(0, 5)) {
    const pattern = `%${term}%`;
    const { data, error } = await sb
      .from("decisions")
      .select("*")
      .or(`title.ilike.${pattern},description.ilike.${pattern}`)
      .order("decision_date", { ascending: false })
      .limit(20);

    if (error) {
      console.error(`searchDecisionsByKeywords(${term}): ${error.message}`);
      continue;
    }
    for (const row of (data ?? [])) {
      if (!seenIds.has(row.id)) {
        seenIds.add(row.id);
        allRows.push(row);
      }
    }
  }
  return allRows;
}

/**
 * Get open loops, optionally filtered by keyword in question_text or assigned_to ILIKE.
 */
export async function getOpenLoopsByKeyword(
  sb: SB,
  terms?: string[],
  assignedToVariants?: string[],
): Promise<OpenLoopRow[]> {
  const allRows: OpenLoopRow[] = [];
  const seenIds = new Set<string>();

  if (assignedToVariants && assignedToVariants.length > 0) {
    for (const variant of assignedToVariants.slice(0, 5)) {
      const { data, error } = await sb
        .from("open_loops")
        .select("*")
        .ilike("assigned_to", `%${variant}%`)
        .order("created_at", { ascending: false })
        .limit(20);

      if (error) {
        console.error(`getOpenLoopsByKeyword assigned_to(${variant}): ${error.message}`);
        continue;
      }
      for (const row of (data ?? [])) {
        if (!seenIds.has(row.id)) { seenIds.add(row.id); allRows.push(row); }
      }
    }
  } else if (terms && terms.length > 0) {
    for (const term of terms.slice(0, 5)) {
      const { data, error } = await sb
        .from("open_loops")
        .select("*")
        .ilike("question_text", `%${term}%`)
        .order("created_at", { ascending: false })
        .limit(20);

      if (error) {
        console.error(`getOpenLoopsByKeyword term(${term}): ${error.message}`);
        continue;
      }
      for (const row of (data ?? [])) {
        if (!seenIds.has(row.id)) { seenIds.add(row.id); allRows.push(row); }
      }
    }
  } else {
    // No filter: return recent open loops
    const { data, error } = await sb
      .from("open_loops")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(30);

    if (error) {
      console.error(`getOpenLoopsByKeyword(all): ${error.message}`);
    } else {
      for (const row of (data ?? [])) allRows.push(row);
    }
  }
  return allRows;
}
