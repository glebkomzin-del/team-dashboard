
-- IVFFlat needs k-means clustering which exceeds 32MB maintenance_work_mem.
-- HNSW builds incrementally without batch memory spikes.
DROP INDEX IF EXISTS idx_transcript_chunks_vector;
CREATE INDEX idx_transcript_chunks_vector
ON transcript_chunks USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
;
