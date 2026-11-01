// time_parser.ts — German-aware time range parser

import { WORD_NUMBERS } from "./lexicon.ts";

export interface TimeRange {
  from: string; // ISO date string
  to: string;   // ISO date string
  mode: string; // e.g. 'day', 'week', 'month', 'quarter', 'range', 'since'
  confidence: number; // 0..1
  phrase: string; // matched input phrase
}

const DAY_NAMES: Record<string, number> = {
  "montag": 1, "dienstag": 2, "mittwoch": 3, "donnerstag": 4,
  "freitag": 5, "samstag": 6, "sonntag": 0,
  "monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4,
  "friday": 5, "saturday": 6, "sunday": 0,
};

const MONTH_NAMES: Record<string, number> = {
  "januar": 0, "februar": 1, "märz": 2, "maerz": 2, "april": 3,
  "mai": 4, "juni": 5, "juli": 6, "august": 7,
  "september": 8, "oktober": 9, "november": 10, "dezember": 11,
  "january": 0, "february": 1, "march": 2, "may": 4,
  "june": 5, "july": 6, "october": 9, "december": 11,
};

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}

function endOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);
}

/** Monday of the ISO week containing `d`. */
function mondayOfWeek(d: Date): Date {
  const day = d.getDay(); // 0=Sun
  const diff = day === 0 ? -6 : 1 - day;
  const mon = new Date(d.getFullYear(), d.getMonth(), d.getDate() + diff);
  return mon;
}

function parseWordNumber(s: string): number | null {
  const key = s.trim().toLowerCase();
  if (WORD_NUMBERS[key] !== undefined) return WORD_NUMBERS[key];
  const n = parseInt(key, 10);
  return isNaN(n) ? null : n;
}

function iso(d: Date): string {
  return d.toISOString();
}

