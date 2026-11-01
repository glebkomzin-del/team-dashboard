// context_builder.ts — Build structured context packets for Claude, with budgeting and audit

import type { RetrievalPlan } from "./retrieval_planner.ts";
import type { ScoredResult } from "./ranking.ts";
import type { ActivityRow } from "./sql_retriever.ts";

// ── Context budget constants ──
const CONTEXT_LIMITS: Record<string, { fullDetail: number; compact: number }> = {
  person_status_query: { fullDetail: 30, compact: 20 },
  decision_history:    { fullDetail: 20, compact: 20 },
  open_items:          { fullDetail: 35, compact: 15 },
  // v2: topic/semantic brauchen breite Themenabdeckung über mehrere Meetings.
  // Sonst landen gerollte Meeting-Kandidaten im Kompakt-Block (120 Zeichen)
  // und verlieren Inhalt (z.B. "S/4HANA").
  topic_query:         { fullDetail: 25, compact: 20 },
  semantic_search:     { fullDetail: 25, compact: 20 },
  default:             { fullDetail: 10, compact: 20 },
};

// Per-entity-type minimum slots guaranteed within the full-detail window.
// Prevents high-scoring but lower-relevance entity types from crowding out
// critical types (e.g. decisions pushed out by todos in person queries).
const ENTITY_MIN_SLOTS: Record<string, Record<string, number>> = {
  person_status_query: {
    decisions:   10,
    commitments: 10,
    open_loops:   5,
  },
  decision_history: {
    decisions: 15,
  },
  open_items: {
    todos:      15,
    blockers:   10,
    open_loops: 10,
  },
};
const MAX_CHARS_MEETING_EXCERPT = 1200;
const MAX_CHARS_ENTITY_EXCERPT = 600;
const MAX_CHARS_COMPACT_EXCERPT = 120;
const MAX_ACTIVITY_GROUPS = 15;

export interface Aggregations {
  byStatus: Record<string, number>;
  byPriority: Record<string, number>;
  byEntityType: Record<string, number>;
}

export interface RiskSignals {
  highPrioOpenTodos: { title: string; assignee: string | null; due_date: string | null }[];
  activeBlockers: { title: string; reported_by: string | null; status: string | null }[];
  overdueTodos: { title: string; assignee: string | null; due_date: string | null }[];
  staleOpenItems: { title: string; owner: string | null; created_at: string }[];
}

export interface RetrievalAudit {
  query: string;
  intent: string;
  detected: {
    persons: string[];
    projects: string[];
    topicAnchors: string[];
    timeRange: { from: string; to: string; phrase: string } | null;
    statusFilters: string[];
  };
  tables_queried: string[];
  returned_counts: Record<string, number>;
  full_detail_count: number;
  compact_count: number;
  aggregated_count: number;
  vector_search_used: boolean;
  fallback_used: string[];
  warnings: string[];
  retrieval_completeness: "complete" | "partial" | "minimal";
  context_completeness: "full" | "partial" | "aggregated_only";
  answer_confidence: "high" | "medium" | "low";
  timestamp: string;
}

/**
 * Compute aggregations from scored results.
 */
export function computeAggregations(results: ScoredResult[]): Aggregations {
  const byStatus: Record<string, number> = {};
  const byPriority: Record<string, number> = {};
  const byEntityType: Record<string, number> = {};

  for (const r of results) {
    if (r.status) byStatus[r.status] = (byStatus[r.status] ?? 0) + 1;
    if (r.priority) byPriority[r.priority] = (byPriority[r.priority] ?? 0) + 1;
    byEntityType[r.entity_type] = (byEntityType[r.entity_type] ?? 0) + 1;
  }

  return { byStatus, byPriority, byEntityType };
}

/**
 * Format activity delta with aggregation, capped at MAX_ACTIVITY_GROUPS.
 */
