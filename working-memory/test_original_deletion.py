import copy
import unittest

from memory import ValidationError, fingerprint
from journal_projection import digest
from original_deletion import (
    REQUIRED_SCOPES, deletion_label, find_plaintext_leaks,
    plaintext_canaries, prepare_redacted_entry, verify_redacted_entry,
    sanitize_json_receipt,
    prepare_sanitization_plan,
)


DELETION_ID = '11111111-1111-4111-8111-111111111111'
PREPARED_AT = '2026-09-19T12:00:00+00:00'


def fixture(transcript='Intro. Nina übernimmt den Export bis Freitag. Ende.'):
    quote = 'Nina übernimmt den Export bis Freitag.'
    content_hash = fingerprint(transcript)
    source_id = 'drive:original-delete-fixture'
    proposal = {'observations': [{
        'kind': 'commitment', 'title': 'Export liefern', 'claim': 'Nina liefert den Export.',
        'matter': 'Export', 'owner': 'Nina', 'uncertainty': None,
        'action_uncertainty': None, 'condition_text': None, 'matter_id': None,
        'update_target': None, 'update': 'none', 'required_review': False,
        'quotes': [quote], 'source_spans': [{
            'start': transcript.index(quote), 'end': transcript.index(quote) + len(quote), 'quote': quote,
        }], 'due_text': 'bis Freitag', 'work_state': 'open',
        'commitment_strength': 'explicit',
    }], 'coverage_notes': ['May contain broad derived prose that is not needed for replay.']}
    payload = {
        'format': 'wm-source-batch-v1', 'pipeline': 'fixture-v1', 'model': 'fixture',
        'proposal': proposal, 'provenance': {'raw_excerpt': transcript}, 'usage': {'tokens': 1},
        'archive_note': {'legacy_record': {'raw_transcript': transcript}},
        'result_sha256': 'a' * 64, 'human_guard': 'field-v1',
    }
    source = {
        'id': fingerprint(source_id + ':' + content_hash), 'source_id': source_id,
        'content_hash': content_hash, 'event_date': '2026-09-19', 'title': 'Fixture',
        'transcript': transcript, 'observed_at': '2026-09-19T10:00:00+00:00',
    }
    return {'kind': 'source', 'source': source, 'payload': payload}


