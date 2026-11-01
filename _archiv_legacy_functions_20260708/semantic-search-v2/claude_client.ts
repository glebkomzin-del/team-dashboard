// claude_client.ts — Claude API integration with system prompt construction

import type { RetrievalPlan } from "./retrieval_planner.ts";
import type { RetrievalAudit } from "./context_builder.ts";

const CLAUDE_API_URL = "https://api.anthropic.com/v1/messages";

const HAIKU_INTENTS = new Set([
  "meeting_list",
]);

function getMaxTokens(intent: string): number {
  const shortIntents = new Set([
    "count_query",
    "meeting_list",
  ]);
  if (shortIntents.has(intent)) return 400;
  return 2048;
}

function getModel(intent: string): string {
  if (HAIKU_INTENTS.has(intent)) {
    return "claude-haiku-4-5-20251001";
  }
  return "claude-sonnet-4-20250514";
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const SYSTEM_PROMPT_TEMPLATE = `Du bist Glebs persönlicher Job-Assistent für sein Team-Dashboard bei TEDi GmbH & Co. KG, Lünen. Gleb leitet das Group Controlling (Datenanalyse & Berichtswesen).

Direkte Vorgesetzte: Bernadette Heidl (scheidet Juli 2026 aus), Nachfolge: Caroline Witschorke.
Stakeholder: Darius Kauthe (CFO).
Team: Niko (intern), Mathias (extern, ER + Power BI), Jan Philipp (extern, Teilzeit, Power BI).

Heutiges Datum: {CURRENT_DATE}

SCHREIBSTIL:

Direkt anfangen. Das erste Wort ist niemals "Basierend", "Gerne", "Hier", "Als", "Ich" oder "Gemäß". Kein Kontext-Framing, keine Einleitung. Der erste Satz enthält bereits den ersten Fakt.

Dicht statt kurz. Fülltext weglassen, nicht Informationen. Namen, Zahlen, Daten direkt nennen. Wichtige Aussagen von Personen direkt wiedergeben, nicht paraphrasieren.

Sprache: Deutsch. Keine Emojis, keine Symbole (✅ ⚠️ ✓ ✗ 🔴).

Formatierung sinnvoll einsetzen:
- **Fettdruck** für Namen, Schlüsselbegriffe und wichtige Hervorhebungen
- _Kursiv_ für Einschränkungen, Ableitungen und Unsicherheiten
- Keine Markdown-Headers (#, ##) außer bei Management-Updates
- Bullets nur bei echten Listen (5+ gleichwertige Punkte) – sonst Fließtext
- Keine verschachtelten Listen

Keine Frage wiederholen. Nicht mit "Du hast gefragt..." beginnen. Kein Coaching-Duktus.

So lang wie nötig, nicht länger.

QUELLENKENNTLICHMACHUNG – immer einhalten:

Alles was direkt aus Meeting-Transkripten, Entscheidungen, Zusagen oder Todos stammt: normal formulieren.

Alles was aus dem Kontext logisch abgeleitet ist aber nicht explizit so gesagt wurde: _kursiv_ und mit Kennzeichnung wie _"lässt sich ableiten"_, _"liegt nahe"_ oder _"nicht explizit belegt"_.

Niemals Ableitungen als Fakten darstellen. Niemals etwas erfinden das nicht in den Daten steht.

STRUKTUR DER ANTWORT:

Die Struktur folgt der Frage – nicht einem festen Template. Wenn jemand fragt "Was wurde entschieden?" kommt eine Liste von Entscheidungen. Wenn jemand fragt "Fass das Meeting zusammen" kommt ein zusammenhängender Text. Wenn jemand ein Management-Update braucht kommt die Management-Update-Struktur.

Leere Sektionen werden niemals angezeigt – auch nicht bei Management-Updates. Was nicht in den Daten steht kommt nicht in die Antwort, es sei denn es ist explizit als Ableitung gekennzeichnet.

Management-Update-Struktur (nur wenn explizit angefragt oder klar aus dem Kontext):

**Kurzfazit**
[2-3 Sätze Gesamtbild]

**Fortschritt**
[Was wurde erreicht]

**Entscheidungen**
[Getroffene Beschlüsse mit Person und Datum]

**Offen**
[Laufende Punkte mit Zuständigkeit]

**Blockiert**
[Nur wenn tatsächlich Blocker in den Daten]

**Risiken**
[Nur wenn tatsächlich Risiken in den Daten]

**Nächste Schritte**
[Konkrete geplante Maßnahmen]

**Datenbasis**
[Welche Meetings/Quellen wurden verwendet]

REGELN:

1. Verwende ausschließlich die bereitgestellten DATEN, METADATEN und den RETRIEVAL_AUDIT.

2. Direkte Verknüpfungen (z.B. meeting_id) klar von logischen Ableitungen trennen. Ableitungen immer _kursiv_ und als solche kennzeichnen.

3. Bei Count-Anfragen direkt mit Zahlen antworten. Wenn der Count auf einem Suchergebnis statt dem Gesamtbestand basiert: klar sagen.

4. Bei Audit-Fragen ("Welche Daten hast du verwendet?", "Ist das vollständig?"): ausschließlich aus RETRIEVAL_AUDIT antworten.

5. Bei Widerspruch zwischen RETRIEVAL_AUDIT und DATEN: hinweisen. Live-Daten für Inhalte bevorzugen, Audit für Suchweg.

6. Wenn nur ein Teil der relevanten Daten übergeben wurde: am Ende kurz darauf hinweisen.

SUCHPLAN UND AUDIT:
{retrievalAudit}

KONTEXTDATEN:
{contextPacket}`;

/**
 * Format a RetrievalAudit as a compact, Claude-readable block for the system prompt.
 * Distinct from formatAuditAsMarkdown (which is the user-facing version for source_intent).
 */
function formatAuditForPrompt(
  audit: RetrievalAudit | null | undefined,
  intent: RetrievalPlan,
): string {
  if (!audit) {
    return `Intent: ${intent.intent} | Modus: ${intent.retrievalMode}\nKein Audit verfügbar (erster Call oder Audit nicht übertragen).`;
  }

  const lines: string[] = [];

  lines.push(`Intent: ${audit.intent} | Modus: ${intent.retrievalMode}`);

  // Detected entities
  const det: string[] = [];
  if (audit.detected.persons.length > 0) det.push(`Personen: ${audit.detected.persons.join(", ")}`);
  if (audit.detected.projects.length > 0) det.push(`Projekte: ${audit.detected.projects.join(", ")}`);
  if (audit.detected.topicAnchors.length > 0) det.push(`Themen: ${audit.detected.topicAnchors.join(", ")}`);
  if (audit.detected.statusFilters.length > 0) det.push(`Status-Filter: ${audit.detected.statusFilters.join(", ")}`);
  if (audit.detected.timeRange) {
    det.push(`Zeitraum: ${audit.detected.timeRange.phrase} (${audit.detected.timeRange.from.substring(0, 10)} – ${audit.detected.timeRange.to.substring(0, 10)})`);
  }
  if (det.length > 0) lines.push(`Erkannt: ${det.join(" | ")}`);

  // Tables + counts
  if (audit.tables_queried.length > 0) {
    lines.push(`Tabellen: ${audit.tables_queried.join(", ")}`);
  } else {
    lines.push("Tabellen: keine (kein Datenbankzugriff)");
  }

  const nonZeroCounts = Object.entries(audit.returned_counts).filter(([, v]) => v > 0);
  if (nonZeroCounts.length > 0) {
    lines.push(`Gefunden: ${nonZeroCounts.map(([k, v]) => `${k}=${v}`).join(", ")}`);
  } else {
    lines.push("Gefunden: 0 Einträge");
  }

  // Context budget
  lines.push(
    `Kontext-Budget: ${audit.full_detail_count} vollständig, ${audit.compact_count} kompakt, ${audit.aggregated_count} aggregiert` +
    (audit.vector_search_used ? " | Vektorsuche: ja" : ""),
  );

  // Quality
  lines.push(
    `Vollständigkeit: ${audit.retrieval_completeness} / ${audit.context_completeness} → Konfidenz: ${audit.answer_confidence}`,
  );

  if (audit.fallback_used.length > 0) {
    lines.push(`Fallbacks: ${audit.fallback_used.join(", ")}`);
  }
  if (audit.warnings.length > 0) {
    lines.push(`Warnungen: ${audit.warnings.join(", ")}`);
  }

  return lines.join("\n");
}

/**
 * Build the system prompt for Claude given a context packet, intent, and optional audit.
 */
export function buildSystemPrompt(
  contextPacket: string,
  intent: RetrievalPlan,
  audit?: RetrievalAudit | null,
): string {
  return SYSTEM_PROMPT_TEMPLATE
    .replace("{CURRENT_DATE}", new Date().toISOString().substring(0, 10))
    .replace("{retrievalAudit}", formatAuditForPrompt(audit, intent))
    .replace("{contextPacket}", contextPacket);
}

/**
 * Call Claude API (non-streaming) and return the full response text.
 */
export async function callClaude(
  systemPrompt: string,
  messages: ChatMessage[],
  intent = "general_question",
): Promise<string> {
  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");

  const response = await fetch(CLAUDE_API_URL, {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: getModel(intent),
      max_tokens: getMaxTokens(intent),
      system: systemPrompt,
      messages: messages.map((m) => ({ role: m.role, content: m.content })),
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Claude API error ${response.status}: ${body}`);
  }

  const json = await response.json();
  const textBlocks = json.content?.filter(
    (b: { type: string }) => b.type === "text",
  );
  return textBlocks?.map((b: { text: string }) => b.text).join("") ?? "";
}

/**
 * Stream Claude API response. Returns a ReadableStream of SSE-formatted chunks.
 */
export function streamClaudeResponse(
  systemPrompt: string,
  messages: ChatMessage[],
  intent = "general_question",
): ReadableStream<Uint8Array> {
  const apiKey = Deno.env.get("ANTHROPIC_API_KEY");
  if (!apiKey) throw new Error("ANTHROPIC_API_KEY not set");

  const encoder = new TextEncoder();

  return new ReadableStream({
    async start(controller) {
      try {
        const response = await fetch(CLAUDE_API_URL, {
          method: "POST",
          headers: {
            "x-api-key": apiKey,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
          },
          body: JSON.stringify({
            model: getModel(intent),
            max_tokens: getMaxTokens(intent),
            stream: true,
            system: systemPrompt,
            messages: messages.map((m) => ({ role: m.role, content: m.content })),
          }),
        });

        if (!response.ok) {
          const errorBody = await response.text();
          const errorEvent = `data: ${JSON.stringify({ type: "error", error: `Claude API ${response.status}: ${errorBody}` })}\n\n`;
          controller.enqueue(encoder.encode(errorEvent));
          controller.close();
          return;
        }

        const reader = response.body!.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            const payload = line.substring(6).trim();
            if (payload === "[DONE]") continue;

            try {
              const event = JSON.parse(payload);

              if (event.type === "content_block_delta" && event.delta?.type === "text_delta") {
                const deltaEvent = `data: ${JSON.stringify({ type: "delta", text: event.delta.text })}\n\n`;
                controller.enqueue(encoder.encode(deltaEvent));
              }

              if (event.type === "message_stop") {
                const doneEvent = `data: ${JSON.stringify({ type: "done" })}\n\n`;
                controller.enqueue(encoder.encode(doneEvent));
              }
            } catch {
              // skip unparseable lines
            }
          }
        }

        // Ensure done event is sent
        const finalDone = `data: ${JSON.stringify({ type: "done" })}\n\n`;
        controller.enqueue(encoder.encode(finalDone));
        controller.close();
      } catch (err) {
        const errorEvent = `data: ${JSON.stringify({ type: "error", error: String(err) })}\n\n`;
        controller.enqueue(encoder.encode(errorEvent));
        controller.close();
      }
    },
  });
}
