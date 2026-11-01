
CREATE OR REPLACE FUNCTION get_member_id_by_name(member_name TEXT)
RETURNS UUID AS $$
  SELECT id FROM team_members WHERE name = member_name LIMIT 1;
$$ LANGUAGE sql;
;
