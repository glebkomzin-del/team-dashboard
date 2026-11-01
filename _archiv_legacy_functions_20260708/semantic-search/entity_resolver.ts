// entity_resolver.ts — Canonical entity resolution for persons, projects, and topics.
//
// Persons are resolved from query text to a PersonEntry that carries:
//   - canonical_name: used in responses
//   - db_name_variants: exact values as stored in DB columns (assignee, reported_by, owner, decided_by)
//   - participant_patterns: ILIKE patterns for searching meetings.participants (ARRAY column)
//   - aliases: lowercase terms a user might type
//
// The separation between db_name_variants (exact match) and participant_patterns (ILIKE)
// is necessary because meetings.participants stores "Lastname, Firstname" while todos.assignee
// may store "Firstname" or a different format.

export interface PersonEntry {
  person_id: string;
  display_name: string;
  canonical_name: string;
  aliases: string[]; // all lowercase query terms that resolve to this person
  db_name_variants: string[]; // exact values stored in assignee/owner/reported_by columns
  participant_patterns: string[]; // ILIKE patterns for meetings.participants::text
  active: boolean;
}

export const PERSON_LEXICON: PersonEntry[] = [
  {
    person_id: "niko",
    display_name: "Niko",
    canonical_name: "Niko",
    aliases: ["niko", "nico", "nikolaos", "giannas", "nikos", "nikolaus"],
    db_name_variants: ["Niko", "Nikolaos", "Giannas, Nikolaos", "Nikolaos Giannas"],
    participant_patterns: ["%Giannas%", "%Nikolaos%"],
    active: true,
  },
  {
    person_id: "mathias",
    display_name: "Mathias",
    canonical_name: "Mathias",
    aliases: ["mathias", "hummel", "matthias"],
    db_name_variants: ["Mathias", "Hummel, Mathias", "Mathias Hummel"],
    participant_patterns: ["%Hummel%"],
    active: true,
  },
  {
    person_id: "jan-philipp",
    display_name: "Jan Philipp",
    canonical_name: "Jan Philipp",
    aliases: ["jan philipp", "jan-philipp", "jp", "gieselberg"],
    db_name_variants: ["Jan Philipp", "Gieselberg, Jan Philipp", "Jan Philipp Gieselberg"],
    participant_patterns: ["%Gieselberg%", "%Jan Philipp%"],
    active: true,
  },
  {
    person_id: "darius",
    display_name: "Darius",
    canonical_name: "Darius",
    aliases: ["darius", "kauthe", "darius kauthe"],
    db_name_variants: ["Darius", "Kauthe, Darius", "Darius Kauthe"],
    participant_patterns: ["%Kauthe%", "%Darius%"],
    active: true,
  },
  {
    person_id: "bernadette",
    display_name: "Bernadette",
    canonical_name: "Bernadette",
    aliases: ["bernadette", "heidl", "bernadette heidl", "berni"],
    db_name_variants: ["Bernadette", "Heidl, Bernadette", "Bernadette Heidl"],
    participant_patterns: ["%Heidl%", "%Bernadette%"],
    active: true,
  },
  {
    person_id: "caroline",
    display_name: "Caroline",
    canonical_name: "Caroline",
    aliases: ["caroline", "witschorke", "caroline witschorke"],
    db_name_variants: ["Caroline", "Witschorke, Caroline", "Caroline Witschorke"],
    participant_patterns: ["%Witschorke%", "%Caroline%"],
    active: true,
  },
  {
    person_id: "gleb",
    display_name: "Gleb",
    canonical_name: "Gleb",
    aliases: ["gleb", "komzin", "gleb komzin"],
    db_name_variants: ["Gleb", "Komzin, Gleb", "Gleb Komzin"],
    participant_patterns: ["%Komzin%", "%Gleb%"],
    active: true,
  },
  {
    person_id: "sebastian",
    display_name: "Sebastian",
    canonical_name: "Sebastian",
    aliases: ["sebastian", "hehs", "sebastian hehs"],
    db_name_variants: ["Sebastian", "Hehs, Sebastian", "Sebastian Hehs"],
    participant_patterns: ["%Hehs%", "%Sebastian%"],
    active: true,
  },
  {
    person_id: "daniela",
    display_name: "Daniela",
    canonical_name: "Daniela",
    aliases: ["daniela", "vorndran", "daniela vorndran"],
    db_name_variants: ["Daniela", "Vorndran, Daniela", "Daniela Vorndran"],
    participant_patterns: ["%Vorndran%", "%Daniela%"],
    active: true,
  },
  {
    person_id: "thomas",
    display_name: "Thomas",
    canonical_name: "Thomas",
    aliases: ["thomas", "peckhaus", "thomas peckhaus"],
    db_name_variants: ["Thomas", "Peckhaus, Thomas", "Thomas Peckhaus"],
    participant_patterns: ["%Peckhaus%"],
    active: true,
  },
  {
    person_id: "marc",
    display_name: "Marc",
    canonical_name: "Marc",
    aliases: ["marc", "kursawe", "marc kursawe"],
    db_name_variants: ["Marc", "Kursawe, Marc", "Marc Kursawe"],
    participant_patterns: ["%Kursawe%"],
    active: true,
  },
  {
    person_id: "andre",
    display_name: "André",
    canonical_name: "André",
    aliases: ["andré", "andre", "brandt", "andre brandt", "andré brandt"],
    db_name_variants: ["André", "Brandt, André", "André Brandt"],
    participant_patterns: ["%Brandt%"],
    active: true,
  },
  {
    person_id: "tim",
    display_name: "Tim",
    canonical_name: "Tim",
    aliases: ["tim", "kilp", "tim kilp"],
    db_name_variants: ["Tim", "Kilp, Tim", "Tim Kilp"],
    participant_patterns: ["%Kilp%"],
    active: true,
  },
  {
    person_id: "jonas",
    display_name: "Jonas",
    canonical_name: "Jonas",
    aliases: ["jonas", "schmidt", "jonas schmidt"],
    db_name_variants: ["Jonas", "Schmidt, Jonas", "Jonas Schmidt"],
    participant_patterns: ["%Schmidt, Jonas%"],
    active: true,
  },
  {
    person_id: "marika",
    display_name: "Marika",
    canonical_name: "Marika",
    aliases: ["marika", "massari", "marika massari"],
    db_name_variants: ["Marika", "Massari, Marika", "Marika Massari"],
    participant_patterns: ["%Massari%"],
    active: true,
  },
  {
    person_id: "julia",
    display_name: "Julia",
    canonical_name: "Julia",
    aliases: ["julia", "orlova", "julia orlova"],
    db_name_variants: ["Julia", "Orlova, Julia", "Julia Orlova"],
    participant_patterns: ["%Orlova%"],
    active: true,
  },
  {
    person_id: "torben",
    display_name: "Torben",
    canonical_name: "Torben",
    aliases: ["torben", "schaff", "torben schaff"],
    db_name_variants: ["Torben", "Schaff, Torben", "Torben Schaff"],
    participant_patterns: ["%Schaff%"],
    active: true,
  },
  {
    person_id: "vadim",
    display_name: "Vadim",
    canonical_name: "Vadim",
    aliases: ["vadim", "pustilnikov", "vadim pustilnikov"],
    db_name_variants: ["Vadim", "Pustilnikov, Vadim", "Vadim Pustilnikov"],
    participant_patterns: ["%Pustilnikov%"],
    active: true,
  },
  {
    person_id: "faruk",
    display_name: "Faruk",
    canonical_name: "Faruk",
    aliases: ["faruk", "toy", "faruk toy"],
    db_name_variants: ["Faruk", "Toy, Faruk", "Faruk Toy"],
    participant_patterns: ["%Toy%"],
    active: true,
  },
  {
    person_id: "marvin",
    display_name: "Marvin",
    canonical_name: "Marvin",
    aliases: ["marvin", "paul", "marvin paul"],
    db_name_variants: ["Marvin", "Paul, Marvin", "Marvin Paul"],
    participant_patterns: ["%Paul, Marvin%"],
    active: true,
  },
  {
    person_id: "sieglinde",
    display_name: "Sieglinde",
    canonical_name: "Sieglinde",
    aliases: ["sieglinde", "von zieten", "sieglinde von zieten"],
    db_name_variants: ["Sieglinde", "von Zieten, Sieglinde", "Sieglinde von Zieten"],
    participant_patterns: ["%Zieten%"],
    active: true,
  },
  {
    person_id: "jan-lang",
    display_name: "Jan Lang",
    canonical_name: "Jan Lang",
    aliases: ["jan lang", "lang", "lang, jan"],
    db_name_variants: ["Jan Lang", "Lang, Jan", "Jan"],
    participant_patterns: ["%Lang, Jan%", "%Jan Lang%"],
    active: true,
  },
  {
    person_id: "florian",
    display_name: "Florian",
    canonical_name: "Florian",
    aliases: ["florian", "haferkorn", "florian haferkorn"],
    db_name_variants: ["Florian", "Haferkorn, Florian", "Florian Haferkorn"],
    participant_patterns: ["%Haferkorn%"],
    active: true,
  },
  {
    person_id: "christoph",
    display_name: "Christoph",
    canonical_name: "Christoph",
    aliases: ["christoph", "karloff", "christoph karloff"],
    db_name_variants: ["Christoph", "Karloff, Christoph", "Christoph Karloff"],
    participant_patterns: ["%Karloff%"],
    active: true,
  },
  {
    person_id: "daniel",
    display_name: "Daniel",
    canonical_name: "Daniel",
    aliases: ["daniel", "göttling", "goettling", "daniel göttling", "daniel goettling"],
    db_name_variants: ["Daniel", "Göttling, Daniel", "Daniel Göttling"],
    participant_patterns: ["%Göttling%", "%Goettling%"],
    active: true,
  },
  {
    person_id: "cenk",
    display_name: "Cenk",
    canonical_name: "Cenk",
    aliases: ["cenk", "genisol", "cenk genisol"],
    db_name_variants: ["Cenk", "Genisol, Cenk", "Cenk Genisol"],
    participant_patterns: ["%Genisol%"],
    active: true,
  },
  {
    person_id: "patrizia",
    display_name: "Patrizia",
    canonical_name: "Patrizia",
    aliases: ["patrizia", "aundrup", "patrizia aundrup"],
    db_name_variants: ["Patrizia", "Aundrup, Patrizia", "Patrizia Aundrup"],
    participant_patterns: ["%Aundrup%"],
    active: true,
  },
  {
    person_id: "oliver",
    display_name: "Oliver",
    canonical_name: "Oliver",
    aliases: ["oliver", "droste", "oliver droste"],
    db_name_variants: ["Oliver", "Droste, Oliver", "Oliver Droste"],
    participant_patterns: ["%Droste%"],
    active: true,
  },
  {
    person_id: "cornelia",
    display_name: "Cornelia",
    canonical_name: "Cornelia",
    aliases: ["cornelia", "nikolai", "cornelia nikolai"],
    db_name_variants: ["Cornelia", "Nikolai, Cornelia", "Cornelia Nikolai"],
    participant_patterns: ["%Nikolai%"],
    active: true,
  },
  {
    person_id: "maryam",
    display_name: "Maryam",
    canonical_name: "Maryam",
    aliases: ["maryam", "mariam"],
    db_name_variants: ["Maryam", "Mariam"],
    participant_patterns: ["%Maryam%", "%Mariam%"],
    active: true,
  },
];

