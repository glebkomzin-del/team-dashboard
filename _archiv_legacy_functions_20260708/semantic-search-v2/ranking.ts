// ranking.ts — Score, rank, and annotate search results via Reciprocal Rank Fusion

import type { RetrievalPlan } from "./retrieval_planner.ts";

export interface ScoredResult {
  entity_type: string;
  entity_id: string;
  title: string;
  status: string | null;
  priority: string | null;
  assignee: string | null; // or owner / reported_by
  project_id: string | null;
  project_name: string | null;
  date: string | null;
  content_excerpt: string;
  match_reason: string[];
  score: number;
  similarity: number;
  inferred_relation: string | null;
  source?: string;             // retrieval source: 'vector'|'sql'|'keyword'|'decisions'|'commitments'|'open_loops'
  rrf_score?: number;          // accumulated RRF score (Σ weight/(k+rank))
  retrieval_sources?: string[]; // all sources this item appeared in
  boost_reasons?: string[];    // deterministic boosts applied
  // deno-lint-ignore no-explicit-any
  raw: Record<string, any>;
}

// ── Entity helpers ────────────────────────────────────────────────────────────

// deno-lint-ignore no-explicit-any
function getPersonField(raw: Record<string, any>, entityType: string): string | null {
  if (entityType === "todos") return raw.assignee ?? null;
  if (entityType === "blockers") return raw.reported_by ?? null;
  if (entityType === "open_items") return raw.owner ?? null;
  if (entityType === "decisions") return raw.decided_by ?? null;
  if (entityType === "commitments") return raw.person ?? null;
  if (entityType === "open_loops") return raw.assigned_to ?? null;
  return null;
}

// deno-lint-ignore no-explicit-any
function toScoredResult(raw: Record<string, any>, entityType: string, similarity: number): ScoredResult {
  const description = raw.description ?? raw.ai_summary ?? raw.executive_summary ?? "";
  return {
    entity_type: entityType,
    entity_id: raw.id,
    title: raw.title ?? raw.name ?? raw.commitment_text ?? raw.question_text ?? "Unbenannt",
    status: raw.status ?? null,
    priority: raw.priority ?? null,
    assignee: getPersonField(raw, entityType),
    project_id: raw.project_id ?? null,
    project_name: null,
    date: raw.meeting_date ?? raw.due_date ?? raw.created_at ?? null,
    content_excerpt: typeof description === "string" ? description.substring(0, 300) : "",
    match_reason: [],
    score: 0,
    similarity,
    inferred_relation: null,
    raw,
  };
}

// ── RRF Fusion ────────────────────────────────────────────────────────────────

const RRF_K = 60;

export function fuseWithRRF(
  candidateLists: Array<{
    name: string;
    // deno-lint-ignore no-explicit-any
    items: any[];
    weight?: number;
  }>,
  // deno-lint-ignore no-explicit-any
): any[] {
  // deno-lint-ignore no-explicit-any
  const scoreMap = new Map<string, { item: any; rrf_score: number; sources: string[] }>();

  for (const list of candidateLists) {
    const weight = list.weight ?? 1.0;
    list.items.forEach((item, index) => {
      const rank = index + 1;
      const rrfContribution = weight / (RRF_K + rank);
      const id = item.id ?? `${item.entity_type}_${item.entity_id}`;

      if (scoreMap.has(id)) {
        const existing = scoreMap.get(id)!;
        existing.rrf_score += rrfContribution;
        if (!existing.sources.includes(list.name)) {
          existing.sources.push(list.name);
        }
      } else {
        scoreMap.set(id, {
          item: { ...item },
          rrf_score: rrfContribution,
          sources: [list.name],
        });
      }
    });
  }

  return Array.from(scoreMap.values())
    .sort((a, b) => b.rrf_score - a.rrf_score)
    .map((entry) => ({
      ...entry.item,
      rrf_score: entry.rrf_score,
      retrieval_sources: entry.sources,
      score: entry.rrf_score,
    }));
}

