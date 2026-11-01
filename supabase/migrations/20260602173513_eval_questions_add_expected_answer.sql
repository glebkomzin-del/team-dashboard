ALTER TABLE eval_questions ADD COLUMN IF NOT EXISTS expected_answer text;
ALTER TABLE eval_results  ADD COLUMN IF NOT EXISTS judge_score int;      -- 0..3 inhaltliche Korrektheit
ALTER TABLE eval_results  ADD COLUMN IF NOT EXISTS judge_reason text;    -- Begründung des Judge
ALTER TABLE eval_results  ADD COLUMN IF NOT EXISTS hallucination boolean;-- hat must_not_claim verletzt
ALTER TABLE eval_runs     ADD COLUMN IF NOT EXISTS avg_judge_score numeric;;
