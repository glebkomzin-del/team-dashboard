// retrieval_planner.ts — Generates a full RetrievalPlan from a user query.
// Replaces query_router.ts. The plan is the single source of truth for
// what the retrieval layer will do — tables, filters, strategies, flags.

import { parseTimeRange, type TimeRange } from "./time_parser.ts";
import {
  resolvePersonsFromQuery,
  resolvePersonsFromQueryDynamic,
  type PersonEntry,
} from "./entity_resolver.ts";
import {
  STATUS_MAP,
  PRIORITY_MAP,
  ENTITY_SYNONYMS,
  STOPWORDS,
  parseNumber,
} from "./lexicon.ts";

// ── Types ─────────────────────────────────────────────────────────────────────

export type IntentClass =
  | "summarize_notes"      // Fasse Notizen/Meetings zusammen
  | "delta_report"         // Was ist passiert / was hat sich verändert
  | "management_update"    // Chef-Update / Management-Bericht
  | "decision_history"     // Welche Entscheidungen wurden getroffen (kein Personenbezug)
  | "open_items"           // Offene Todos/Blocker/Open Loops als Arbeitsliste
  | "status_check"         // Status eines Projekts/Themas (kein Personenname)
  | "person_status_query"  // Was ist bei Person X offen/erledigt
  | "person_meetings_query"// Welche Meetings hatte Person X / follow-up bei X
  | "project_query"        // Alles zu Projekt P (aus DB)
  | "topic_query"          // Alles zu Thema T (per Anchor-Suche)
  | "risk_analysis"        // Risiken, Blocker, Überfällige
  | "count_query"          // Wie viele X gibt es
  | "source_audit"         // Welche Daten hast du verwendet
  | "latest_entities"      // Letzte N Meetings/Todos/etc.
  | "time_range_query"     // Alles in Zeitraum X
  | "direct_lookup"        // Einzelner Datensatz per ID oder Titel
  | "semantic_search"      // Offene semantische Suche
  | "unknown";

export type ContextStrategy =
  | "meeting_summaries_with_audit"           // Meetings per SQL (time_range / latest), Summaries
  | "aggregate_changes_then_top_details"     // Activity log führend, dann Top-Details
  | "person_entity_full_structured"          // Alle Entity-Tabellen per SQL für eine Person
  | "person_meetings_structured"             // Meetings per Participant-ILIKE
  | "topic_filtered_results"                 // Topic-Anchor über alle Tabellen
  | "risk_signals_grouped"                   // High-prio todos + active blockers + overdue
  | "management_update_full"                 // Delta + Recent meetings + Risk signals
  | "counts_only"                            // SQL COUNT, kein Kontext
  | "from_last_audit"                        // Source-Audit: prev_audit zurückgeben
  | "recent_entities_compact"               // Neueste Entitäten, kompakt
  | "top_semantic_results";                  // Vector search only

export type ExpectedCompleteness =
  | "complete_structured"              // SQL liefert vollständige strukturierte Daten
  | "complete_with_semantic_supplement"// SQL + semantisch ergänzt
  | "partial_top_n"                    // Zu viele Ergebnisse, Top N gezeigt
  | "semantic_only"                    // Nur Vektorsuche, inhärent unvollständig
  | "audit_only"                       // Aus vorherigem Audit, keine neue Suche
  | "data_model_gap";                  // Bekannte Lücke im Datenmodell

export interface ResolvedProject {
  project_id: string;
  name: string;
  from_db: boolean; // true = came from projects table, false = hardcoded alias
}

export interface RetrievalFlags {
  include_decisions: boolean;
  include_commitments: boolean;
  include_open_loops: boolean;
  include_todos: boolean;
  include_blockers: boolean;
}

export interface RetrievalPlan {
  // ── Query ──────────────────────────────────────────────────────────────────
  original_query: string;
  normalized_query: string;

  // ── Intent & Strategy ──────────────────────────────────────────────────────
  intent: IntentClass;
  context_strategy: ContextStrategy;
  expected_completeness: ExpectedCompleteness;

  // ── Resolved Entities ──────────────────────────────────────────────────────
  people: PersonEntry[];
  projects: ResolvedProject[];
  topic_anchors: string[];
  statuses: string[];
  priorities: string[];
  time_range: TimeRange | null;

  // ── Tables ─────────────────────────────────────────────────────────────────
  primary_tables: string[];
  secondary_tables: string[];

  // ── Retrieval Flags ────────────────────────────────────────────────────────
  needs_activity_log: boolean;
  needs_relations: boolean;
  needs_source_audit: boolean;
  needs_semantic_search: boolean;
  needs_raw_evidence: boolean;
  retrieval_flags: RetrievalFlags;

  // ── Limits & Sort ──────────────────────────────────────────────────────────
  sort_field: string;
  sort_dir: "asc" | "desc";
  limit: number;
  meeting_count: number;

  // ── Semantic / Anchor ──────────────────────────────────────────────────────
  semantic_query: string;
  anchor_terms: string[];

  // ── Convenience Flags (for claude_client / context_builder) ────────────────
  isChefUpdate: boolean;
  isRiskQuestion: boolean;
  isCountQuery: boolean;
  isSourceAudit: boolean;
  isLatestMeeting: boolean;

  // ── Backward compat (used by existing context_builder / ranking) ───────────
  retrievalMode: string;
  persons: string[]; // canonical names, for code that still uses string[]
}

// ── Pattern banks ─────────────────────────────────────────────────────────────