// Pre-built lookup: alias -> PersonEntry (longest first for matching)
const _aliasIndex: { alias: string; person: PersonEntry }[] = PERSON_LEXICON
  .flatMap((p) => p.aliases.map((a) => ({ alias: a, person: p })))
  .sort((a, b) => b.alias.length - a.alias.length);

/**
 * Resolve all persons mentioned in a query string.
 * Uses longest-alias-first matching to avoid "jan" shadowing "jan philipp".
 */
export function resolvePersonsFromQuery(query: string): PersonEntry[] {
  const q = query.toLowerCase();
  const found: PersonEntry[] = [];
  const seen = new Set<string>();
  for (const { alias, person } of _aliasIndex) {
    if (!seen.has(person.person_id) && q.includes(alias)) {
      seen.add(person.person_id);
      found.push(person);
    }
  }
  return found;
}

/**
 * Build the OR-filter string for Supabase .or() on participants::text.
 * Returns Supabase filter expression like:
 *   "participants::text.ilike.%Kauthe%,participants::text.ilike.%Darius%"
 */
export function buildParticipantFilter(person: PersonEntry): string {
  // Use the most specific pattern (last-name only, avoids ambiguity)
  // Primary: first pattern in participant_patterns (usually "%Lastname%")
  return person.participant_patterns
    .map((p) => `participants::text.ilike.${p}`)
    .join(",");
}

