-- The indexed hybrid search can exceed PostgREST's inherited 8s limit.
-- Keep this exemption scoped to this RPC and below the gateway's 25s timeout.
-- PostgREST hoists the function setting before executing the request.
alter function public.wm_search_query(uuid, text, text, extensions.vector, text[], integer)
  set statement_timeout = '20s';

notify pgrst, 'reload schema';