const SUMMARIZE_NOTES = [
  /\bfass.{0,20}(notizen?|meetings?|besprechung(?:en)?|sitzung(?:en)?)\b/i,
  /\b(notizen?|meetings?|besprechung(?:en)?|sitzung(?:en)?)\s+(?:zusammenfass|fass|überblick)\b/i,
  /\bübersicht\s+(?:der\s+)?(?:letzten?\s+)?(?:notizen?|meetings?)\b/i,
  /\b(?:summarize|zusammenfass)\s+(?:the\s+)?(?:notes?|meetings?)\b/i,
  /\bnotizen?\s+(?:aus|von|der|letzte[rn]?)\b/i,
];

const DELTA = [
  /\bwas\s+(?:hat\s+sich|ist|wurde|kam)\b.{0,30}\b(?:geändert|passiert|verändert|gemacht|umgesetzt|abgeschlossen|erledigt|dazu|neu)\b/i,
  /\bwas\s+gibt'?s?\s+neues?\b/i,
  /\b(?:neuigkeiten|änderungen?|updates?|delta|changelog)\b/i,
  /\bwas\s+ist\s+(?:passiert|neu)\b/i,
  /\bwas\s+(?:kam|kommt)\s+(?:hinzu|dazu|neu)\b/i,
  /\bwas\s+wurde\s+(?:abgeschlossen|erledigt|umgesetzt|abgehakt)\b/i,
  /\b(?:what'?s?\s+new|what\s+happened|changes?)\b/i,
  /\bwas\s+hat\s+sich\s+(?:seit|in|diese[mr])\b/i,
  /\bseit\s+(?:letzter?|dieser?|den\s+letzten?)\s+\w+\s+(?:passiert|getan|gemacht|gesehen)\b/i,
];

const CHEF = [
  /\bchef[\s-]?update\b/i,
  /\bmanagement[\s-]?update\b/i,
  /\bstatus[\s-]?(?:bericht|report)\b/i,
  /\bwöchentliche[rn]?\s+(?:bericht|update|status|zusammenfassung)\b/i,
  /\b(?:weekly|wöchentlich)\b.{0,20}\b(?:update|brief|bericht)\b/i,
  /\b(?:briefing|update für)\b/i,
  /\bzusammenfassung für\b/i,
];

const RISK = [
  /\b(?:risik\w*|risks?|gefahr\w*|gefährd\w*|kritisch|critical)\b/i,
  /\b(?:überfällig|overdue|verspätet)\b/i,
  /\b(?:blocker|blockier|blocked)\b/i,
  /\b(?:eskalat|warnung|warning|alarm)\b/i,
  /\bwas\s+ist\s+(?:kritisch|riskant|problematisch)\b/i,
  /\bprobleme?\b.{0,40}\bgefährd\w*\b/i,
  /\bwas\s+(?:könnte|kann)\s+(?:schief(?:gehen|laufen)|scheitern)\b/i,
  /\bwas\s+(?:gefährdet|bedroht)\b/i,
];

// Arbeitsliste-Muster: Todos/offene Punkte (KEIN Blocker — Blocker gehört zu risk_analysis)
const OPEN_ITEMS = [
  /\bwelche\s+(?:todos?|aufgaben|punkte|themen|fragen)\s+(?:sind\s+)?(?:noch\s+)?offen\b/i,
  /\boffene[nr]?\s+(?:todos?|aufgaben|punkte|themen|fragen)\b/i,
  /\bwas\s+ist\s+(?:noch\s+)?(?:offen|ungeklärt)\b/i,
  /\bwas\s+sind\s+(?:die\s+)?(?:wichtigsten\s+)?offene[nr]?\s+punkte\b/i,
  /\b(?:open[\s-]?items?|ungeklärte\s+punkte)\b/i,
  /\bwas\s+(?:steht\s+noch\s+aus|fehlt\s+noch)\b/i,
  /\bwelche\s+todos?\s+(?:gibt\s+es|sind)\b/i,
  /\bwas\s+muss\s+noch\s+(?:erledigt|getan|gemacht)\s+werden\b/i,
];

// Entscheidungs-Muster: Beschlüsse/Entscheidungen ohne Personenbezug
const DECISION_HISTORY = [
  /\bwelche\s+entscheidungen?\s+(?:wurden|sind|hat\s+es\s+gegeben)\b/i,
  /\bwas\s+wurde\s+(?:.*?\s+)?entschieden\b/i,
  /\b(?:welche|was)\s+(?:beschlüsse?|beschlossen)\b/i,
  /\bentscheidungen?\s+(?:getroffen|gefällt|gemacht)\b/i,
  /\bwas\s+(?:wurde|ist)\s+(?:.*?\s+)?(?:festgelegt|vereinbart|beschlossen)\b/i,
  /\bwelche\s+beschlüsse?\s+(?:gab|gibt)\s+es\b/i,
  /\b(?:decision[\s-]?history|entscheidungshistorie)\b/i,
];

// Status-Muster: Projektstatus ohne Personennamen
const STATUS_CHECK = [
  /\b(?:status|stand)\s+(?:der|des|von|beim?)\s+\w/i,
  /\baktuell(?:er|en|em)?\s+stand\b/i,
  /\bwo\s+steh(?:en\s+wir|t\s+(?:das|die|der))\s+(?:bei|mit|beim?)\b/i,
  /\bwie\s+(?:läuft|steht|ist)\s+(?:es\s+(?:mit|bei|um)|der|die|das)\b/i,
  /\bwie\s+(?:ist|war)\s+der\s+(?:aktuelle\s+)?(?:status|stand|fortschritt)\b/i,
  /\bfortschritt\s+(?:bei|von|der|des)\b/i,
];

const LATEST_MEETING = [
  /\b(?:letzte[ns]?|neueste[ns]?|aktuellste[ns]?|recent|last|latest)\s+\w*\s*meetings?\b/i,
  /\b(?:letzte[ns]?|neueste[ns]?)\s+(?:besprechung|sitzung)\b/i,
  /\bletzte[ns]?\s+(?:zwei|drei|vier|fünf|\d+)\s+meetings?\b/i,
];

const PERSON_MEETING = [
  /\bwelche\s+meetings?\s+(?:hatte[ns]?|hat[te]*|war[en]?\s+in)\s+\w+/i,
  /\bmeeting[s\b].{0,20}\b(?:mit|bei|von|für)\s+\w+/i,
  /\bwelche?\s+meetings?\s+(?:zu|für|mit|von|bei)\s+\w+\b/i,
  /\bfollow[\s-]?up\b.{0,30}\b(?:bei|mit|von)\b/i,
  /\b(?:bei|mit|von)\b.{0,30}\bfollow[\s-]?up\b/i,
  /\bletzten?\s+\w*\s*meetings?\s+(?:zu|für|mit|bei|von)\b/i,
  /\bwelche\s+notizen?\s+(?:gibt|haben)\s+(?:es\s+)?(?:zu\s+)?\w+\b/i,
];

const SOURCE_AUDIT = [
  /welche\s+\w+\s+hast\s+du\s+(?:dir\s+)?(?:verwendet|angeschaut|angesehen|abgerufen|genutzt|abgefragt)/i,
  /was\s+hast\s+du\s+(?:dir\s+)?(?:angeschaut|angesehen|abgerufen|verwendet)/i,
  /woher\s+(?:weißt|kennst|hast)\s+du/i,
  /woher\s+kommen\s+(?:diese|die)\s+daten/i,
  /welche\s+quellen?\s+hast\s+du/i,
  /aus\s+welche[nm]\s+quellen/i,
  /wie\s+bist\s+du\s+zu\s+dieser\s+antwort/i,
  /was\s+sind\s+deine\s+quellen/i,
  /zeig\s+(?:mir\s+)?den\s+audit/i,
  /retrieval[\s-]?audit/i,
  /welche\s+datenbanktabellen/i,
  /worauf\s+(?:basiert|stützt)\s+du/i,
  /auf\s+welchen\s+daten\s+basier/i,
  /ist\s+das\s+vollständig/i,
  /welche\s+(?:treffer|datensätze?|einträge?)\s+wurden\s+(?:nur\s+)?aggregiert/i,
];

const COUNT = [
  /wie\s+viele?\s+(?:todos?|aufgaben?|meetings?|blocker|open[\s-]?items?|offene\s+(?:punkte|aufgaben?)|entscheidungen?|projekte?|beschlüsse?|einträge?)/i,
  /wieviele?\s+(?:todos?|aufgaben?|meetings?|blocker|projekte?)/i,
  /anzahl\s+(?:der\s+|aller\s+|von\s+)?(?:todos?|aufgaben?|meetings?|blocker|projekte?)/i,
  /how\s+many\s+(?:todos?|meetings?|blockers?|decisions?|projects?)/i,
  /\b(?:gesamtanzahl|gesamtzahl|total count)\b/i,
];

function hit(q: string, patterns: RegExp[]): boolean {
  return patterns.some((p) => p.test(q));
}

// ── Extraction helpers ─────────────────────────────────────────────────────────

function extractStatuses(q: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const key of Object.keys(STATUS_MAP).sort((a, b) => b.length - a.length)) {
    const re = new RegExp(`\\b${key.replace(/\s+/g, "\\s+")}\\b`, "i");
    if (re.test(q)) {
      const v = STATUS_MAP[key];
      if (!seen.has(v)) { seen.add(v); out.push(v); }
    }
  }
  return out;
}