/**
 * All exact-match values to try for assignee/owner/reported_by/decided_by columns.
 * The DB may store "Niko", "Giannas, Nikolaos", etc. — try all variants.
 */
export function getPersonAssigneeVariants(person: PersonEntry): string[] {
  return [...new Set([person.canonical_name, ...person.db_name_variants])];
}

/**
 * Backward-compat: resolve canonical name string (used by old code paths).
 */
export function resolveCanonicalName(query: string): string | null {
  const persons = resolvePersonsFromQuery(query);
  return persons.length > 0 ? persons[0].canonical_name : null;
}

// ── Dynamic person lexicon (DB-backed, cached per isolate) ────────────────────

// Maps lowercase name variant → array of raw DB values (e.g. "haferkorn" → ["Haferkorn, Florian"])
let _dynamicPersonMap: Map<string, string[]> | null = null;
let _dynamicPersonMapAt = 0;
const DYNAMIC_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function _addNameVariants(map: Map<string, string[]>, rawName: string): void {
  if (!rawName?.trim()) return;
  const name = rawName.trim();
  const put = (key: string) => {
    const arr = map.get(key) ?? [];
    if (!arr.includes(name)) arr.push(name);
    map.set(key, arr);
  };
  put(name.toLowerCase());
  if (name.includes(",")) {
    const [last, first] = name.split(",").map((s) => s.trim());
    if (first) put(`${first} ${last}`.toLowerCase());
    put(last.toLowerCase());
    if (first) put(first.toLowerCase());
  } else {
    const parts = name.split(/\s+/);
    if (parts.length >= 2) parts.forEach((p) => put(p.toLowerCase()));
  }
}