export function parseTimeRange(query: string, now: Date): TimeRange | null {
  const q = query.toLowerCase().trim();
  const today = startOfDay(now);

  // heute / today
  if (/\bheute\b|\btoday\b/.test(q)) {
    return { from: iso(today), to: iso(endOfDay(now)), mode: "day", confidence: 1, phrase: "heute" };
  }

  // gestern / yesterday
  if (/\bgestern\b|\byesterday\b/.test(q)) {
    const d = new Date(today); d.setDate(d.getDate() - 1);
    return { from: iso(d), to: iso(endOfDay(d)), mode: "day", confidence: 1, phrase: "gestern" };
  }

  // morgen / tomorrow
  if (/\bmorgen\b/.test(q) && !/\bguten morgen\b/.test(q)) {
    // Distinguish "morgen" (tomorrow) from "guten morgen" (good morning)
    const d = new Date(today); d.setDate(d.getDate() + 1);
    return { from: iso(d), to: iso(endOfDay(d)), mode: "day", confidence: 0.8, phrase: "morgen" };
  }

  // vorletzte Woche
  if (/\bvorletzte\s+woche\b/.test(q)) {
    const mon = mondayOfWeek(today);
    const start = new Date(mon); start.setDate(start.getDate() - 14);
    const end = new Date(start); end.setDate(end.getDate() + 6);
    return { from: iso(start), to: iso(endOfDay(end)), mode: "week", confidence: 1, phrase: "vorletzte Woche" };
  }

  // letzte Woche — last calendar week (Mon–Sun)
  if (/\bletzte\s+woche\b|\blast\s+week\b/.test(q)) {
    const mon = mondayOfWeek(today);
    const start = new Date(mon); start.setDate(start.getDate() - 7);
    const end = new Date(start); end.setDate(end.getDate() + 6);
    return { from: iso(start), to: iso(endOfDay(end)), mode: "week", confidence: 1, phrase: "letzte Woche" };
  }

  // diese Woche — current calendar week (Mon–now)
  if (/\bdiese\s+woche\b|\bthis\s+week\b/.test(q)) {
    const mon = mondayOfWeek(today);
    return { from: iso(mon), to: iso(endOfDay(now)), mode: "week", confidence: 1, phrase: "diese Woche" };
  }

  // letzten N Wochen
  {
    const m = q.match(/\bletzten?\s+(\w+)\s+wochen?\b/);
    if (m) {
      const n = parseWordNumber(m[1]);
      if (n) {
        const from = new Date(today); from.setDate(from.getDate() - n * 7);
        return { from: iso(from), to: iso(endOfDay(now)), mode: "weeks", confidence: 0.9, phrase: m[0] };
      }
    }
  }

  // letzten N Tage
  {
    const m = q.match(/\bletzten?\s+(\w+)\s+tage?\b/);
    if (m) {
      const n = parseWordNumber(m[1]);
      if (n) {
        const from = new Date(today); from.setDate(from.getDate() - n);
        return { from: iso(from), to: iso(endOfDay(now)), mode: "days", confidence: 0.9, phrase: m[0] };
      }
    }
  }

  // seit Montag/Dienstag/...
  {
    const m = q.match(/\bseit\s+(\w+)\b/);
    if (m) {
      const dayName = m[1].toLowerCase();
      const targetDay = DAY_NAMES[dayName];
      if (targetDay !== undefined) {
        const currentDay = now.getDay();
        let diff = currentDay - targetDay;
        if (diff < 0) diff += 7;
        if (diff === 0) diff = 0; // seit today's day name means since today
        const from = new Date(today); from.setDate(from.getDate() - diff);
        return { from: iso(from), to: iso(endOfDay(now)), mode: "since", confidence: 0.9, phrase: m[0] };
      }

      // seit + month name
      const monthIdx = MONTH_NAMES[dayName];
      if (monthIdx !== undefined) {
        let year = now.getFullYear();
        if (monthIdx > now.getMonth()) year--; // if month is in the future, assume last year
        const from = new Date(year, monthIdx, 1);
        return { from: iso(from), to: iso(endOfDay(now)), mode: "since", confidence: 0.85, phrase: m[0] };
      }
    }
  }

  // im Januar/Februar/... or specific month
  {
    const m = q.match(/\b(?:im|in)\s+(\w+)\b/);
    if (m) {
      const monthIdx = MONTH_NAMES[m[1].toLowerCase()];
      if (monthIdx !== undefined) {
        let year = now.getFullYear();
        if (monthIdx > now.getMonth()) year--; // if the month hasn't happened yet this year
        const from = new Date(year, monthIdx, 1);
        const to = new Date(year, monthIdx + 1, 0); // last day of month
        return { from: iso(from), to: iso(endOfDay(to)), mode: "month", confidence: 0.9, phrase: m[0] };
      }
    }
  }

  // am X. Mai / am 15. / am 3. Januar
  {
    const m = q.match(/\bam\s+(\d{1,2})\.\s*(\w*)/);
    if (m) {
      const day = parseInt(m[1], 10);
      let month = now.getMonth();
      let year = now.getFullYear();
      if (m[2]) {
        const mi = MONTH_NAMES[m[2].toLowerCase()];
        if (mi !== undefined) {
          month = mi;
          if (month > now.getMonth() || (month === now.getMonth() && day > now.getDate())) year--;
        }
      }
      const d = new Date(year, month, day);
      return { from: iso(d), to: iso(endOfDay(d)), mode: "day", confidence: 0.9, phrase: m[0] };
    }
  }

  // zwischen X und Y (dates)
  {
    const m = q.match(/\bzwischen\s+(?:dem\s+)?(\d{1,2})\.?\s*(\w*)\s+und\s+(?:dem\s+)?(\d{1,2})\.?\s*(\w*)/);
    if (m) {
      const day1 = parseInt(m[1], 10);
      const day2 = parseInt(m[3], 10);
      let month1 = now.getMonth();
      let month2 = now.getMonth();
      const year = now.getFullYear();
      if (m[2]) { const mi = MONTH_NAMES[m[2].toLowerCase()]; if (mi !== undefined) month1 = mi; }
      if (m[4]) { const mi = MONTH_NAMES[m[4].toLowerCase()]; if (mi !== undefined) month2 = mi; }
      else { month2 = month1; }
      const from = new Date(year, month1, day1);
      const to = new Date(year, month2, day2);
      return { from: iso(from), to: iso(endOfDay(to)), mode: "range", confidence: 0.85, phrase: m[0] };
    }
  }

  // letzter Monat / letzten Monat
  if (/\bletzter?\s*monat\b|\bletzten\s*monat\b|\blast\s*month\b/.test(q)) {
    const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
    const to = new Date(now.getFullYear(), now.getMonth(), 0);
    return { from: iso(from), to: iso(endOfDay(to)), mode: "month", confidence: 1, phrase: "letzter Monat" };
  }

  // dieser Monat
  if (/\bdiese[rn]?\s*monat\b|\bthis\s*month\b/.test(q)) {
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from: iso(from), to: iso(endOfDay(now)), mode: "month", confidence: 1, phrase: "dieser Monat" };
  }

  // dieses Quartal
  if (/\bdieses\s*quartal\b|\bthis\s*quarter\b/.test(q)) {
    const qStart = Math.floor(now.getMonth() / 3) * 3;
    const from = new Date(now.getFullYear(), qStart, 1);
    return { from: iso(from), to: iso(endOfDay(now)), mode: "quarter", confidence: 0.9, phrase: "dieses Quartal" };
  }

  // letztes Quartal
  if (/\bletztes\s*quartal\b|\blast\s*quarter\b/.test(q)) {
    const qStart = Math.floor(now.getMonth() / 3) * 3;
    const from = new Date(now.getFullYear(), qStart - 3, 1);
    const to = new Date(now.getFullYear(), qStart, 0);
    return { from: iso(from), to: iso(endOfDay(to)), mode: "quarter", confidence: 0.9, phrase: "letztes Quartal" };
  }

  return null;
}
