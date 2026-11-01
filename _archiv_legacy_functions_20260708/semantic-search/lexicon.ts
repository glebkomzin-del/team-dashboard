// lexicon.ts — Lookup maps for people, projects, statuses, priorities, entity synonyms, etc.

/** Canonical person name lookup. All keys are lowercase. */
export const PEOPLE_MAP: Record<string, string> = {
  // Gleb Komzin
  "gleb": "Gleb",
  "komzin": "Gleb",
  "komzin gleb": "Gleb",
  // Mathias Hummel
  "mathias": "Mathias",
  "hummel": "Mathias",
  "hummel mathias": "Mathias",
  // Niko / Nikolaos Giannas
  "niko": "Niko",
  "nikolaos": "Niko",
  "giannas": "Niko",
  "giannas nikolaos": "Niko",
  // Jan Philipp Gieselberg
  "jan philipp": "Jan Philipp",
  "jan": "Jan Philipp",
  "jp": "Jan Philipp",
  "gieselberg": "Jan Philipp",
  "gieselberg jan philipp": "Jan Philipp",
  // Faruk Toy
  "faruk": "Faruk",
  "toy": "Faruk",
  "toy faruk": "Faruk",
  // Bernadette Heidl
  "bernadette": "Bernadette",
  "berni": "Bernadette",
  "heidl": "Bernadette",
  "heidl bernadette": "Bernadette",
  // Darius Kauthe
  "darius": "Darius",
  "kauthe": "Darius",
  "kauthe darius": "Darius",
  // Sebastian Barth
  "sebastian": "Sebastian",
  "barth": "Sebastian",
  "barth sebastian": "Sebastian",
  // Florian Haferkorn
  "florian": "Florian",
  "haferkorn": "Florian",
  "haferkorn florian": "Florian",
  // Jan Lang
  "jan lang": "Jan Lang",
  "lang": "Jan Lang",
  "lang jan": "Jan Lang",
  // Sieglinde von Zieten
  "sieglinde": "Sieglinde",
  "von zieten": "Sieglinde",
  "von zieten sieglinde": "Sieglinde",
  // Julia Orlova
  "julia": "Julia",
  "orlova": "Julia",
  "orlova julia": "Julia",
  // Oliver Droste
  "oliver": "Oliver",
  "droste": "Oliver",
  "droste oliver": "Oliver",
  // Ute Bonnen
  "ute": "Ute",
  "bonnen": "Ute",
  "bonnen ute": "Ute",
  // Special assignments
  "extern": "Extern",
  "nicht zugeordnet": "Nicht zugeordnet",
};

/** Resolve a person name from a query fragment. Case-insensitive. */
export function resolvePerson(input: string): string | null {
  const key = input.trim().toLowerCase();
  return PEOPLE_MAP[key] ?? null;
}

/** Status value normalization map. Keys are lowercase. */
export const STATUS_MAP: Record<string, string> = {
  "offen": "offen",
  "open": "offen",
  "in arbeit": "in Arbeit",
  "in progress": "in Arbeit",
  "in bearbeitung": "in Arbeit",
  "erledigt": "erledigt",
  "done": "erledigt",
  "abgeschlossen": "erledigt",
  "closed": "erledigt",
  "geschlossen": "erledigt",
  "blockiert": "blockiert",
  "blocked": "blockiert",
  "gelöst": "gelöst",
  "resolved": "gelöst",
  "aktiv": "aktiv",
  "active": "aktiv",
  "on hold": "on hold",
  "pausiert": "on hold",
  "genehmigt": "genehmigt",
  "approved": "genehmigt",
  "abgelehnt": "abgelehnt",
  "rejected": "abgelehnt",
  "not started": "not started",
  "nicht begonnen": "not started",
};

/**
 * Reverse map: normalized status → all DB variants that represent this status.
 * Used when querying the database to match all possible stored values.
 */
export const STATUS_DB_VARIANTS: Record<string, string[]> = {
  "offen": ["offen", "open"],
  "in Arbeit": ["in Arbeit", "in_progress", "in progress"],
  "erledigt": ["erledigt", "done", "closed"],
  "blockiert": ["blockiert", "blocked"],
  "gelöst": ["gelöst", "resolved"],
  "aktiv": ["aktiv", "active"],
  "on hold": ["on hold", "paused", "pausiert"],
  "genehmigt": ["genehmigt", "approved"],
  "abgelehnt": ["abgelehnt", "rejected"],
  "not started": ["not started", "nicht begonnen"],
};

/** Get all DB-level status values for a normalized status. */
export function getStatusDbVariants(normalizedStatus: string): string[] {
  return STATUS_DB_VARIANTS[normalizedStatus] ?? [normalizedStatus];
}

/** Priority normalization map. Keys are lowercase. */
export const PRIORITY_MAP: Record<string, string> = {
  "hoch": "hoch",
  "high": "hoch",
  "mittel": "mittel",
  "medium": "mittel",
  "niedrig": "niedrig",
  "low": "niedrig",
  "kritisch": "kritisch",
  "critical": "kritisch",
  "dringend": "hoch",
  "urgent": "hoch",
};

/** Reverse map: normalized priority → all DB variants. */
export const PRIORITY_DB_VARIANTS: Record<string, string[]> = {
  "hoch": ["hoch", "high"],
  "mittel": ["mittel", "medium"],
  "niedrig": ["niedrig", "low"],
  "kritisch": ["kritisch", "critical", "urgent"],
};

/** Get all DB-level priority values for a normalized priority. */
export function getPriorityDbVariants(normalizedPriority: string): string[] {
  return PRIORITY_DB_VARIANTS[normalizedPriority] ?? [normalizedPriority];
}

