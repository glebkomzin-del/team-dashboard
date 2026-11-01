// Temporary, isolated evaluation bridge. No database access or secret export.
// Existing imports and production functions do not call this endpoint.
const ALLOWED = new Set(['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-6-astra']);
const EXPIRES = Date.parse('2026-09-08T00:00:00Z');
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
});

export async function handle(req: Request, env = Deno.env.get, fetcher = fetch, now = Date.now()) {
  const secret = env('INTERNAL_FUNCTION_SECRET');
  if (!secret || req.headers.get('x-internal-secret') !== secret) return json({ error: 'Unauthorized' }, 401);
  if (now >= EXPIRES) return json({ error: 'Evaluation window expired' }, 410);
  if (req.method !== 'POST') return json({ error: 'POST required' }, 405);
  const key = env('OPENAI_API_KEY');
  if (!key) return json({ error: 'OPENAI_API_KEY unavailable' }, 503);
  try {
    const raw = await req.text();
    if (raw.length > 180_000) return json({ error: 'Input limit exceeded' }, 413);
    const body = JSON.parse(raw);
    if (body.operation === 'capabilities') return json({ openai: !!key,
      google_drive_service_account: !!env('GOOGLE_SERVICE_ACCOUNT_KEY') });
    let path: string;
    let payload: unknown;
    if (body.operation === 'models') {
      path = '/v1/models';
    } else {
      if (!ALLOWED.has(body.model) || typeof body.prompt !== 'string' || body.prompt.length > 140_000 ||
          !body.schema || typeof body.schema !== 'object') return json({ error: 'Invalid evaluation request' }, 400);
      path = '/v1/responses';
      payload = { model: body.model, input: body.prompt, store: false,
        max_output_tokens: 12000, reasoning: { effort: body.model === 'gpt-6-astra' ? 'low' : 'none' },
        text: { format: { type: 'json_schema', name: 'meeting_observations', strict: true, schema: body.schema } } };
    }
    const upstream = await fetcher('https://api.openai.com' + path, {
      method: payload ? 'POST' : 'GET',
      headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
      body: payload ? JSON.stringify(payload) : undefined,
      signal: AbortSignal.timeout(140_000),
    });
    const result = await upstream.json();
    // Never return upstream error messages, which can echo a credential fragment.
    if (!upstream.ok) return json({ error: 'OpenAI request failed', upstream_status: upstream.status,
      code: result.error?.code ?? null, type: result.error?.type ?? null }, 502);
    if (body.operation === 'models') return json({ models: result.data.map((m: { id: string }) => m.id).sort() });
    return json({ id: result.id, model: result.model, status: result.status, usage: result.usage,
      incomplete_details: result.incomplete_details, output: result.output });
  } catch (e) {
    return json({ error: e instanceof SyntaxError ? 'Invalid JSON' : 'Evaluation request failed' }, 502);
  }
}

if (import.meta.main) Deno.serve((req) => handle(req));