async function _loadDynamicPersonMap(
  // deno-lint-ignore no-explicit-any
  supabase: any,
): Promise<Map<string, string[]>> {
  const now = Date.now();
  if (_dynamicPersonMap && now - _dynamicPersonMapAt < DYNAMIC_CACHE_TTL) {
    return _dynamicPersonMap;
  }

  const [c, d, t, ch] = await Promise.all([
    supabase.from("commitments").select("person").not("person", "is", null),
    supabase.from("decisions").select("speaker").not("speaker", "is", null),
    supabase.from("team_members").select("name").not("name", "is", null),
    supabase
      .from("transcript_chunks")
      .select("speaker")
      .not("speaker", "is", null)
      .neq("speaker", "__meta__")
      .limit(3000),
  ]);

  const map = new Map<string, string[]>();
  for (const row of c.data ?? []) _addNameVariants(map, row.person);
  for (const row of d.data ?? []) _addNameVariants(map, row.speaker);
  for (const row of t.data ?? []) _addNameVariants(map, row.name);
  for (const row of ch.data ?? []) _addNameVariants(map, row.speaker);

  _dynamicPersonMap = map;
  _dynamicPersonMapAt = now;
  console.log(`[entity_resolver] Dynamic map loaded: ${map.size} name variants`);
  return map;
}

