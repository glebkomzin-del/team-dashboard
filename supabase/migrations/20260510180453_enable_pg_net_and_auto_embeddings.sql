
-- Enable pg_net for HTTP calls from triggers
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

-- Function that calls the generate-embedding Edge Function automatically
CREATE OR REPLACE FUNCTION public.trigger_generate_embedding()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  _entity_type TEXT;
  _action TEXT;
  _service_key TEXT := current_setting('app.settings.service_role_key', true);
BEGIN
  -- Determine entity type from table name
  IF TG_TABLE_NAME = 'todos' THEN _entity_type := 'todo';
  ELSIF TG_TABLE_NAME = 'blockers' THEN _entity_type := 'blocker';
  ELSIF TG_TABLE_NAME = 'open_items' THEN _entity_type := 'open_item';
  ELSIF TG_TABLE_NAME = 'meetings' THEN _entity_type := 'meeting';
  ELSIF TG_TABLE_NAME = 'decisions' THEN _entity_type := 'decision';
  ELSIF TG_TABLE_NAME = 'projects' THEN _entity_type := 'project';
  END IF;

  IF TG_OP = 'DELETE' THEN
    _action := 'deleted';
    PERFORM net.http_post(
      url := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/generate-embedding',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || _service_key
      ),
      body := jsonb_build_object('entity_type', _entity_type, 'entity_id', OLD.id, 'action', 'deleted')
    );
    RETURN OLD;
  ELSE
    _action := CASE WHEN TG_OP = 'INSERT' THEN 'created' ELSE 'updated' END;
    PERFORM net.http_post(
      url := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/generate-embedding',
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || _service_key
      ),
      body := jsonb_build_object('entity_type', _entity_type, 'entity_id', NEW.id, 'action', _action)
    );
    RETURN NEW;
  END IF;
END;
$$;

-- Attach triggers to all entity tables
CREATE TRIGGER trg_todos_embedding
  AFTER INSERT OR UPDATE OR DELETE ON public.todos
  FOR EACH ROW EXECUTE FUNCTION public.trigger_generate_embedding();

CREATE TRIGGER trg_blockers_embedding
  AFTER INSERT OR UPDATE OR DELETE ON public.blockers
  FOR EACH ROW EXECUTE FUNCTION public.trigger_generate_embedding();

CREATE TRIGGER trg_open_items_embedding
  AFTER INSERT OR UPDATE OR DELETE ON public.open_items
  FOR EACH ROW EXECUTE FUNCTION public.trigger_generate_embedding();

CREATE TRIGGER trg_meetings_embedding
  AFTER INSERT OR UPDATE OR DELETE ON public.meetings
  FOR EACH ROW EXECUTE FUNCTION public.trigger_generate_embedding();

CREATE TRIGGER trg_decisions_embedding
  AFTER INSERT OR UPDATE OR DELETE ON public.decisions
  FOR EACH ROW EXECUTE FUNCTION public.trigger_generate_embedding();

CREATE TRIGGER trg_projects_embedding
  AFTER INSERT OR UPDATE OR DELETE ON public.projects
  FOR EACH ROW EXECUTE FUNCTION public.trigger_generate_embedding();
;
