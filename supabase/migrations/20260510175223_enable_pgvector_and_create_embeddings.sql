
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

-- Embeddings table: stores vector representations of all entities
CREATE TABLE IF NOT EXISTS public.embeddings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type TEXT NOT NULL CHECK (entity_type IN ('todo', 'blocker', 'open_item', 'meeting', 'decision', 'project')),
  entity_id UUID NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1536),
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(entity_type, entity_id)
);

-- Index for fast similarity search
CREATE INDEX IF NOT EXISTS idx_embeddings_vector ON public.embeddings
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Index for entity lookups
CREATE INDEX IF NOT EXISTS idx_embeddings_entity ON public.embeddings (entity_type, entity_id);

-- RLS
ALTER TABLE public.embeddings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can read embeddings"
  ON public.embeddings FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY "Service role can manage embeddings"
  ON public.embeddings FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Function for semantic search
CREATE OR REPLACE FUNCTION match_embeddings(
  query_embedding vector(1536),
  match_threshold FLOAT DEFAULT 0.7,
  match_count INT DEFAULT 10
)
RETURNS TABLE (
  id UUID,
  entity_type TEXT,
  entity_id UUID,
  content TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    e.id,
    e.entity_type,
    e.entity_id,
    e.content,
    1 - (e.embedding <=> query_embedding) AS similarity
  FROM public.embeddings e
  WHERE 1 - (e.embedding <=> query_embedding) > match_threshold
  ORDER BY e.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
;
