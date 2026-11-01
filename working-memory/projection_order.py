"""Comparable replay order for events stored in separate projection tables.

The canonical journal revision is implicit in replay call order.  This small
derived table preserves that order without changing any accepted journal
payload or result checksum.
"""

from memory import ValidationError


def setup(db):
    db.execute('''CREATE TABLE IF NOT EXISTS projection_event_order (
      sequence INTEGER PRIMARY KEY AUTOINCREMENT,
      event_type TEXT NOT NULL, event_id TEXT NOT NULL,
      UNIQUE(event_type,event_id))''')


def record(db, event_type, event_id):
    if event_type not in ('source', 'planning', 'human') or not isinstance(event_id, str) or not event_id:
        raise ValidationError('Invalid projection event identity')
    setup(db)
    db.execute('INSERT OR IGNORE INTO projection_event_order(event_type,event_id) VALUES (?,?)',
               (event_type,event_id))


def sequence(db, event_type, event_id):
    setup(db)
    row=db.execute('SELECT sequence FROM projection_event_order WHERE event_type=? AND event_id=?',
                   (event_type,event_id)).fetchone()
    if row is None:
        raise ValidationError('Projection event order is missing; rebuild the derived projection from the canonical journal')
    return row[0]