function extractPriorities(q: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const key of Object.keys(PRIORITY_MAP).sort((a, b) => b.length - a.length)) {
    if (new RegExp(`\\b${key}\\b`, "i").test(q)) {
      const v = PRIORITY_MAP[key];
      if (!seen.has(v)) { seen.add(v); out.push(v); }
    }
  }
  return out;
}

function extractEntityHints(q: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const key of Object.keys(ENTITY_SYNONYMS).sort((a, b) => b.length - a.length)) {
    const re = new RegExp(`\\b${key.replace(/\s+/g, "\\s+")}\\b`, "i");
    if (re.test(q)) {
      for (const t of ENTITY_SYNONYMS[key]) {
        if (!seen.has(t)) { seen.add(t); out.push(t); }
      }
    }
  }
  return out;
}

function extractTopicAnchors(
  original: string,
  people: PersonEntry[],
): string[] {
  const personTerms = new Set(people.flatMap((p) => [
    ...p.aliases,
    p.display_name.toLowerCase(),
    p.canonical_name.toLowerCase(),
  ]));
  const words = original.split(/[\s,;.!?()[\]{}]+/);
  const anchors: string[] = [];
  for (let i = 0; i < words.length; i++) {
    const raw = words[i].replace(/[^\wäöüÄÖÜß-]/g, "");
    if (raw.length < 3) continue;
    const lower = raw.toLowerCase();
    if (STOPWORDS.has(lower) || personTerms.has(lower)) continue;
    const isCapitalized = /^[A-ZÜÖÄ]/.test(raw) && i > 0;
    const isAllCaps = /^[A-Z]{2,}$/.test(raw);
    const isCamelCase = /^[a-z]+[A-Z]/.test(raw);
    const isNumber = /^\d{4}$/.test(raw); // year-like numbers
    if (isCapitalized || isAllCaps || isCamelCase || isNumber) {
      anchors.push(raw);
    }
  }
  return [...new Set(anchors)];
}

function extractMeetingCount(q: string): number {
  const m = q.match(/\bletzten?\s+(\w+|\d+)\s+meetings?\b/i)
    ?? q.match(/\b(\w+|\d+)\s+(?:letzten?\s+)?meetings?\b/i);
  if (m) { const n = parseNumber(m[1]); if (n && n > 0 && n < 50) return n; }
  return 1;
}

