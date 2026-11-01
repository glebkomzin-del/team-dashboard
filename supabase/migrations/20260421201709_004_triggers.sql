
-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_todos_updated BEFORE UPDATE ON todos
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_blockers_updated BEFORE UPDATE ON blockers
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_open_items_updated BEFORE UPDATE ON open_items
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auto-log status changes
CREATE OR REPLACE FUNCTION log_status_change()
RETURNS TRIGGER AS $$
DECLARE
  etype TEXT;
BEGIN
  IF TG_TABLE_NAME = 'todos' THEN etype := 'todo';
  ELSIF TG_TABLE_NAME = 'blockers' THEN etype := 'blocker';
  ELSIF TG_TABLE_NAME = 'open_items' THEN etype := 'open_item';
  END IF;
  IF OLD.status IS DISTINCT FROM NEW.status THEN
    INSERT INTO activity_log (entity_type, entity_id, action, field_changed, old_value, new_value)
    VALUES (etype, NEW.id, 'status_changed', 'status', OLD.status, NEW.status);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_todos_log AFTER UPDATE ON todos
  FOR EACH ROW EXECUTE FUNCTION log_status_change();
CREATE TRIGGER trg_blockers_log AFTER UPDATE ON blockers
  FOR EACH ROW EXECUTE FUNCTION log_status_change();
CREATE TRIGGER trg_open_items_log AFTER UPDATE ON open_items
  FOR EACH ROW EXECUTE FUNCTION log_status_change();

-- Auto-log creation
CREATE OR REPLACE FUNCTION log_creation()
RETURNS TRIGGER AS $$
DECLARE
  etype TEXT;
BEGIN
  IF TG_TABLE_NAME = 'todos' THEN etype := 'todo';
  ELSIF TG_TABLE_NAME = 'blockers' THEN etype := 'blocker';
  ELSIF TG_TABLE_NAME = 'open_items' THEN etype := 'open_item';
  ELSIF TG_TABLE_NAME = 'meetings' THEN etype := 'meeting';
  END IF;
  INSERT INTO activity_log (entity_type, entity_id, action, new_value)
  VALUES (etype, NEW.id, 'created', NEW.title);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_todos_created AFTER INSERT ON todos
  FOR EACH ROW EXECUTE FUNCTION log_creation();
CREATE TRIGGER trg_blockers_created AFTER INSERT ON blockers
  FOR EACH ROW EXECUTE FUNCTION log_creation();
CREATE TRIGGER trg_open_items_created AFTER INSERT ON open_items
  FOR EACH ROW EXECUTE FUNCTION log_creation();
CREATE TRIGGER trg_meetings_created AFTER INSERT ON meetings
  FOR EACH ROW EXECUTE FUNCTION log_creation();
;