function formatActivityDelta(activities: ActivityRow[]): string {
  if (activities.length === 0) return "Keine Aktivitäten im Zeitraum.";

  // Group by entity_type + action
  const groups: Record<string, ActivityRow[]> = {};
  for (const a of activities) {
    const key = `${a.entity_type}:${a.action}`;
    if (!groups[key]) groups[key] = [];
    groups[key].push(a);
  }

  // Sort groups by size descending, cap at MAX_ACTIVITY_GROUPS
  const sortedGroups = Object.entries(groups)
    .sort(([, a], [, b]) => b.length - a.length)
    .slice(0, MAX_ACTIVITY_GROUPS);

  const lines: string[] = [];
  lines.push(`Aktivitäten (${activities.length} gesamt, ${sortedGroups.length} Gruppen gezeigt):`);

  for (const [key, items] of sortedGroups) {
    const [entityType, action] = key.split(":");
    lines.push(`\n  ${entityType} — ${action}: ${items.length} Einträge`);
    // Show max 5 details per group
    for (const item of items.slice(0, 5)) {
      const detail = item.field_changed
        ? `${item.field_changed}: "${item.old_value ?? "-"}" → "${item.new_value ?? "-"}"`
        : item.note ?? item.new_value ?? "";
      const snippet = detail.length > 100 ? detail.substring(0, 100) + "…" : detail;
      lines.push(`    • [${item.entity_id.substring(0, 8)}] ${snippet} (${item.created_at.substring(0, 10)})`);
    }
    if (items.length > 5) {
      lines.push(`    … und ${items.length - 5} weitere`);
    }
  }

  if (Object.keys(groups).length > MAX_ACTIVITY_GROUPS) {
    lines.push(`\n  … und ${Object.keys(groups).length - MAX_ACTIVITY_GROUPS} weitere Gruppen (${activities.length} Aktivitäten gesamt)`);
  }

  return lines.join("\n");
}

/**
 * Format a single item in Full Detail mode.
 */
function formatItemFull(item: ScoredResult): string {
  const lines: string[] = [];
  lines.push(`• [${item.entity_type.toUpperCase()}] ${item.title}`);
  lines.push(`  ID: ${item.entity_id}`);
  if (item.status) lines.push(`  Status: ${item.status}`);
  if (item.priority) lines.push(`  Priorität: ${item.priority}`);
  if (item.assignee) lines.push(`  Zuständig: ${item.assignee}`);
  if (item.project_name) lines.push(`  Projekt: ${item.project_name}`);
  else if (item.project_id) lines.push(`  Projekt-ID: ${item.project_id}`);
  if (item.date) lines.push(`  Datum: ${item.date.substring(0, 10)}`);
  if (item.content_excerpt) {
    const maxLen = item.entity_type === "meetings" ? MAX_CHARS_MEETING_EXCERPT : MAX_CHARS_ENTITY_EXCERPT;
    const excerpt = item.content_excerpt.length > maxLen
      ? item.content_excerpt.substring(0, maxLen) + "…"
      : item.content_excerpt;
    lines.push(`  Inhalt: ${excerpt}`);
  }
  if (item.match_reason?.length > 0) lines.push(`  Treffer: ${item.match_reason.join(", ")}`);
  if (item.inferred_relation) lines.push(`  Beziehung: ${item.inferred_relation}`);
  return lines.join("\n");
}

/**
 * Format a single item in Compact mode.
 */
function formatItemCompact(item: ScoredResult): string {
  const parts: string[] = [`[${item.entity_type}] ${item.title}`];
  if (item.status) parts.push(`Status: ${item.status}`);
  if (item.priority) parts.push(`Prio: ${item.priority}`);
  if (item.assignee) parts.push(`→ ${item.assignee}`);
  if (item.date) parts.push(item.date.substring(0, 10));
  if (item.content_excerpt) {
    const excerpt = item.content_excerpt.length > MAX_CHARS_COMPACT_EXCERPT
      ? item.content_excerpt.substring(0, MAX_CHARS_COMPACT_EXCERPT) + "…"
      : item.content_excerpt;
    parts.push(`| ${excerpt}`);
  }
  return "  • " + parts.join(" | ");
}