function buildSemanticQuery(q: string): string {
  return q.split(/\s+/)
    .filter((w) => !STOPWORDS.has(w.toLowerCase()) && w.length > 1)
    .join(" ");
}

function tableSets(
  intent: IntentClass,
  entityHints: string[],
  hasPeople: boolean,
  hasTime: boolean,
): { primary: string[]; secondary: string[] } {
  switch (intent) {
    case "summarize_notes":
      return { primary: ["meetings"], secondary: ["decisions"] };
    case "delta_report":
    case "management_update":
      return {
        primary: ["activity_log", "meetings"],
        secondary: ["todos", "open_items", "blockers", "decisions"],
      };
    case "decision_history":
      return { primary: ["decisions"], secondary: ["meetings"] };
    case "open_items":
      return { primary: ["todos", "open_items", "blockers"], secondary: [] };
    case "status_check":
      return {
        primary: ["meetings", "todos", "open_items"],
        secondary: ["blockers", "decisions"],
      };
    case "person_status_query":
      return {
        primary: ["todos", "open_items", "blockers"],
        secondary: hasPeople ? ["meetings"] : [],
      };
    case "person_meetings_query":
      return { primary: ["meetings"], secondary: ["todos", "open_items", "blockers"] };
    case "project_query":
    case "topic_query":
      return {
        primary: ["meetings", "todos", "open_items", "blockers", "decisions"],
        secondary: ["activity_log"],
      };
    case "risk_analysis":
      return { primary: ["todos", "blockers", "open_items"], secondary: ["meetings"] };
    case "count_query":
      return {
        primary: entityHints.length > 0
          ? entityHints
          : ["todos", "meetings", "blockers", "open_items", "decisions"],
        secondary: [],
      };
    case "latest_entities":
      return {
        primary: entityHints.length > 0 ? entityHints : ["meetings"],
        secondary: [],
      };
    case "time_range_query":
      return {
        primary: ["meetings", "todos", "open_items", "blockers"],
        secondary: ["activity_log", "decisions"],
      };
    default:
      return {
        primary: entityHints.length > 0
          ? entityHints
          : ["meetings", "todos", "open_items", "blockers"],
        secondary: ["decisions"],
      };
  }
}

// ── Transcript evidence gate ──────────────────────────────────────────────────

const QUALITATIVE_SIGNALS = [
  /was\s+hat/i, /was\s+wurde/i, /wer\s+hat\s+gesagt/i, /wie\s+hat/i,
  /\bwarum\b/i, /\bbegründung\b/i, /\breaktion\b/i, /\bton\b/i,
  /\batmosphäre\b/i, /\bstimmung\b/i, /\boriginalton\b/i, /\bzitat\b/i,
  /hat\s+erwähnt/i, /hat\s+angesprochen/i, /\beinschätzung\b/i,
  /\bmeinung\b/i, /what\s+did/i, /\bwhy\b/i, /how\s+did/i,
  /\bmentioned\b/i, /\bsaid\b/i, /\bdiscussed\b/i,
];

// Returns false only for pure count/meta/list queries with no qualitative signal.
// Default is true — in doubt always fetch transcript evidence.
function determineNeedsRawEvidence(query: string, intent: IntentClass): boolean {
  const noEvidenceIntents: IntentClass[] = [
    "count_query", "source_audit", "risk_analysis", "decision_history", "open_items",
  ];
  const hasQualitativeSignal = QUALITATIVE_SIGNALS.some((p) => p.test(query));
  if (noEvidenceIntents.includes(intent) && !hasQualitativeSignal) return false;
  return true;
}

// ── Main planner ──────────────────────────────────────────────────────────────

