-- memory_metrics erweitern für Token-/Kostentracking
-- Die Tabelle existiert bereits (von der ask-memory Edge Function angelegt/beschrieben),
-- hat aber keinen versionskontrollierten DDL und nur Input-/Cache-Token-Spalten.

ALTER TABLE public.memory_metrics
  ADD COLUMN IF NOT EXISTS output_tokens INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS uncached_input_tokens INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS model TEXT,
  ADD COLUMN IF NOT EXISTS cost_usd NUMERIC(10, 6) DEFAULT 0;

-- created_at Spalte, falls noch nicht vorhanden (für Monats-Filterung).
-- Nimmt an, dass die Tabelle über DEFAULT now() verfügt; falls fehlt, nachträglich anlegen.
ALTER TABLE public.memory_metrics
  ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT now();

-- Index für die Monats-Filterung (Frontend liest nach created_at).
CREATE INDEX IF NOT EXISTS idx_memory_metrics_created_at
  ON public.memory_metrics (created_at DESC);

-- Lesender Zugriff für das Frontend (anon-key). Schreiben erfolgt über service_role.
-- WICHTIG: Die Tabelle wurde von der Edge Function (service_role) angelegt und hatte
-- daher nur service_role/postgres-Privilegien. GRANT ist erforderlich — die RLS-Policy
-- allein reicht nicht (RLS filtert nur Zeilen, das Table-Privileg muss separat stehen).
GRANT SELECT ON public.memory_metrics TO anon, authenticated;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'memory_metrics' AND policyname = 'anon_read'
  ) THEN
    ALTER TABLE public.memory_metrics ENABLE ROW LEVEL SECURITY;
    CREATE POLICY "anon_read" ON public.memory_metrics FOR SELECT USING (true);
  END IF;
END $$;
