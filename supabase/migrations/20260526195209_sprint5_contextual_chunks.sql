
ALTER TABLE public.transcript_chunks 
ADD COLUMN IF NOT EXISTS contextual_content text,
ADD COLUMN IF NOT EXISTS context_embedded_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_transcript_chunks_context_embedded 
ON transcript_chunks(context_embedded_at) 
WHERE context_embedded_at IS NULL;
;
