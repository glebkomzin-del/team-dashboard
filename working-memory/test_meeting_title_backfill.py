import copy
import unittest

from archive_index import digest
from meeting_title_backfill import apply, current_documents, note_for, plan, validated_exception, validated_title
from memory import ValidationError


BODY = '''Meeting Titel: Gieselberg, Jan Philipp\nTeilnehmer: Gleb Komzin; Jan Philipp Gieselberg\nDatum: 18.09.2026\n[09:47:10] Jan Philipp Gieselberg: Wir müssen das Power BI Modell und RLS prüfen.\n'''


def document(identifier='a', observed='2026-09-18T10:30:00Z', title='Gieselberg, Jan Philipp'):
    return {'id': identifier * 64, 'source_id': 'teams:call-1', 'event_date': '2026-09-18',
            'observed_at': observed, 'title': title, 'body_hash': digest(BODY), 'body': BODY,
            'registered_revision': 1}


PROPOSAL = {'text': 'Power-BI-Modell und RLS prüfen', 'evidence_ids': ['U0004']}


class Store:
    def __init__(self, rows, notes=None):
        self.rows = rows
        self.notes = notes or []
        self.revision = len(rows)
        self.writes = []
    def space(self):
        return {'archive_revision': self.revision}
    def archive_rows(self, kind, *, through):
        self.asserted = (kind, through)
        return iter(copy.deepcopy(self.rows if kind == 'documents' else self.notes))
    def archive_note_put(self, note):
        self.writes.append(note)
        return {'id': note['id'], 'repeated': False}


class MeetingTitleBackfillTests(unittest.TestCase):
    def test_latest_inventory_uses_only_one_envelope_per_source(self):
        old = document('a', '2026-09-18T10:00:00Z')
        new = document('b', '2026-09-18T11:00:00Z'); new['registered_revision'] = 2
        revision, rows = current_documents(Store([old, new]))
        self.assertEqual(revision, 2)
        self.assertEqual([row['id'] for row in rows], [new['id']])
        self.assertEqual(set(rows[0]), {'id','source_id','event_date','observed_at','title','body_hash','body'})

    def test_title_and_note_are_strictly_grounded_and_deterministic(self):
        doc = document()
        title = validated_title(doc, PROPOSAL)
        self.assertEqual(title['passages'], ['[09:47:10] Jan Philipp Gieselberg: Wir müssen das Power BI Modell und RLS prüfen.'])
        first = note_for(doc, PROPOSAL); second = note_for(doc, PROPOSAL)
        self.assertEqual(first, second)
        self.assertEqual(first['document_id'], doc['id'])
        self.assertEqual(first['origin'], 'source_summary')
        self.assertNotIn(doc['source_id'], first['id'])

    def test_invented_title_clear_source_and_changed_body_are_rejected(self):
        with self.assertRaises(ValidationError):
            validated_title(document(), {'text':'SAP-Migration beschließen','evidence_ids':['U0004']})
        with self.assertRaises(ValidationError):
            validated_title(document(title='Power-BI-Modell und RLS'), PROPOSAL)
        changed = document(); changed['body'] += 'verändert'
        with self.assertRaises(ValidationError):
            validated_title(changed, PROPOSAL)

    def test_plan_requires_complete_review_and_apply_is_dry_by_default(self):
        doc = document(); store = Store([doc])
        incomplete = plan(store, {})
        self.assertEqual((incomplete['inventory_count'], incomplete['ambiguous_count']), (1, 1))
        with self.assertRaises(ValidationError): apply(store, incomplete)
        with self.assertRaises(ValidationError): apply(store, incomplete, commit=True)
        ready = plan(store, {doc['id']: PROPOSAL})
        self.assertEqual(apply(store, ready), {'dry_run':True,'planned':1,'written':0})
        self.assertEqual(store.writes, [])
        result = apply(store, ready, commit=True)
        self.assertEqual(result['written'], 1)
        self.assertEqual(store.writes[0], ready['notes'][0])

    def test_reviewed_short_no_topic_exception_completes_plan_without_write(self):
        body = 'Meeting Titel: Teams Meeting\nDatum: 2026-09-18\n[10:00:00] Unknown: Bild\n'
        doc = document(title='Teams Meeting'); doc['body'] = body; doc['body_hash'] = digest(body)
        proposal = {'exception':'no_transcribed_content','reason':'Nur ein Bildhinweis, kein Gesprächsinhalt.',
                    'evidence_ids':['U0003']}
        self.assertEqual(validated_exception(doc, proposal)['exception'], 'no_transcribed_content')
        store = Store([doc]); ready = plan(store, {doc['id']: proposal})
        self.assertEqual((ready['target_count'], len(ready['notes']), len(ready['exceptions'])), (1, 1, 1))
        self.assertEqual(apply(store, ready), {'dry_run':True,'planned':1,'written':0})
        payload = __import__('json').loads(ready['notes'][0]['note_json'])
        self.assertEqual(payload['display_title']['text'], 'Aufzeichnung ohne Gesprächsinhalt · 18.09.2026')

    def test_exception_is_blocked_for_substantive_transcript(self):
        proposal = {'exception':'no_transcribed_content','reason':'Kein Gesprächsinhalt.','evidence_ids':[]}
        doc = document(); doc['body'] += 'x' * 700; doc['body_hash'] = digest(doc['body'])
        with self.assertRaisesRegex(ValidationError, 'short unchanged'):
            validated_exception(doc, proposal)

    def test_archive_revision_change_blocks_commit(self):
        doc = document(); store = Store([doc]); ready = plan(store, {doc['id']: PROPOSAL})
        store.revision += 1
        with self.assertRaisesRegex(ValidationError, 'Archive changed'):
            apply(store, ready, commit=True)


if __name__ == '__main__':
    unittest.main()