/**
 * Build the full context packet string for Claude, with context budgeting.
 * Returns context string plus budget usage for audit.
 */
export interface TranscriptExcerpt {
  speaker: string;
  content: string;
  chunk_index: number;
  meeting_id: string;
}

export function buildContextPacket(
  intent: RetrievalPlan,
  rankedResults: ScoredResult[],
  aggregations: Aggregations,
  riskSignals: RiskSignals | null,
  warnings: string[],
  activityDelta?: ActivityRow[],
  transcriptExcerpts?: TranscriptExcerpt[],
): { context: string; fullDetailCount: number; compactCount: number; aggregatedCount: number } {
  const sections: string[] = [];

  // === SUCHANFRAGE ===
  sections.push("=== SUCHANFRAGE ===");
  sections.push(`Absicht: ${intent.intent}`);
  sections.push(`Retrieval-Modus: ${intent.retrievalMode}`);
  if (intent.persons.length > 0) sections.push(`Personen: ${intent.persons.join(", ")}`);
  if (intent.projects.length > 0) sections.push(`Projekte: ${intent.projects.map((p) => p.name).join(", ")}`);
  if (intent.topic_anchors.length > 0) sections.push(`Themen-Anker: ${intent.topic_anchors.join(", ")}`);
  if (intent.time_range) {
    sections.push(`Zeitraum: ${intent.time_range.phrase} (${intent.time_range.from.substring(0, 10)} bis ${intent.time_range.to.substring(0, 10)})`);
  }
  if (intent.statuses.length > 0) sections.push(`Status-Filter: ${intent.statuses.join(", ")}`);
  if (intent.priorities.length > 0) sections.push(`Prioritäts-Filter: ${intent.priorities.join(", ")}`);
  if (intent.primary_tables.length > 0) sections.push(`Abgefragte Tabellen: ${intent.primary_tables.join(", ")}`);
  sections.push(`Semantische Query: "${intent.semantic_query}"`);
  sections.push("");

  // Apply intent-aware context budget with per-entity-type slot reservation.
  // Reserved types are guaranteed to appear in full-detail even if their RRF
  // score is lower than other entity types (e.g. decisions vs. todos).
  const { fullDetail: MAX_FULL_DETAIL, compact: MAX_COMPACT } =
    CONTEXT_LIMITS[intent.intent] ?? CONTEXT_LIMITS.default;
  const entityMins = ENTITY_MIN_SLOTS[intent.intent] ?? {};

  const reservedItems: ScoredResult[] = [];
  const reservedIds = new Set<string>();

  for (const [entityType, minCount] of Object.entries(entityMins)) {
    const typeItems = rankedResults.filter((r) => r.entity_type === entityType);
    for (const item of typeItems.slice(0, minCount)) {
      if (!reservedIds.has(item.entity_id)) {
        reservedItems.push(item);
        reservedIds.add(item.entity_id);
      }
    }
  }

  const remainingItems = rankedResults.filter((r) => !reservedIds.has(r.entity_id));
  const fillCount = Math.max(0, MAX_FULL_DETAIL - reservedItems.length);
  const fullDetailItems = [...reservedItems, ...remainingItems.slice(0, fillCount)];
  const fullDetailIds = new Set(fullDetailItems.map((r) => r.entity_id));

  const compactItems = rankedResults
    .filter((r) => !fullDetailIds.has(r.entity_id))
    .slice(0, MAX_COMPACT);
  const compactIds = new Set(compactItems.map((r) => r.entity_id));

  const aggregatedItems = rankedResults.filter(
    (r) => !fullDetailIds.has(r.entity_id) && !compactIds.has(r.entity_id),
  );

  const fullDetailCount = fullDetailItems.length;
  const compactCount = compactItems.length;
  const aggregatedCount = aggregatedItems.length;
  const totalCount = rankedResults.length;

  // === ERGEBNISSE ===
  sections.push(`=== ERGEBNISSE (${totalCount} Treffer gesamt) ===`);

  if (fullDetailItems.length > 0) {
    sections.push(`\n--- VOLLSTÄNDIG (${fullDetailItems.length}) ---`);
    // Group by entity_type for readability
    const grouped: Record<string, ScoredResult[]> = {};
    for (const r of fullDetailItems) {
      if (!grouped[r.entity_type]) grouped[r.entity_type] = [];
      grouped[r.entity_type].push(r);
    }
    for (const [entityType, items] of Object.entries(grouped)) {
      sections.push(`\n[${entityType.toUpperCase()}]`);
      for (const item of items) {
        sections.push(formatItemFull(item));
        sections.push("");
      }
    }
  }

  if (compactItems.length > 0) {
    sections.push(`\n--- KOMPAKT (${compactItems.length}) ---`);
    for (const item of compactItems) {
      sections.push(formatItemCompact(item));
    }
    sections.push("");
  }

  if (aggregatedItems.length > 0) {
    sections.push(`\n--- AGGREGIERT (${aggregatedItems.length} weitere, nur Statistik) ---`);
    // Just show type/status counts for remaining
    const aggByType: Record<string, number> = {};
    const aggByStatus: Record<string, number> = {};
    for (const r of aggregatedItems) {
      aggByType[r.entity_type] = (aggByType[r.entity_type] ?? 0) + 1;
      if (r.status) aggByStatus[r.status] = (aggByStatus[r.status] ?? 0) + 1;
    }
    for (const [t, c] of Object.entries(aggByType)) sections.push(`  ${t}: ${c}`);
    if (Object.keys(aggByStatus).length > 0) {
      sections.push("  Status-Verteilung: " + Object.entries(aggByStatus).map(([k, v]) => `${k}=${v}`).join(", "));
    }
    sections.push(`  Hinweis: Diese ${aggregatedItems.length} Einträge wurden aus Platzgründen nicht vollständig übertragen.`);
    sections.push("");
  }

  // === ORIGINALTRANSKRIPT-AUSSCHNITTE ===
  if (transcriptExcerpts && transcriptExcerpts.length > 0) {
    sections.push("## Originaltranskript-Ausschnitte (Rohdaten)");
    for (const ex of transcriptExcerpts) {
      sections.push(`[Meeting-ID: ${ex.meeting_id} · Chunk ${ex.chunk_index}]`);
      sections.push(`Speaker: ${ex.speaker}`);
      sections.push(`"${ex.content}"`);
      sections.push("---");
    }
    sections.push("");
  }

  // === AKTIVITÄTEN / DELTA ===
  if (activityDelta && activityDelta.length > 0) {
    sections.push("=== AKTIVITÄTEN / DELTA ===");
    sections.push(formatActivityDelta(activityDelta));
    sections.push("");
  }

  // === AGGREGATIONEN ===
  sections.push("=== STATISTIK ===");
  if (Object.keys(aggregations.byStatus).length > 0) {
    sections.push("Nach Status: " + Object.entries(aggregations.byStatus).map(([k, v]) => `${k}=${v}`).join(", "));
  }
  if (Object.keys(aggregations.byPriority).length > 0) {
    sections.push("Nach Priorität: " + Object.entries(aggregations.byPriority).map(([k, v]) => `${k}=${v}`).join(", "));
  }
  if (Object.keys(aggregations.byEntityType).length > 0) {
    sections.push("Nach Typ: " + Object.entries(aggregations.byEntityType).map(([k, v]) => `${k}=${v}`).join(", "));
  }
  sections.push("");

  // === RISIKOSIGNALE ===
  if (riskSignals) {
    sections.push("=== RISIKOSIGNALE ===");
    if (riskSignals.highPrioOpenTodos.length > 0) {
      sections.push("Hohe Priorität, offen:");
      for (const t of riskSignals.highPrioOpenTodos) {
        sections.push(`  • ${t.title} (${t.assignee ?? "k.A."}, Fällig: ${t.due_date ?? "k.A."})`);
      }
    }
    if (riskSignals.activeBlockers.length > 0) {
      sections.push("Aktive Blocker:");
      for (const b of riskSignals.activeBlockers) {
        sections.push(`  • ${b.title} (${b.reported_by ?? "k.A."}, Status: ${b.status ?? "k.A."})`);
      }
    }
    if (riskSignals.overdueTodos.length > 0) {
      sections.push("Überfällige Todos:");
      for (const t of riskSignals.overdueTodos) {
        sections.push(`  • ${t.title} (${t.assignee ?? "k.A."}, Fällig: ${t.due_date ?? "k.A."})`);
      }
    }
    if (riskSignals.staleOpenItems.length > 0) {
      sections.push("Veraltete offene Punkte (>14 Tage):");
      for (const o of riskSignals.staleOpenItems) {
        sections.push(`  • ${o.title} (${o.owner ?? "k.A."}, Erstellt: ${o.created_at.substring(0, 10)})`);
      }
    }
    if (
      riskSignals.highPrioOpenTodos.length === 0 &&
      riskSignals.activeBlockers.length === 0 &&
      riskSignals.overdueTodos.length === 0 &&
      riskSignals.staleOpenItems.length === 0
    ) {
      sections.push("Keine akuten Risikosignale erkannt.");
    }
    sections.push("");
  }

  // === WARNUNGEN ===
  if (warnings.length > 0) {
    sections.push("=== WARNUNGEN ===");
    for (const w of warnings) {
      sections.push(`WARNUNG: ${w}`);
    }
    sections.push("");
  }

  return {
    context: sections.join("\n"),
    fullDetailCount,
    compactCount,
    aggregatedCount,
  };
}