// ── Deterministic Boosts ──────────────────────────────────────────────────────

export function applyDeterministicBoosts(
  // deno-lint-ignore no-explicit-any
  items: any[],
  plan: RetrievalPlan,
  // deno-lint-ignore no-explicit-any
): any[] {
  return items.map((item) => {
    let boost = 0;
    const reasons: string[] = [];

    // Boost 1: Exact person match
    if (plan.persons?.length > 0) {
      const personNames = plan.persons.map((p) => p.toLowerCase());
      const itemText = [
        item.speaker, item.person, item.title,
        item.content_excerpt, item.raw?.decision_text, item.raw?.commitment_text,
      ].filter(Boolean).join(" ").toLowerCase();
      if (personNames.some((name) => itemText.includes(name))) {
        boost += 0.15;
        reasons.push("person_match");
      }
    }

    // Boost 2: Keyword/anchor match (topic_anchors includes Haiku exact_terms)
    if (plan.topic_anchors?.length > 0) {
      const itemText = [
        item.content_excerpt, item.title,
        item.raw?.decision_text, item.raw?.commitment_text,
      ].filter(Boolean).join(" ").toLowerCase();
      const matches = plan.topic_anchors.filter((term) =>
        itemText.includes(term.toLowerCase())
      );
      if (matches.length > 0) {
        boost += 0.10 * Math.min(matches.length, 2);
        reasons.push(`keyword_match:${matches.join(",")}`);
      }
    }

    // Boost 3: Recency — only for temporally-oriented queries
    const isTemporalQuery =
      plan.intent === "latest_entities" ||
      plan.intent === "delta_report" ||
      plan.intent === "time_range_query";

    if (isTemporalQuery && item.date) {
      const daysSince = (Date.now() - new Date(item.date).getTime()) / (1000 * 60 * 60 * 24);
      if (daysSince < 7) { boost += 0.12; reasons.push("very_recent"); }
      else if (daysSince < 30) { boost += 0.06; reasons.push("recent"); }
    }

    // Boost 4a: Recency for decision_history
    if (plan.intent === "decision_history" && item.entity_type === "decisions") {
      const dateStr = item.raw?.decision_date ?? item.date;
      const daysSince = dateStr
        ? (Date.now() - new Date(dateStr).getTime()) / (1000 * 60 * 60 * 24)
        : 999;
      if (daysSince < 14) { boost += 0.10; reasons.push("decision_recent_14d"); }
      else if (daysSince < 30) { boost += 0.05; reasons.push("decision_recent_30d"); }
      else if (daysSince < 90) { boost += 0.02; reasons.push("decision_recent_90d"); }
    }

    // Boost 4b: Entity type match for decisions/commitments
    if (plan.retrieval_flags?.include_decisions && item.entity_type === "decisions") {
      boost += 0.08;
      reasons.push("decision_type_match");
    }
    if (plan.retrieval_flags?.include_commitments && item.entity_type === "commitments") {
      boost += 0.08;
      reasons.push("commitment_type_match");
    }

    const finalScore = (item.rrf_score ?? 0) + boost;
    return {
      ...item,
      rrf_score: finalScore,
      score: finalScore,
      boost_reasons: reasons.length > 0 ? reasons : undefined,
    };
  }).sort((a, b) => b.rrf_score - a.rrf_score);
}

// ── Source grouping helpers ───────────────────────────────────────────────────

// deno-lint-ignore no-explicit-any
function groupBySource(candidates: any[]): Record<string, any[]> {
  // deno-lint-ignore no-explicit-any
  const groups: Record<string, any[]> = {};
  for (const item of candidates) {
    const src = item.source ?? item.retrieval_source ?? "vector";
    if (!groups[src]) groups[src] = [];
    groups[src].push(item);
  }
  return groups;
}

function getListWeight(sourceName: string, plan: RetrievalPlan): number {
  // v2: chunk-rollup meeting candidates lead — granular signal beats coarse meeting vectors.
  if (sourceName === "chunk_meeting") return 1.3;
  if (sourceName === "transcript" && plan.needs_raw_evidence) return 1.2;
  if (sourceName === "sql" && plan.retrievalMode === "sql_direct") return 1.2;
  return 1.0;
}