export function planRetrieval(query: string, now: Date): RetrievalPlan {
  const q = query.toLowerCase().trim();

  const people = resolvePersonsFromQuery(q);
  const statuses = extractStatuses(q);
  const priorities = extractPriorities(q);
  const entityHints = extractEntityHints(q);
  const timeRange = parseTimeRange(q, now);
  const meetingCount = extractMeetingCount(q);
  const semanticQuery = buildSemanticQuery(q);
  const topicAnchors = extractTopicAnchors(query, people);

  const isSummarize = hit(q, SUMMARIZE_NOTES);
  const isDelta = hit(q, DELTA);
  const isChef = hit(q, CHEF);
  const isRisk = hit(q, RISK);
  const isOpenItems = hit(q, OPEN_ITEMS);
  // decision_history and status_check only fire without a person in the query
  const isDecisionHistory = hit(q, DECISION_HISTORY) && people.length === 0;
  const isStatusCheck = hit(q, STATUS_CHECK) && people.length === 0;
  // risk_analysis = risk signals, but NOT if it's just an open-items list query
  const isRiskAnalysis = isRisk && !isOpenItems;
  const isLatest = hit(q, LATEST_MEETING);
  const isSourceAudit = hit(query, SOURCE_AUDIT);
  const isCount = hit(query, COUNT);

  // Is this specifically a meeting query for a person?
  const isPersonMeeting = people.length > 0 && (
    hit(q, PERSON_MEETING) ||
    /\bmeeting[s]?\b/i.test(q) ||
    /\bnotizen?\b/i.test(q) ||
    /\bbesprechung\b/i.test(q)
  );
  const isPersonStatus = people.length > 0 && !isPersonMeeting;

  // ── Intent determination (priority cascade — order matters!) ─────────────
  // 1. count_query / source_audit — short-circuit in index.ts, must come first
  // 2. management_update / delta_report — temporal/aggregation
  // 3. decision_history / open_items — structural content types
  // 4. risk_analysis — threat-framed queries
  // 5. status_check — project-status without person
  // 6. person_* — person-specific queries
  // 7. topic/semantic fallbacks
  let intent: IntentClass;
  let contextStrategy: ContextStrategy;
  let expectedCompleteness: ExpectedCompleteness;
  let needsActivityLog = false;
  let needsSemantic = false;

  if (isSourceAudit) {
    intent = "source_audit";
    contextStrategy = "from_last_audit";
    expectedCompleteness = "audit_only";
  } else if (isCount) {
    intent = "count_query";
    contextStrategy = "counts_only";
    expectedCompleteness = "complete_structured";
  } else if (isChef) {
    intent = "management_update";
    contextStrategy = "management_update_full";
    expectedCompleteness = "complete_with_semantic_supplement";
    needsActivityLog = true;
  } else if (isDelta) {
    intent = "delta_report";
    contextStrategy = "aggregate_changes_then_top_details";
    expectedCompleteness = timeRange ? "complete_structured" : "partial_top_n";
    needsActivityLog = true;
  } else if (isDecisionHistory) {
    intent = "decision_history";
    contextStrategy = "topic_filtered_results";
    expectedCompleteness = "complete_structured";
  } else if (isOpenItems) {
    intent = "open_items";
    contextStrategy = "person_entity_full_structured";
    expectedCompleteness = "complete_structured";
  } else if (isRiskAnalysis) {
    intent = "risk_analysis";
    contextStrategy = "risk_signals_grouped";
    expectedCompleteness = "complete_structured";
  } else if (isStatusCheck) {
    intent = "status_check";
    contextStrategy = "topic_filtered_results";
    expectedCompleteness = "complete_with_semantic_supplement";
    needsSemantic = true;
  } else if (isSummarize) {
    intent = "summarize_notes";
    contextStrategy = "meeting_summaries_with_audit";
    expectedCompleteness = "complete_structured";
  } else if (isLatest) {
    intent = "latest_entities";
    contextStrategy = "recent_entities_compact";
    expectedCompleteness = "complete_structured";
  } else if (isPersonMeeting) {
    intent = "person_meetings_query";
    contextStrategy = "person_meetings_structured";
    expectedCompleteness = "complete_structured";
  } else if (isPersonStatus) {
    intent = "person_status_query";
    contextStrategy = "person_entity_full_structured";
    expectedCompleteness = "complete_structured";
  } else if (timeRange) {
    intent = "time_range_query";
    contextStrategy = "meeting_summaries_with_audit";
    expectedCompleteness = "complete_structured";
  } else if (topicAnchors.length > 0) {
    intent = "topic_query";
    contextStrategy = "topic_filtered_results";
    expectedCompleteness = "complete_with_semantic_supplement";
    needsSemantic = true;
  } else if (entityHints.length > 0) {
    intent = "latest_entities";
    contextStrategy = "recent_entities_compact";
    expectedCompleteness = "partial_top_n";
    needsSemantic = true;
  } else if (semanticQuery.length > 3) {
    intent = "semantic_search";
    contextStrategy = "top_semantic_results";
    expectedCompleteness = "semantic_only";
    needsSemantic = true;
  } else {
    intent = "unknown";
    contextStrategy = "top_semantic_results";
    expectedCompleteness = "semantic_only";
    needsSemantic = true;
  }

  const { primary, secondary } = tableSets(intent, entityHints, people.length > 0, !!timeRange);

  // Sort default
  const sortField = ["summarize_notes", "latest_entities", "person_meetings_query"]
    .includes(intent) ? "meeting_date" : "created_at";

  return {
    original_query: query,
    normalized_query: semanticQuery,
    intent,
    context_strategy: contextStrategy,
    expected_completeness: expectedCompleteness,
    people,
    projects: [], // populated at runtime by checking the DB projects table
    topic_anchors: topicAnchors,
    statuses,
    priorities,
    time_range: timeRange,
    primary_tables: primary,
    secondary_tables: secondary,
    needs_activity_log: needsActivityLog,
    needs_relations: false,
    needs_source_audit: isSourceAudit,
    needs_semantic_search: needsSemantic,
    needs_raw_evidence: determineNeedsRawEvidence(query, intent),
    sort_field: sortField,
    sort_dir: "desc",
    limit: isCount ? 0 : 50,
    meeting_count: meetingCount,
    semantic_query: semanticQuery,
    anchor_terms: topicAnchors,
    isChefUpdate: isChef,
    isRiskQuestion: isRiskAnalysis,
    isCountQuery: isCount,
    isSourceAudit,
    isLatestMeeting: isLatest,
    // Backward compat
    retrievalMode: needsSemantic ? "semantic_hybrid"
      : isCount ? "count_only"
      : isSourceAudit ? "source_intent"
      : needsActivityLog ? "delta_report"
      : "sql_direct",
    persons: people.map((p) => p.canonical_name),
    retrieval_flags: {
      include_decisions: [
        "delta_report", "management_update", "summarize_notes",
        "latest_entities", "decision_history",
      ].includes(intent),
      include_commitments: intent === "person_status_query" || intent === "person_meetings_query",
      include_open_loops: isRiskAnalysis || intent === "open_items",
      include_todos: ["person_status_query", "risk_analysis", "open_items"].includes(intent),
      include_blockers: isRiskAnalysis || intent === "open_items",
    },
  };
}

// ── Haiku Query Planner ───────────────────────────────────────────────────────

