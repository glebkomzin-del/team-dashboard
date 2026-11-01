CREATE OR REPLACE FUNCTION public.match_embeddings(
  query_embedding vector,
  match_threshold double precision,
  match_count integer,
  filter_entity_type text DEFAULT NULL
)
RETURNS TABLE(id uuid, entity_type text, entity_id uuid, content text, metadata jsonb, similarity double precision)
LANGUAGE plpgsql
AS $function$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.entity_type,
    e.entity_id,
    e.content,
    e.metadata,
    (1 - (e.embedding <=> query_embedding))::float AS similarity
  FROM public.embeddings e
  WHERE
    1 - (e.embedding <=> query_embedding) > match_threshold
    AND (filter_entity_type IS NULL OR e.entity_type = filter_entity_type)
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$function$;;
