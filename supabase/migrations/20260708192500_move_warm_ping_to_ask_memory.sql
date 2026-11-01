-- Cache-Warmhalter von der geloeschten Legacy-Funktion semantic-search auf
-- ask-memory umziehen. ask-memory beantwortet {"question":"ping"} mit einem
-- Guard vor DB-/Anthropic-Zugriff (haelt nur die Edge-Instanz warm).
-- Bereits am 2026-07-08 direkt auf dem Projekt ausgefuehrt; idempotent gehalten.

select cron.unschedule(jobid)
from cron.job
where jobname in ('keep-semantic-search-warm', 'keep-ask-memory-warm');

select cron.schedule(
  'keep-ask-memory-warm',
  '*/4 * * * *',
  $cron$
  SELECT net.http_post(
    url := 'https://lghwikeotbkmojyyjglz.supabase.co/functions/v1/ask-memory',
    body := '{"question":"ping"}'::jsonb,
    headers := '{
      "Content-Type": "application/json",
      "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxnaHdpa2VvdGJrbW9qeXlqZ2x6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY2OTUyNDMsImV4cCI6MjA5MjI3MTI0M30.pyWWro6BNGf_BeBNi3W-IgrTPGOVZymAjemO-ZVO8TM"
    }'::jsonb
  );
  $cron$
);
