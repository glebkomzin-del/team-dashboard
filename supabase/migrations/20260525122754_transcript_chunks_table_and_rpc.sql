CREATE TABLE public.transcript_chunks (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  meeting_id uuid NOT NULL REFERENCES public.meetings(id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  speaker text,
  content text NOT NULL,
  embedding vector(1536),
  token_count integer,
  created_at timestamptz DEFAULT now(),
  UNIQUE(meeting_id, chunk_index)
);

CREATE INDEX idx_transcript_chunks_meeting ON public.transcript_chunks(meeting_id);
CREATE INDEX idx_transcript_chunks_vector
  ON public.transcript_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
ALTER TABLE public.transcript_chunks ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION match_transcript_chunks(
  query_embedding vector,
  match_threshold float DEFAULT 0.6,
  match_count int DEFAULT 5,
  filter_meeting_id uuid DEFAULT NULL
)
RETURNS TABLE(id uuid, meeting_id uuid, chunk_index int, speaker text, content text, similarity float)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT c.id, c.meeting_id, c.chunk_index, c.speaker, c.content,
    (1 - (c.embedding <=> query_embedding))::float AS similarity
  FROM public.transcript_chunks c
  WHERE 1 - (c.embedding <=> query_embedding) > match_threshold
    AND (filter_meeting_id IS NULL OR c.meeting_id = filter_meeting_id)
  ORDER BY c.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;;
