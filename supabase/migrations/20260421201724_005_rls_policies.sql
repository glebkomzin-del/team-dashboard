
ALTER TABLE team_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
ALTER TABLE todos ENABLE ROW LEVEL SECURITY;
ALTER TABLE blockers ENABLE ROW LEVEL SECURITY;
ALTER TABLE open_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;

-- Read access for anon key (dashboard)
CREATE POLICY "anon_read" ON team_members FOR SELECT USING (true);
CREATE POLICY "anon_read" ON meetings FOR SELECT USING (true);
CREATE POLICY "anon_read" ON todos FOR SELECT USING (true);
CREATE POLICY "anon_read" ON blockers FOR SELECT USING (true);
CREATE POLICY "anon_read" ON open_items FOR SELECT USING (true);
CREATE POLICY "anon_read" ON activity_log FOR SELECT USING (true);

-- Write access for anon key (dashboard can write changes)
CREATE POLICY "anon_insert" ON todos FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_update" ON todos FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "anon_delete" ON todos FOR DELETE USING (true);

CREATE POLICY "anon_insert" ON blockers FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_update" ON blockers FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "anon_delete" ON blockers FOR DELETE USING (true);

CREATE POLICY "anon_insert" ON open_items FOR INSERT WITH CHECK (true);
CREATE POLICY "anon_update" ON open_items FOR UPDATE USING (true) WITH CHECK (true);
CREATE POLICY "anon_delete" ON open_items FOR DELETE USING (true);

CREATE POLICY "anon_insert" ON activity_log FOR INSERT WITH CHECK (true);

-- Full access for service_role (Make)
CREATE POLICY "service_all" ON meetings FOR ALL USING (true) WITH CHECK (true);
;