const PLANNER_SYSTEM_PROMPT = `Du bist ein Query Planner für ein deutsches Job-Dashboard.
Das Dashboard enthält: Meeting-Transkripte, Todos, Blocker, Open Items,
Decisions, Commitments, Open Loops, Team-Member-Profile.
Analysiere die Anfrage und antworte NUR mit validem JSON, kein Markdown:
{
  "intent": "<intent_class>",
  "answer_mode": "<mode>",
  "needs_raw_evidence": <bool>,
  "exact_terms": ["<term>"],
  "entities": {
    "persons": ["<name>"],
    "projects": ["<name>"],
    "topics": ["<topic>"]
  },
  "semantic_queries": ["<query>"],
  "retrieval_flags": {
    "include_decisions": <bool>,
    "include_commitments": <bool>,
    "include_open_loops": <bool>,
    "include_todos": <bool>,
    "include_blockers": <bool>
  },
  "time_filter": {
    "direction": "recent|past|specific|none",
    "reference": "<z.B. letzte Woche>|null"
  }
}

INTENT-KLASSIFIKATION – prüfe in dieser festen Reihenfolge:

1. count_query
   Wann: Query enthält Zählwörter ("wie viele", "wie oft", "Anzahl", "zähle").
   Beispiele: "Wie viele Todos gibt es?", "Wie viele Meetings hatten wir?"
   needs_raw_evidence: false

2. delta_report
   Wann: Query fragt nach Veränderungen in einem Zeitraum.
   Trigger: "seit [Zeitangabe]", "letzte X Tage/Wochen", "was ist neu",
   "was hat sich geändert", "was ist passiert seit".
   Beispiele: "Was ist seit letzter Woche passiert?",
   "Was gab es Neues diese Woche?"
   needs_raw_evidence: true

3. decision_history
   Wann: Query fragt nach getroffenen Entscheidungen, UNABHÄNGIG von Personen.
   Trigger: "entschieden", "beschlossen", "Entscheidung", "wurde festgelegt",
   "haben wir vereinbart", "ist entschieden".
   KEIN Personenname in der Query nötig.
   Beispiele: "Welche Entscheidungen wurden getroffen?",
   "Was wurde zum Budget entschieden?",
   "Welche Beschlüsse gab es letzten Monat?"
   needs_raw_evidence: false
   retrieval_flags: include_decisions: true

4. open_items
   Wann: Query fragt nach offenen Aufgaben, Todos, ungeklärten Punkten als Arbeitsliste.
   Fokus: Was muss noch erledigt werden? (Aufgabenliste, keine Bedrohungsanalyse)
   Trigger: "offen", "Todo", "ausstehend", "was steht aus",
   "noch nicht erledigt", "was fehlt noch".
   KEIN Blocker-Trigger — Blocker gehoert zu risk_analysis!
   Abgrenzung:
   "Welche Todos sind offen?" -> open_items (Aufgabenliste)
   "Was sind die aktuellen Blocker?" -> risk_analysis (Blocker = Risiko-Signal)
   "Was gefaehrdet das Projekt?" -> risk_analysis
   Beispiele: "Welche Todos sind noch offen?",
   "Was ist noch ungeklaert?",
   "Was steht noch aus?",
   "Was sind die wichtigsten offenen Punkte?"
   needs_raw_evidence: false
   retrieval_flags: include_todos: true, include_open_loops: true

5. risk_analysis
   Wann: Query fragt nach Risiken, Gefahren, Bedrohungen oder Blockern.
   Fokus: Was koennte scheitern oder gefaehrdet sein?
   Trigger: "Risiko", "Gefahr", "gefaehrdet", "Blocker", "aktuellen Blocker",
   "was koennte schiefgehen", "was bedroht", "kritisch", "ueberfaellig".
   Abgrenzung zu open_items: Blocker und Risiken -> IMMER risk_analysis.
   Beispiele: "Was sind die Risiken bei der SAP-Migration?",
   "Was sind die aktuellen Blocker?",
   "Was koennte beim Forecasting schiefgehen?",
   "Welche Blocker gibt es?"
   needs_raw_evidence: true

6. status_check
   Wann: Query fragt nach dem Status eines PROJEKTS oder THEMAS.
   KEIN Personenname in der Query.
   Trigger: "Status", "Stand", "wie läuft", "aktueller Stand",
   "wo stehen wir bei", "Fortschritt".
   Abgrenzung zu person_status_query: Kein Name -> status_check.
   Beispiele: "Was ist der Status der SAP-Migration?",
   "Wie ist der Stand beim Forecasting?",
   "Wo stehen wir bei der Harmonisierung?"
   needs_raw_evidence: true

7. person_status_query
   Wann: NUR wenn ein KONKRETER PERSONENNAME genannt wird UND nach
   ihren Aktivitäten, Zusagen oder Entscheidungen gefragt wird.
   Ohne Personenname -> NICHT dieser Intent.
   Beispiele: "Was hat Bernadette entschieden?",
   "Welche Zusagen hat Lang gemacht?",
   "Was hat Caroline zur Nachfolge gesagt?"
   needs_raw_evidence: true
   retrieval_flags: include_commitments: true, include_decisions: true

8. person_meetings_query
   Wann: Explizit nach Meetings einer Person gefragt.
   Beispiele: "Welche Meetings hatte Bernadette diese Woche?",
   "Wann hat Darius zuletzt teilgenommen?"

9. person_profile
   Wann: NUR wenn ein KONKRETER NAME der Person bekannt ist und nach ihrer
   Rolle oder ihrem Hintergrund gefragt wird.
   WICHTIG: "Wer ist fuer X verantwortlich?" OHNE konkreten Namen -> topic_query!
   Beispiele (person_profile): "Wer ist Caroline Witschorke?",
   "Was macht Jan Lang bei TEDi?"
   Beispiele (NICHT person_profile, sondern topic_query):
   "Wer ist fuer die SAP-Migration verantwortlich?" -> topic_query
   "Wer ist zustaendig fuer X?" -> topic_query

10. meeting_summary
    Wann: Nach Zusammenfassung eines bestimmten Meetings gefragt.
    Trigger: spezifischer Meeting-Name oder Datum + "Zusammenfassung",
    "was wurde besprochen", "was war das Ergebnis".

11. meeting_list
    Wann: Nach einer Liste von Meetings gefragt.
    Trigger: "welche Meetings", "zeig mir Meetings zu", "wann war das Meeting".

12. latest_entities
    Wann: Nach den neuesten oder wichtigsten Eintraegen eines Typs gefragt.
    Trigger: "neueste", "letzte", "zuletzt hinzugefuegt", "aktuellste",
    "wichtigsten X aus dem letzten Monat/Jahr", "Top-X".
    Abgrenzung zu decision_history:
    "Welche Entscheidungen wurden getroffen?" -> decision_history (Historizitaet)
    "Was sind die wichtigsten Entscheidungen aus dem letzten Monat?" -> latest_entities (Top-N)
    Beispiele: "Zeig mir die letzten Decisions",
    "Was sind die wichtigsten Entscheidungen aus dem letzten Monat?",
    "Was wurde zuletzt eingetragen?"

13. topic_query
    Wann: Frage zu einem Thema oder Projekt ohne klaren strukturierten Intent.
    Fallback wenn keiner der oberen Intents passt aber ein Thema erkennbar ist.
    Beispiele: "Was wurde über GCP besprochen?",
    "Erzähl mir mehr über die Harmonisierung."

14. general_question
    Wann: Keine der oberen Kategorien passt. Letzter Fallback.

KLASSIFIKATIONS-BEISPIELE:
"Welche Todos sind noch offen?"
-> intent: open_items, needs_raw_evidence: false,
  retrieval_flags: {include_todos: true, include_open_loops: true}
"Was sind die wichtigsten offenen Punkte?"
-> intent: open_items, needs_raw_evidence: false,
  retrieval_flags: {include_todos: true, include_open_loops: true}
"Was ist noch ungeklaert beim Thema Reporting?"
-> intent: open_items, needs_raw_evidence: false,
  retrieval_flags: {include_todos: true, include_open_loops: true}
"Was sind die aktuellen Blocker?"
-> intent: risk_analysis, needs_raw_evidence: true
"Welche Blocker gibt es?"
-> intent: risk_analysis, needs_raw_evidence: true
"Was gefaehrdet die SAP-Migration?"
-> intent: risk_analysis, needs_raw_evidence: true,
  exact_terms: ["SAP"]
"Wer ist fuer die SAP-Migration verantwortlich?"
-> intent: topic_query, needs_raw_evidence: true,
  exact_terms: ["SAP"]
"Was hat Bernadette letzte Woche entschieden?"
-> intent: person_status_query, needs_raw_evidence: true,
  entities: {persons: ["Bernadette"]}
"Was ist der Status der SAP-Migration?"
-> intent: status_check, needs_raw_evidence: true,
  exact_terms: ["SAP"]
"Was wurde zum Budget entschieden?"
-> intent: decision_history, needs_raw_evidence: false,
  exact_terms: ["Budget"],
  retrieval_flags: {include_decisions: true}
"Welche Entscheidungen wurden getroffen?"
-> intent: decision_history, needs_raw_evidence: false,
  retrieval_flags: {include_decisions: true}
"Was sind die wichtigsten Entscheidungen aus dem letzten Monat?"
-> intent: latest_entities, needs_raw_evidence: false,
  time_filter: {direction: "recent", reference: "letzter Monat"},
  retrieval_flags: {include_decisions: true}
"Was ist seit letzter Woche passiert?"
-> intent: delta_report, needs_raw_evidence: true,
  time_filter: {direction: "recent", reference: "letzte Woche"}
"Wie viele Meetings hatten wir diesen Monat?"
-> intent: count_query, needs_raw_evidence: false
"Welche Entscheidungen wurden letzten Monat getroffen?"
-> intent: decision_history, needs_raw_evidence: false,
  time_filter: {direction: "recent", reference: "letzter Monat"},
  retrieval_flags: {include_decisions: true}
"Was sind die wichtigsten Themen im letzten Monat?"
-> intent: topic_query, needs_raw_evidence: true,
  time_filter: {direction: "recent", reference: "letzter Monat"}

answer_mode: sql_primary | vector_primary | hybrid | transcript
needs_raw_evidence=true bei qualitativen Fragen, Personenfragen, Status-Fragen.
needs_raw_evidence=false bei count/list/decision-list/open-items-list.
semantic_queries: 1-3 Suchvarianten. Immer mindestens eine.
exact_terms: Eigennamen, Akronyme, spezifische Begriffe für Keyword-Suche.`;