/**
 * Build a RetrievalAudit object from all retrieval metadata.
 */
export function buildAudit(
  intent: RetrievalPlan,
  tablesQueried: string[],
  returnedCounts: Record<string, number>,
  fullDetailCount: number,
  compactCount: number,
  aggregatedCount: number,
  vectorSearchUsed: boolean,
  fallbackUsed: string[],
  warnings: string[],
): RetrievalAudit {
  const totalReturned = Object.values(returnedCounts).reduce((s, v) => s + v, 0);

  // Assess retrieval completeness
  let retrieval_completeness: RetrievalAudit["retrieval_completeness"] = "complete";
  if (totalReturned === 0) {
    retrieval_completeness = "minimal";
  } else if (warnings.some((w) => w.includes("empty") || w.includes("fallback"))) {
    retrieval_completeness = "partial";
  }

  // Assess context completeness
  let context_completeness: RetrievalAudit["context_completeness"] = "full";
  if (aggregatedCount > 0 && fullDetailCount + compactCount === 0) {
    context_completeness = "aggregated_only";
  } else if (aggregatedCount > fullDetailCount + compactCount) {
    context_completeness = "partial";
  }

  // Assess answer confidence
  let answer_confidence: RetrievalAudit["answer_confidence"] = "high";
  if (retrieval_completeness === "minimal" || totalReturned === 0) {
    answer_confidence = "low";
  } else if (retrieval_completeness === "partial" || fallbackUsed.length > 0) {
    answer_confidence = "medium";
  }

  return {
    query: intent.original_query,
    intent: intent.intent,
    detected: {
      persons: intent.persons,
      projects: intent.projects.map((p) => p.name),
      topicAnchors: intent.topic_anchors,
      timeRange: intent.time_range
        ? { from: intent.time_range.from, to: intent.time_range.to, phrase: intent.time_range.phrase }
        : null,
      statusFilters: intent.statuses,
    },
    tables_queried: tablesQueried,
    returned_counts: returnedCounts,
    full_detail_count: fullDetailCount,
    compact_count: compactCount,
    aggregated_count: aggregatedCount,
    vector_search_used: vectorSearchUsed,
    fallback_used: fallbackUsed,
    warnings,
    retrieval_completeness,
    context_completeness,
    answer_confidence,
    timestamp: new Date().toISOString(),
  };
}

