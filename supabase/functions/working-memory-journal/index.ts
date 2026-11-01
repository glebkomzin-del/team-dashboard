import { handler } from './handler.ts'
const url = Deno.env.get('SUPABASE_URL') || ''
const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') || JSON.parse(Deno.env.get('SUPABASE_SECRET_KEYS') || '{}').default || ''
Deno.serve(handler({ url, key }))
