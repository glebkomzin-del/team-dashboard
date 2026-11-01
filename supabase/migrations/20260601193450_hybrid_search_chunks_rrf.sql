CREATE OR REPLACE FUNCTION hybrid_search_chunks(
  query_text       text,
  query_embedding  vector(1536),
  match_count      int  DEFAULT 20,
  rrf_k            int  DEFAULT 50,
  candidate_n      int  DEFAULT 80
)
RETURNS TABLE (
  chunk_id     uuid,
  meeting_id   uuid,
  content      text,
  speaker      text,
  fused_score  double precision,
  fts_rank     int,
  vec_rank     int
)
LANGUAGE sql STABLE AS $$
WITH fts AS (
  SELECT tc.id,
         row_number() OVER (
           ORDER BY ts_rank_cd(tc.content_tsv,
                    websearch_to_tsquery('german', query_text)) DESC
         )::int AS rnk
  FROM transcript_chunks tc
  WHERE tc.content_tsv @@ websearch_to_tsquery('german', query_text)
  LIMIT candidate_n
),
vec AS (
  SELECT id, row_number() OVER (ORDER BY dist)::int AS rnk
  FROM (
    SELECT tc.id, tc.embedding <=> query_embedding AS dist
    FROM transcript_chunks tc
    WHERE tc.embedding IS NOT NULL
    ORDER BY tc.embedding <=> query_embedding
    LIMIT candidate_n
  ) v
),
fused AS (
  SELECT COALESCE(fts.id, vec.id) AS id,
         COALESCE(1.0 / (rrf_k + fts.rnk), 0) +
         COALESCE(1.0 / (rrf_k + vec.rnk), 0) AS score,
         fts.rnk AS fts_rank,
         vec.rnk AS vec_rank
  FROM fts FULL OUTER JOIN vec ON fts.id = vec.id
)
SELECT f.id, tc.meeting_id, tc.content, tc.speaker,
       f.score, f.fts_rank, f.vec_rank
FROM fused f
JOIN transcript_chunks tc ON tc.id = f.id
ORDER BY f.score DESC
LIMIT match_count;
$$;;
