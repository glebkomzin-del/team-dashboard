
-- Trigger function: fires ingest-transcript edge function after meeting INSERT
CREATE OR REPLACE FUNCTION trigger_ingest_transcript()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  _url text := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/ingest-transcript';
  _anon_key text := 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM';
BEGIN
  -- Only fire when a transcript source is actually present
  IF NEW.raw_transcript IS NOT NULL OR NEW.source_file IS NOT NULL THEN
    PERFORM net.http_post(
      url := _url,
      headers := jsonb_build_object(
        'Content-Type', 'application/json',
        'Authorization', 'Bearer ' || _anon_key
      ),
      body := jsonb_build_object(
        'meeting_id', NEW.id::text,
        'source_file', NEW.source_file
      )
    );
  END IF;
  RETURN NEW;
END;
$$;

-- Drop if already exists (idempotent)
DROP TRIGGER IF EXISTS on_meeting_created_ingest_transcript ON public.meetings;

CREATE TRIGGER on_meeting_created_ingest_transcript
  AFTER INSERT ON public.meetings
  FOR EACH ROW
  EXECUTE FUNCTION trigger_ingest_transcript();
;