// ── Main ranking entry point ──────────────────────────────────────────────────

/**
 * Rank and score a mixed set of results using Reciprocal Rank Fusion.
 * Each candidate must have a `source` field indicating its retrieval list.
 * Items appearing in multiple source lists are rewarded — they score higher
 * than items that only appeared in one list.
 */
export function rankAndScore(
  candidates: ScoredResult[],
  plan: RetrievalPlan,
  options: { limit?: number } = {},
): ScoredResult[] {
  if (candidates.length === 0) return candidates;

  const bySource = groupBySource(candidates);
  const lists = Object.entries(bySource)
    .filter(([, items]) => items.length > 0)
    .map(([name, items]) => ({ name, items, weight: getListWeight(name, plan) }));

  if (lists.length === 0) return candidates;

  const fused = fuseWithRRF(lists) as ScoredResult[];
  const boosted = applyDeterministicBoosts(fused, plan) as ScoredResult[];
  return boosted.slice(0, options.limit ?? 50);
}

// ── Relation inference ────────────────────────────────────────────────────────

/**
 * Infer temporal relations between entities and meetings.
 * Marks entities created within 24h of a meeting as related.
 */
export function inferRelations(entities: ScoredResult[]): ScoredResult[] {
  const meetings = entities.filter((e) => e.entity_type === "meetings" && e.date);
  const meetingDates = meetings.map((m) => ({
    id: m.entity_id,
    date: new Date(m.date!),
  }));

  if (meetingDates.length === 0) return entities;

  const TWENTY_FOUR_HOURS = 24 * 60 * 60 * 1000;

  for (const entity of entities) {
    if (entity.entity_type === "meetings") continue;
    const entityDate = entity.raw.created_at ? new Date(entity.raw.created_at) : null;
    if (!entityDate) continue;

    for (const meeting of meetingDates) {
      const diff = Math.abs(entityDate.getTime() - meeting.date.getTime());
      if (diff <= TWENTY_FOUR_HOURS) {
        entity.inferred_relation = "temporal_proximity_to_meeting";
        if (!entity.match_reason.includes("inferred:meeting_proximity")) {
          entity.match_reason.push("inferred:meeting_proximity");
        }
        break;
      }
    }
  }

  return entities;
}

// ── Conversion helpers ────────────────────────────────────────────────────────

export function rawToScoredResults(
  // deno-lint-ignore no-explicit-any
  groups: { type: string; data: Record<string, any>[] }[],
): ScoredResult[] {
  const results: ScoredResult[] = [];
  for (const group of groups) {
    for (const row of group.data) {
      results.push(toScoredResult(row, group.type, 0));
    }
  }
  return results;
}

export function vectorToScoredResults(
  vectorMatches: { entity_type: string; entity_id: string; content: string; similarity: number }[],
  // deno-lint-ignore no-explicit-any
  liveData: Map<string, Record<string, any>>,
): ScoredResult[] {
  const results: ScoredResult[] = [];
  for (const vm of vectorMatches) {
    const tableType = vm.entity_type.endsWith("s") ? vm.entity_type : vm.entity_type + "s";
    const key = `${tableType}:${vm.entity_id}`;
    const live = liveData.get(key);
    if (live) {
      results.push(toScoredResult(live, tableType, vm.similarity));
    } else {
      results.push({
        entity_type: vm.entity_type,
        entity_id: vm.entity_id,
        title: vm.content.substring(0, 100),
        status: null,
        priority: null,
        assignee: null,
        project_id: null,
        project_name: null,
        date: null,
        content_excerpt: vm.content.substring(0, 300),
        match_reason: [`similarity:${vm.similarity.toFixed(2)}`],
        score: 0,
        similarity: vm.similarity,
        inferred_relation: null,
        raw: {},
      });
    }
  }
  return results;
}
