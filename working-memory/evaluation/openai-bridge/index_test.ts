import { handle } from './index.ts';
const env = (name: string) => ({ INTERNAL_FUNCTION_SECRET: 'test-auth', OPENAI_API_KEY: 'test-private' })[name];
const date = Date.parse('2026-09-06T00:00:00Z');
const req = (body: unknown, auth = 'test-auth') => new Request('http://localhost', {
  method: 'POST', headers: { 'x-internal-secret': auth }, body: JSON.stringify(body),
});
Deno.test('rejects unauthorized callers before any upstream request', async () => {
  const response = await handle(req({ operation: 'models' }, 'wrong'), env, () => { throw new Error('must not call'); }, date);
  if (response.status !== 401) throw new Error('auth failed');
});
Deno.test('expires automatically', async () => {
  const response = await handle(req({ operation: 'models' }), env, fetch, date + 3 * 86400000);
  if (response.status !== 410) throw new Error('expiry failed');
});
Deno.test('uses existing key without returning it; only allowlisted endpoint', async () => {
  const response = await handle(req({ operation: 'models' }), env, async (url, options) => {
    if (url !== 'https://api.openai.com/v1/models' || ((options as {headers: Record<string,string>}).headers).Authorization !== 'Bearer test-private') throw new Error('wrong request');
    return new Response(JSON.stringify({ data: [{ id: 'example-model' }] }));
  }, date);
  const body = await response.text();
  if (body.includes('test-private') || !body.includes('example-model')) throw new Error('unsafe output');
});
Deno.test('redacts upstream error messages', async () => {
  const response = await handle(req({ operation: 'models' }), env, async () => new Response(JSON.stringify({error:{message:'secret test-private',code:'invalid_api_key'}}),{status:401}), date);
  if ((await response.text()).includes('test-private')) throw new Error('leaked secret');
});
Deno.test('rejects arbitrary models and prompts beyond budget', async () => {
  for (const body of [{ model: 'arbitrary', prompt: 'x', schema: {} }, {model:'gpt-5.6-luna',prompt:'x'.repeat(140001),schema:{}}]) {
    const response = await handle(req(body), env, () => {throw new Error('must not call');}, date);
    if (response.status !== 400) throw new Error('missing input check');
  }
});