function _buildPersonEntryFromName(
  rawName: string,
  dbVariants: string[],
): PersonEntry {
  const parts = rawName.trim().split(/\s+/);
  const lastName = parts.length >= 2 ? parts[parts.length - 1] : rawName;
  const allVariants = [...new Set([rawName, ...dbVariants])];

  return {
    person_id: `dynamic_${rawName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    display_name: rawName,
    canonical_name: rawName,
    aliases: [...new Set(allVariants.map((v) => v.toLowerCase()))],
    db_name_variants: allVariants,
    participant_patterns: [`%${lastName}%`],
    active: true,
  };
}

/**
 * Resolves persons from a query, enriching the static lexicon with DB-loaded names.
 * Falls back gracefully to static-only results on any error.
 *
 * @param haikuPersonNames  Names extracted by Haiku (from entities.persons) — tried first
 */
export async function resolvePersonsFromQueryDynamic(
  query: string,
  // deno-lint-ignore no-explicit-any
  supabase: any,
  haikuPersonNames: string[] = [],
): Promise<PersonEntry[]> {
  const staticResults = resolvePersonsFromQuery(query);
  if (!supabase) return staticResults;

  try {
    const dynamicMap = await _loadDynamicPersonMap(supabase);
    const q = query.toLowerCase();

    const results: PersonEntry[] = [...staticResults];
    const addedIds = new Set(staticResults.map((p) => p.person_id));
    const knownVariants = new Set(
      staticResults.flatMap((p) => p.db_name_variants.map((v) => v.toLowerCase())),
    );

    const tryAdd = (rawName: string) => {
      if (!rawName?.trim()) return;
      const lower = rawName.toLowerCase();
      // Already covered by static resolver?
      if (
        staticResults.some(
          (p) =>
            p.aliases.includes(lower) ||
            p.canonical_name.toLowerCase() === lower,
        )
      ) return;

      const pid = `dynamic_${lower.replace(/[^a-z0-9]+/g, "-")}`;
      if (addedIds.has(pid)) return;

      // Gather DB variants for this name
      const dbVariants: string[] = [];
      for (const [key, vals] of dynamicMap) {
        if (
          key === lower ||
          (lower.length > 3 && key.length > 3 &&
            (lower.includes(key) || key.includes(lower)))
        ) {
          vals.forEach((v) => {
            if (!knownVariants.has(v.toLowerCase())) dbVariants.push(v);
          });
        }
      }

      const entry = _buildPersonEntryFromName(rawName, dbVariants);
      results.push(entry);
      addedIds.add(pid);
      dbVariants.forEach((v) => knownVariants.add(v.toLowerCase()));
      console.log(
        `[entity_resolver] Dynamic person: ${rawName} (${dbVariants.length} DB variants)`,
      );
    };

    // 1. Haiku-extracted persons (LLM is good at name recognition)
    for (const name of haikuPersonNames) tryAdd(name);

    // 2. Direct scan of query against dynamic map (catches names Haiku might miss)
    for (const [key, vals] of dynamicMap) {
      if (key.length <= 3) continue;
      if (!q.includes(key)) continue;
      if (results.some((p) => p.aliases.includes(key) || p.db_name_variants.some((v) => vals.includes(v)))) continue;

      const displayName =
        vals.find((v) => /^[A-ZÜÖÄ]/.test(v) && v.includes(" ") && !v.includes(",")) ??
        vals.find((v) => v.includes(",")) ??
        vals[0];
      if (displayName) tryAdd(displayName);
    }

    return results;
  } catch (e) {
    console.error(
      "[entity_resolver] Dynamic resolve failed, using static:",
      String(e).slice(0, 150),
    );
    return staticResults;
  }
}
