
-- Meeting-ID zum Activity Log hinzufügen
ALTER TABLE activity_log ADD COLUMN meeting_id UUID REFERENCES meetings(id) ON DELETE SET NULL;
CREATE INDEX idx_activity_log_meeting ON activity_log(meeting_id);

-- Trigger für Status-Änderungen: meeting_id mitschreiben
CREATE OR REPLACE FUNCTION log_status_change()
RETURNS TRIGGER AS $$
DECLARE
  etype TEXT;
  mid UUID;
BEGIN
  IF TG_TABLE_NAME = 'todos' THEN etype := 'todo'; mid := NEW.meeting_id;
  ELSIF TG_TABLE_NAME = 'blockers' THEN etype := 'blocker'; mid := NEW.meeting_id;
  ELSIF TG_TABLE_NAME = 'open_items' THEN etype := 'open_item'; mid := NEW.meeting_id;
  END IF;
  IF OLD.status IS DISTINCT FROM NEW.status THEN
    INSERT INTO activity_log (entity_type, entity_id, action, field_changed, old_value, new_value, meeting_id)
    VALUES (etype, NEW.id, 'status_changed', 'status', OLD.status, NEW.status, mid);
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger für Neuanlagen: meeting_id mitschreiben
CREATE OR REPLACE FUNCTION log_creation()
RETURNS TRIGGER AS $$
DECLARE
  etype TEXT;
  mid UUID;
BEGIN
  IF TG_TABLE_NAME = 'todos' THEN etype := 'todo'; mid := NEW.meeting_id;
  ELSIF TG_TABLE_NAME = 'blockers' THEN etype := 'blocker'; mid := NEW.meeting_id;
  ELSIF TG_TABLE_NAME = 'open_items' THEN etype := 'open_item'; mid := NEW.meeting_id;
  ELSIF TG_TABLE_NAME = 'meetings' THEN etype := 'meeting'; mid := NEW.id;
  END IF;
  INSERT INTO activity_log (entity_type, entity_id, action, new_value, meeting_id)
  VALUES (etype, NEW.id, 'created', NEW.title, mid);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
;
