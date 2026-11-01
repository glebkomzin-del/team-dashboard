
CREATE TABLE IF NOT EXISTS public.eval_questions (
  id serial PRIMARY KEY,
  question text NOT NULL,
  category text NOT NULL,
  expected_intent text,
  expected_source_ids text[],
  must_include text[],
  must_not_claim text[],
  notes text,
  created_at timestamp DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.eval_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_at timestamp DEFAULT now(),
  semantic_search_version int,
  questions_tested int,
  source_hit_rate float,
  intent_accuracy float,
  notes text
);

CREATE TABLE IF NOT EXISTS public.eval_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid REFERENCES eval_runs(id),
  question_id int REFERENCES eval_questions(id),
  actual_intent text,
  source_ids_returned text[],
  source_hit boolean,
  intent_correct boolean,
  must_include_hits text[],
  must_include_misses text[],
  answer_snippet text,
  latency_ms int,
  created_at timestamp DEFAULT now()
);
;