// Maps Haiku intent names to IntentClass values used downstream.
// "source_audit" and "count_query" are protected: regex detection is more reliable
// for these since they trigger short-circuit code paths in index.ts.
const HAIKU_INTENT_MAP: Record<string, IntentClass> = {
  "person_profile": "person_status_query",
  "person_status_query": "person_status_query",
  "person_meetings_query": "person_meetings_query",
  "decision_history": "decision_history",   // Sprint 9 fix: was "topic_query"
  "open_items": "open_items",               // Sprint 9 fix: was "person_status_query"
  "topic_query": "topic_query",
  "latest_entities": "latest_entities",
  "meeting_summary": "summarize_notes",
  "meeting_list": "latest_entities",
  "count_query": "count_query",
  "status_check": "status_check",           // Sprint 9 fix: was "person_status_query"
  "risk_analysis": "risk_analysis",
  "delta_report": "delta_report",           // Sprint 9 fix: was missing
  "search_by_keyword": "semantic_search",
  "general_question": "semantic_search",
};

// Derive retrievalMode and convenience flags from the merged intent.
function deriveModeAndFlags(
  intent: IntentClass,
  basePlan: RetrievalPlan,
): Pick<RetrievalPlan, "retrievalMode" | "isChefUpdate" | "isRiskQuestion" | "isCountQuery" | "isLatestMeeting"> {
  const needsSemantic = ["topic_query", "semantic_search", "status_check"].includes(intent);
  const isActivityLogIntent = intent === "delta_report" || intent === "management_update" || basePlan.needs_activity_log;
  return {
    retrievalMode: needsSemantic ? "semantic_hybrid"
      : intent === "count_query" ? "count_only"
      : isActivityLogIntent ? "delta_report"
      : "sql_direct",
    isChefUpdate: basePlan.isChefUpdate,
    isRiskQuestion: intent === "risk_analysis",
    isCountQuery: intent === "count_query",
    isLatestMeeting: intent === "latest_entities" && basePlan.isLatestMeeting,
  };
}

