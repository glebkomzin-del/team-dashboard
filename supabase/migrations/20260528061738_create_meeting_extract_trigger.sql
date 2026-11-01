-- Trigger function: ruft extract-structured-data nach jedem neuen Meeting auf
CREATE OR REPLACE FUNCTION public.trigger_extract_structured_data()
RETURNS trigger AS $$
BEGIN
  PERFORM net.http_post(
    url     := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/extract-structured-data',
    body    := jsonb_build_object('meeting_id', NEW.id),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM'
    )
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: feuert nach INSERT auf meetings
DROP TRIGGER IF EXISTS on_meeting_insert_extract ON public.meetings;
CREATE TRIGGER on_meeting_insert_extract
  AFTER INSERT ON public.meetings
  FOR EACH ROW
  EXECUTE FUNCTION public.trigger_extract_structured_data();;