class OriginalDeletionTest(unittest.TestCase):
    def test_prepares_attested_manifest_without_full_original_or_auxiliary_copies(self):
        entry = fixture()
        package = prepare_redacted_entry(entry, deletion_id=DELETION_ID, prepared_at=PREPARED_AT)
        self.assertNotIn('transcript', package['source'])
        self.assertNotIn('provenance', package['retained_payload'])
        self.assertNotIn('archive_note', package['retained_payload'])
        self.assertEqual(package['retained_payload']['proposal']['coverage_notes'], [])
        self.assertEqual(package['attestation']['accepted_payload_sha256'], digest(entry['payload']))
        self.assertEqual(verify_redacted_entry(package)['source_id'], entry['source']['source_id'])
        quote = entry['payload']['proposal']['observations'][0]['quotes'][0]
        self.assertEqual(package['evidence_manifest']['entries'][0]['quote'], quote)

    def test_tampering_with_quote_or_identity_fails_without_original(self):
        package = prepare_redacted_entry(fixture(), deletion_id=DELETION_ID, prepared_at=PREPARED_AT)
        changed = copy.deepcopy(package)
        changed['evidence_manifest']['entries'][0]['quote'] += 'x'
        changed['evidence_manifest']['sha256'] = digest({k: v for k, v in changed['evidence_manifest'].items() if k != 'sha256'})
        changed['package_sha256'] = digest({k: v for k, v in changed.items() if k != 'package_sha256'})
        with self.assertRaisesRegex(ValidationError, 'quote checksum'):
            verify_redacted_entry(changed)
        changed = copy.deepcopy(package)
        changed['source']['source_id'] = 'drive:different'
        changed['package_sha256'] = digest({k: v for k, v in changed.items() if k != 'package_sha256'})
        with self.assertRaisesRegex(ValidationError, 'identity checksum'):
            verify_redacted_entry(changed)

    def test_manifest_rejects_quote_or_span_not_present_in_original(self):
        entry = fixture()
        entry['payload']['proposal']['observations'][0]['source_spans'][0]['start'] = 0
        with self.assertRaisesRegex(ValidationError, 'differs from the original'):
            prepare_redacted_entry(entry, deletion_id=DELETION_ID, prepared_at=PREPARED_AT)

    def test_leak_scan_reports_paths_without_repeating_plaintext(self):
        transcript = fixture()['source']['transcript']
        canaries = plaintext_canaries(transcript, window=16, step=4)
        value = {'safe': 'unrelated', 'nested': [{'copied_original': transcript}]}
        self.assertEqual(find_plaintext_leaks(value, canaries), ['$.nested.0.copied_original'])
        quote = 'Nina übernimmt den Export bis Freitag.'
        self.assertEqual(find_plaintext_leaks({'quote': quote}, canaries, allowed_quotes=(quote,)), [])

    def test_ui_label_requires_every_scope_and_discloses_full_quote_coverage(self):
        package = prepare_redacted_entry(fixture(), deletion_id=DELETION_ID, prepared_at=PREPARED_AT)
        self.assertEqual(deletion_label(package, REQUIRED_SCOPES[:-1]), 'Löschung läuft')
        self.assertEqual(deletion_label(package, REQUIRED_SCOPES), 'Original gelöscht; Belegzitate bleiben erhalten')
        whole = fixture('Nina übernimmt den Export bis Freitag.')
        package = prepare_redacted_entry(whole, deletion_id=DELETION_ID, prepared_at=PREPARED_AT)
        self.assertIn('vollständiger Wortlaut', deletion_label(package, REQUIRED_SCOPES))

    def test_receipt_sanitizer_keeps_unrelated_question_and_answer(self):
        transcript = 'Nina beschreibt die vertrauliche Exportplanung für Freitag ausführlich.'
        raw = __import__('json').dumps({
            'question': 'Welche Aufgabe ist noch offen?',
            'context': 'Beleg: ' + transcript,
            'answer': 'Der Export bleibt offen. ' + transcript,
            'unrelated': 'Diese eigenständige Antwort bleibt erhalten.',
        })
        sanitized, receipt = sanitize_json_receipt(raw, transcript, minimum_match=24)
        value = __import__('json').loads(sanitized)
        self.assertEqual(value['question'], 'Welche Aufgabe ist noch offen?')
        self.assertEqual(value['unrelated'], 'Diese eigenständige Antwort bleibt erhalten.')
        self.assertNotIn(transcript, sanitized)
        self.assertGreater(receipt['removed_characters'], 0)

    def test_receipt_sanitizer_catches_passage_copies_in_later_context(self):
        transcript = 'Alpha private planning sentence. Beta private planning sentence. Gamma.'
        later = __import__('json').dumps({'prompt': 'Earlier context: Beta private planning sentence. Next meeting.'})
        sanitized, receipt = sanitize_json_receipt(later, transcript, minimum_match=20)
        self.assertNotIn('Beta private planning sentence.', sanitized)
        self.assertTrue(receipt['changed'])

    def test_plan_binds_selective_replacement_to_server_before_hash(self):
        transcript='Private source sentence that must leave every technical receipt.'
        candidate={'scope':'model_call','record_key':'a'*64+':0','before_hash':'b'*64,
                   'data':{'request_json':'{"context":"'+transcript+'","question":"Keep me"}',
                           'response_json':'{"answer":"Independent answer"}'}}
        plan=prepare_sanitization_plan(candidate,transcript,minimum_match=24)
        self.assertEqual(plan['before_hash'],'b'*64)
        self.assertEqual(__import__('json').loads(plan['replacement']['request_json'])['question'],'Keep me')
        self.assertEqual(__import__('json').loads(plan['replacement']['response_json'])['answer'],'Independent answer')
        self.assertNotIn(transcript,str(plan['replacement']))


if __name__ == '__main__':
    unittest.main()
