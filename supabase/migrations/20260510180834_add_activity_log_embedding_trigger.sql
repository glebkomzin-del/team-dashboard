
-- Update constraint to allow activity_log as entity_type in embeddings
ALTER TABLE public.embeddings DROP CONSTRAINT IF EXISTS embeddings_entity_type_check;
ALTER TABLE public.embeddings ADD CONSTRAINT embeddings_entity_type_check 
  CHECK (entity_type IN ('todo', 'blocker', 'open_item', 'meeting', 'decision', 'project', 'activity'));

-- Trigger for activity_log
CREATE OR REPLACE FUNCTION public.trigger_activity_embedding()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  PERFORM net.http_post(
    url := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/generate-embedding',
    headers := '{"Content-Type": "application/json"}'::jsonb,
    body := jsonb_build_object('entity_type', 'activity', 'entity_id', NEW.id, 'action', 'INSERT')
  );
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_activity_log_embedding
  AFTER INSERT ON public.activity_log
  FOR EACH ROW EXECUTE FUNCTION public.trigger_activity_embedding();
;