/**
 * LLM-based query planner using claude-haiku-4-5-20251001.
 * Calls planRetrieval() as baseline for entity resolution + time parsing,
 * then overrides the semantic fields with Haiku's understanding.
 * Falls back to planRetrieval() on any Haiku error.
 *
 * @param supabase  Supabase client — used for dynamic person lexicon loading (cached 5 min).
 */
export async function planWithHaiku(
  query: string,
  // deno-lint-ignore no-explicit-any
  conversationHistory: any[] = [],
  now: Date = new Date(),
  // deno-lint-ignore no-explicit-any
  supabase?: any,
): Promise<RetrievalPlan> {
  // Always compute the baseline — it handles entity resolution (PersonEntry[]),
  // time parsing, status extraction, table sets, etc.
  const basePlan = planRetrieval(query, now);

  // Short-circuit intents must not be overridden — they trigger code paths
  // in index.ts that don't go through the main retrieval switch.
  if (basePlan.intent === "source_audit") return basePlan;

  const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY");
  if (!ANTHROPIC_API_KEY) {
    console.warn("[semantic-search] No ANTHROPIC_API_KEY, using regex planner");
    return basePlan;
  }

  const historyContext = conversationHistory
    .slice(-2)
    .map((m) => `${m.role}: ${String(m.content ?? m.text ?? "").slice(0, 150)}`)
    .join("\n");

  const userMessage = historyContext
    ? `Konversations-Kontext:\n${historyContext}\n\nAktuelle Anfrage: ${query}`
    : query;

  try {
    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 600,
        system: PLANNER_SYSTEM_PROMPT,
        messages: [{ role: "user", content: userMessage }],
      }),
    });

    if (!response.ok) {
      console.error(`[semantic-search] Haiku API error ${response.status}`);
      return basePlan;
    }

    const data = await response.json();
    const rawText = data.content?.[0]?.text ?? "{}";
    // deno-lint-ignore no-explicit-any
    const parsed: Record<string, any> = JSON.parse(rawText.replace(/```json|```/g, "").trim());

    // Map Haiku intent → IntentClass, keep base for unknowns
    const mappedIntent: IntentClass =
      HAIKU_INTENT_MAP[parsed.intent as string] ?? basePlan.intent;

    // Merge exact_terms + existing topic_anchors (deduplicated)
    const haikuTerms: string[] = Array.isArray(parsed.exact_terms) ? parsed.exact_terms : [];
    const haikuTopics: string[] = Array.isArray(parsed.entities?.topics) ? parsed.entities.topics : [];
    const mergedAnchors = [...new Set([...basePlan.topic_anchors, ...haikuTerms, ...haikuTopics])];

    // Haiku's first semantic_query is usually better than the regex-stripped version
    const haikuSemanticQueries: string[] = Array.isArray(parsed.semantic_queries) && parsed.semantic_queries.length > 0
      ? parsed.semantic_queries
      : [query];
    const primarySemanticQuery = haikuSemanticQueries[0];

    // Haiku retrieval flags — merge with base (OR logic so base keeps any truthy flags)
    const haikuFlags = parsed.retrieval_flags ?? {};
    const mergedFlags: RetrievalFlags = {
      include_decisions: !!(haikuFlags.include_decisions || basePlan.retrieval_flags.include_decisions),
      include_commitments: !!(haikuFlags.include_commitments || basePlan.retrieval_flags.include_commitments),
      include_open_loops: !!(haikuFlags.include_open_loops || basePlan.retrieval_flags.include_open_loops),
      include_todos: !!(haikuFlags.include_todos || basePlan.retrieval_flags.include_todos),
      include_blockers: !!(haikuFlags.include_blockers || basePlan.retrieval_flags.include_blockers),
    };

    // Dynamic person resolution: enrich basePlan.people with DB-loaded names.
    // Haiku's entities.persons feeds the resolver so it can build PersonEntry for
    // names not in the static PERSON_LEXICON (e.g. new meeting participants).
    const haikuPersonNames: string[] = Array.isArray(parsed.entities?.persons)
      ? parsed.entities.persons
      : [];
    const enrichedPeople = supabase
      ? await resolvePersonsFromQueryDynamic(query, supabase, haikuPersonNames)
      : basePlan.people;

    const modeAndFlags = deriveModeAndFlags(mappedIntent, basePlan);
    const { primary, secondary } = tableSets(
      mappedIntent,
      extractEntityHints(query),
      enrichedPeople.length > 0,
      !!basePlan.time_range,
    );

    return {
      ...basePlan,
      intent: mappedIntent,
      people: enrichedPeople,
      persons: enrichedPeople.map((p) => p.canonical_name),
      topic_anchors: mergedAnchors,
      anchor_terms: mergedAnchors,
      semantic_query: primarySemanticQuery,
      needs_raw_evidence: typeof parsed.needs_raw_evidence === "boolean"
        ? parsed.needs_raw_evidence
        : basePlan.needs_raw_evidence,
      retrieval_flags: mergedFlags,
      primary_tables: primary,
      secondary_tables: secondary,
      ...modeAndFlags,
    };
  } catch (e) {
    console.error("[semantic-search] Haiku planner failed, using regex fallback:", String(e).slice(0, 200));
    return basePlan;
  }
}