/**
 * Format a RetrievalAudit as readable Markdown for source_intent answers.
 */
export function formatAuditAsMarkdown(audit: RetrievalAudit): string {
  const lines: string[] = [];
  lines.push("## Retrieval-Audit");
  lines.push("");
  lines.push(`**Anfrage:** "${audit.query}"`);
  lines.push(`**Erkannte Absicht:** ${audit.intent}`);
  lines.push(`**Zeitstempel:** ${audit.timestamp.substring(0, 19).replace("T", " ")} UTC`);
  lines.push("");

  lines.push("### Erkannte Entitäten");
  if (audit.detected.persons.length > 0) lines.push(`- **Personen:** ${audit.detected.persons.join(", ")}`);
  if (audit.detected.projects.length > 0) lines.push(`- **Projekte:** ${audit.detected.projects.join(", ")}`);
  if (audit.detected.topicAnchors.length > 0) lines.push(`- **Themen-Anker:** ${audit.detected.topicAnchors.join(", ")}`);
  if (audit.detected.statusFilters.length > 0) lines.push(`- **Status-Filter:** ${audit.detected.statusFilters.join(", ")}`);
  if (audit.detected.timeRange) {
    lines.push(`- **Zeitraum:** ${audit.detected.timeRange.phrase} (${audit.detected.timeRange.from.substring(0, 10)} – ${audit.detected.timeRange.to.substring(0, 10)})`);
  }
  if (
    audit.detected.persons.length === 0 &&
    audit.detected.projects.length === 0 &&
    audit.detected.topicAnchors.length === 0 &&
    !audit.detected.timeRange
  ) {
    lines.push("- Keine spezifischen Entitäten erkannt (semantische Suche)");
  }
  lines.push("");

  lines.push("### Datenbankzugriff");
  if (audit.tables_queried.length > 0) {
    lines.push(`**Abgefragte Tabellen:** ${audit.tables_queried.join(", ")}`);
  } else {
    lines.push("**Abgefragte Tabellen:** keine (kein Datenbankzugriff)");
  }
  lines.push("");

  if (Object.keys(audit.returned_counts).length > 0) {
    lines.push("**Gefundene Einträge:**");
    for (const [table, count] of Object.entries(audit.returned_counts)) {
      lines.push(`- ${table}: ${count}`);
    }
    lines.push("");
  }

  lines.push("### Kontext-Budget");
  lines.push(`- Vollständig übertragen: **${audit.full_detail_count}** Einträge`);
  lines.push(`- Kompakt übertragen: **${audit.compact_count}** Einträge`);
  lines.push(`- Aggregiert (nur Statistik): **${audit.aggregated_count}** Einträge`);
  if (audit.vector_search_used) lines.push("- Vektorsuche: verwendet");
  lines.push("");

  lines.push("### Qualitätsmetriken");
  lines.push(`- **Retrieval-Vollständigkeit:** ${audit.retrieval_completeness}`);
  lines.push(`- **Kontext-Vollständigkeit:** ${audit.context_completeness}`);
  lines.push(`- **Antwort-Konfidenz:** ${audit.answer_confidence}`);
  lines.push("");

  if (audit.fallback_used.length > 0) {
    lines.push(`**Verwendete Fallbacks:** ${audit.fallback_used.join(", ")}`);
    lines.push("");
  }
  if (audit.warnings.length > 0) {
    lines.push("**Warnungen:**");
    for (const w of audit.warnings) lines.push(`- ${w}`);
    lines.push("");
  }

  return lines.join("\n");
}
