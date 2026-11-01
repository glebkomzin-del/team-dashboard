
CREATE TABLE inbox_items (
  id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text        NOT NULL CHECK (entity_type IN ('todo','blocker','open_item','meeting','decision')),
  payload     jsonb       NOT NULL DEFAULT '{}',
  source      text        NOT NULL DEFAULT 'make',
  status      text        NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
  created_at  timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE inbox_items ENABLE ROW LEVEL SECURITY;
CREATE POLICY "inbox_public" ON inbox_items USING (true) WITH CHECK (true);
;