/** Synonyms for entity types. Keys are lowercase user terms, values are DB entity_type values. */
export const ENTITY_SYNONYMS: Record<string, string[]> = {
  "todo": ["todos"],
  "todos": ["todos"],
  "aufgabe": ["todos"],
  "aufgaben": ["todos"],
  "task": ["todos"],
  "tasks": ["todos"],
  "blocker": ["blockers"],
  "blockers": ["blockers"],
  "blockierung": ["blockers"],
  "blockierungen": ["blockers"],
  "hindernis": ["blockers"],
  "hindernisse": ["blockers"],
  "open item": ["open_items"],
  "open items": ["open_items"],
  "offene punkte": ["open_items"],
  "offener punkt": ["open_items"],
  "offenes thema": ["open_items"],
  "offene themen": ["open_items"],
  "entscheidung": ["decisions"],
  "entscheidungen": ["decisions"],
  "decision": ["decisions"],
  "decisions": ["decisions"],
  "meeting": ["meetings"],
  "meetings": ["meetings"],
  "besprechung": ["meetings"],
  "besprechungen": ["meetings"],
  "sitzung": ["meetings"],
  "projekt": ["projects"],
  "projekte": ["projects"],
  "project": ["projects"],
  "projects": ["projects"],
  // Composite shortcuts
  "alles": ["todos", "blockers", "open_items", "decisions"],
  "alle items": ["todos", "blockers", "open_items"],
  "all": ["todos", "blockers", "open_items", "decisions"],
};

/** German number words to digits. */
export const WORD_NUMBERS: Record<string, number> = {
  "eins": 1,
  "ein": 1,
  "eine": 1,
  "einem": 1,
  "einen": 1,
  "zwei": 2,
  "drei": 3,
  "vier": 4,
  "fünf": 5,
  "sechs": 6,
  "sieben": 7,
  "acht": 8,
  "neun": 9,
  "zehn": 10,
  "elf": 11,
  "zwölf": 12,
  "dreizehn": 13,
  "vierzehn": 14,
};

/** Stopwords to strip from semantic query extraction. */
export const STOPWORDS = new Set([
  "der", "die", "das", "den", "dem", "des",
  "ein", "eine", "einen", "einem", "eines",
  "und", "oder", "aber", "auch", "noch",
  "ist", "sind", "war", "waren", "wird", "werden",
  "hat", "haben", "hatte", "hatten",
  "ich", "du", "er", "sie", "es", "wir", "ihr",
  "mich", "mir", "dich", "dir", "uns", "euch",
  "was", "wer", "wie", "wo", "wann", "warum", "welche", "welcher", "welches",
  "zu", "in", "an", "auf", "für", "mit", "von", "bei", "nach", "über", "unter",
  "aus", "um", "bis", "durch", "gegen", "ohne", "zwischen",
  "nicht", "kein", "keine", "keinen", "keinem",
  "alle", "alles", "jede", "jeder", "jedes",
  "gibt", "es", "gibt's",
  "mal", "denn", "schon", "ja", "nein",
  "zeig", "zeige", "gib", "liste", "nenne", "sag",
  "bitte", "mir", "doch", "nur", "noch",
  "the", "a", "an", "is", "are", "was", "were",
  "show", "me", "list", "give", "tell", "get", "find",
  "what", "which", "who", "where", "when", "how",
  "all", "any", "some",
]);

/** Project alias lookup. Keys are lowercase. */
export const PROJECT_ALIASES: Record<string, { id: string; name: string }> = {
  "power bi": { id: "a1b2c3d4-0000-0000-0000-000000000001", name: "Power BI Migration" },
  "power bi migration": { id: "a1b2c3d4-0000-0000-0000-000000000001", name: "Power BI Migration" },
  "powerbi": { id: "a1b2c3d4-0000-0000-0000-000000000001", name: "Power BI Migration" },
  "bi migration": { id: "a1b2c3d4-0000-0000-0000-000000000001", name: "Power BI Migration" },
  "pbi": { id: "a1b2c3d4-0000-0000-0000-000000000001", name: "Power BI Migration" },
  "website": { id: "b2c3d4e5-0000-0000-0000-000000000002", name: "Website Relaunch" },
  "website relaunch": { id: "b2c3d4e5-0000-0000-0000-000000000002", name: "Website Relaunch" },
  "relaunch": { id: "b2c3d4e5-0000-0000-0000-000000000002", name: "Website Relaunch" },
  "webseite": { id: "b2c3d4e5-0000-0000-0000-000000000002", name: "Website Relaunch" },
};

/** Resolve a project from a query fragment. */
export function resolveProject(input: string): { id: string; name: string } | null {
  const key = input.trim().toLowerCase();
  return PROJECT_ALIASES[key] ?? null;
}

/** Resolve entity types from a query term. */
export function resolveEntityType(input: string): string[] | null {
  const key = input.trim().toLowerCase();
  return ENTITY_SYNONYMS[key] ?? null;
}

/** Resolve a status value from user input. */
export function resolveStatus(input: string): string | null {
  const key = input.trim().toLowerCase();
  return STATUS_MAP[key] ?? null;
}

/** Resolve a priority value from user input. */
export function resolvePriority(input: string): string | null {
  const key = input.trim().toLowerCase();
  return PRIORITY_MAP[key] ?? null;
}

/** Parse a German number word or digit string to a number. */
export function parseNumber(input: string): number | null {
  const trimmed = input.trim().toLowerCase();
  if (WORD_NUMBERS[trimmed] !== undefined) return WORD_NUMBERS[trimmed];
  const n = parseInt(trimmed, 10);
  return isNaN(n) ? null : n;
}
