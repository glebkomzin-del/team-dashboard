-- Idempotent HNSW write batches can exceed the inherited 8s REST timeout.
-- Scope the exemption to this RPC, below the gateway's 25s request limit.
alter function public.wm_search_put(uuid, jsonb)
  set statement_timeout = '20s';

notify pgrst, 'reload schema';
