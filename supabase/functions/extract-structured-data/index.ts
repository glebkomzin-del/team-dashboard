import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY")!;
const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const INTERNAL_FUNCTION_SECRET = Deno.env.get("INTERNAL_FUNCTION_SECRET")!;

const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
};

const EXTRACTION_PROMPT = `Du analysierst ein Meeting-Transkript und extrahierst strukturierte Daten.

Extrahiere ALLE der folgenden drei Objekttypen:

**DECISIONS** – Explizit getroffene Entscheidungen (nicht Optionen, nicht Diskussionen)
- Kriterien: "wir haben entschieden", "wir machen X", "es wird Y", klare Festlegungen
- Confidence: high = explizit gesagt, medium = klar impliziert, low = interpretiert

**COMMITMENTS** – Konkrete Zusagen einer Person gegenüber einer anderen
- Kriterien: "ich mache X", "ich kümmere mich um Y bis Z", "wir liefern bis"
- person = wer hat die Zusage gemacht
- due_date = falls genannt, sonst null

**OPEN_LOOPS** – Ungeklärte Fragen, offene Punkte die keine Antwort bekommen haben
- Kriterien: Fragen ohne Antwort, "das klären wir noch", "muss geprüft werden"
- raised_by = wer hat die Frage gestellt
- assigned_to = wem wurde die Klärung übertragen (falls genannt)

Antworte NUR mit validem JSON, kein Markdown, keine Erklärungen:
{
  "decisions": [
    {
      "decision_text": "...",
      "speaker": "Name oder null",
      "confidence": "high|medium|low",
      "context": "1-2 Sätze Kontext warum diese Entscheidung getroffen wurde"
    }
  ],
  "commitments": [
    {
      "person": "...",
      "commitment_text": "...",
      "due_date": "YYYY-MM-DD oder Textbeschreibung oder null",
      "confidence": "high|medium|low"
    }
  ],
  "open_loops": [
    {
      "question_text": "...",
      "raised_by": "Name oder null",
      "assigned_to": "Name oder null"
    }
  ]
}`;

// deno-lint-ignore no-explicit-any
async function extractFromMeeting(meeting: any): Promise<{ decisions: number; commitments: number; open_loops: number } | { error: string }> {
  const content = [
    meeting.title ? `# Meeting: ${meeting.title}` : "",
    meeting.meeting_date ? `Datum: ${meeting.meeting_date}` : "",
    meeting.ai_summary ? `\n## Summary:\n${meeting.ai_summary}` : "",
    meeting.raw_transcript
      ? `\n## Transkript:\n${meeting.raw_transcript.slice(0, 12000)}`
      : "",
  ].filter(Boolean).join("\n");

  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": ANTHROPIC_API_KEY,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 2000,
      messages: [{ role: "user", content: `${EXTRACTION_PROMPT}\n\n${content}` }],
    }),
  });

  const llmData = await response.json();
  const rawText = llmData.content?.[0]?.text ?? "{}";

  let extracted: {
    decisions?: Array<{ decision_text: string; speaker?: string; confidence?: string; context?: string }>;
    commitments?: Array<{ person: string; commitment_text: string; due_date?: string; confidence?: string }>;
    open_loops?: Array<{ question_text: string; raised_by?: string; assigned_to?: string }>;
  };
  try {
    extracted = JSON.parse(rawText.replace(/```json|```/g, "").trim());
  } catch {
    return { error: `JSON parse failed: ${rawText.slice(0, 200)}` };
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  // decisions: title = decision_text (NOT NULL), description = context
  if (extracted.decisions && extracted.decisions.length > 0) {
    const rows = extracted.decisions.map((d) => ({
      meeting_id: meeting.id,
      title: d.decision_text,          // maps to existing NOT NULL column
      description: d.context ?? null,  // context goes into existing description column
      speaker: d.speaker ?? null,
      decided_by: d.speaker ?? null,   // populate legacy field too
      confidence: d.confidence ?? "medium",
      decision_date: meeting.meeting_date ?? null,
      context: d.context ?? null,
    }));
    await supabase.from("decisions").insert(rows);
  }

  if (extracted.commitments && extracted.commitments.length > 0) {
    const rows = extracted.commitments.map((c) => ({
      meeting_id: meeting.id,
      person: c.person,
      commitment_text: c.commitment_text,
      due_date: c.due_date ?? null,
      confidence: c.confidence ?? "medium",
    }));
    await supabase.from("commitments").insert(rows);
  }

  if (extracted.open_loops && extracted.open_loops.length > 0) {
    const rows = extracted.open_loops.map((l) => ({
      meeting_id: meeting.id,
      question_text: l.question_text,
      raised_by: l.raised_by ?? null,
      assigned_to: l.assigned_to ?? null,
    }));
    await supabase.from("open_loops").insert(rows);
  }

  return {
    decisions: extracted.decisions?.length ?? 0,
    commitments: extracted.commitments?.length ?? 0,
    open_loops: extracted.open_loops?.length ?? 0,
  };
}

async function detectResolutionsAfterExtraction(meetingId: string) {
  // Reihenfolge bewusst inline nach der Extraktion: Der Dubletten-Check braucht
  // bereits angelegte pending Inbox-Items dieses Meetings und soll nicht gegen
  // einen parallelen pg_net-Trigger racen. Fehler blockieren die Extraktion nicht.
  try {
    const res = await fetch(`${SUPABASE_URL}/functions/v1/detect-resolutions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-secret": INTERNAL_FUNCTION_SECRET,
      },
      body: JSON.stringify({ meeting_id: meetingId }),
    });
    if (!res.ok) console.error("detect-resolutions failed", await res.text());
  } catch (error) {
    console.error("detect-resolutions call failed", error);
  }
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS_HEADERS });
  if (!INTERNAL_FUNCTION_SECRET || req.headers.get("x-internal-secret") !== INTERNAL_FUNCTION_SECRET) {
    return new Response(JSON.stringify({ error: "Unauthorized" }), { status: 401, headers: { ...CORS_HEADERS, "Content-Type": "application/json" } });
  }

  try {
    const { meeting_id, backfill_all } = await req.json();
    const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

    // deno-lint-ignore no-explicit-any
    let meetings: any[];
    if (backfill_all) {
      const { data } = await supabase
        .from("meetings")
        .select("id, title, meeting_date, raw_transcript, ai_summary")
        .order("meeting_date", { ascending: false });
      meetings = data ?? [];
    } else {
      const { data } = await supabase
        .from("meetings")
        .select("id, title, meeting_date, raw_transcript, ai_summary")
        .eq("id", meeting_id)
        .single();
      meetings = data ? [data] : [];
    }

    const results = [];

    // Bulk-check which meetings already have extracted decisions (to make backfill idempotent)
    let alreadyProcessed = new Set<string>();
    if (backfill_all && meetings.length > 0) {
      const meetingIds = meetings.map((m) => m.id);
      const { data: existing } = await supabase
        .from("decisions")
        .select("meeting_id")
        .in("meeting_id", meetingIds);
      alreadyProcessed = new Set((existing ?? []).map((r: { meeting_id: string }) => r.meeting_id));
    }

    for (const meeting of meetings) {
      if (!meeting?.raw_transcript && !meeting?.ai_summary) {
        results.push({ meeting_id: meeting.id, skipped: true, reason: "no content" });
        continue;
      }

      if (backfill_all && alreadyProcessed.has(meeting.id)) {
        results.push({ meeting_id: meeting.id, skipped: true, reason: "already processed" });
        continue;
      }

      const result = await extractFromMeeting(meeting);
      await detectResolutionsAfterExtraction(meeting.id);
      results.push({ meeting_id: meeting.id, title: meeting.title, ...result });

      if (backfill_all) await new Promise((r) => setTimeout(r, 500));
    }

    return new Response(JSON.stringify({ success: true, results }), {
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { ...CORS_HEADERS, "Content-Type": "application/json" },
    });
  }
});
