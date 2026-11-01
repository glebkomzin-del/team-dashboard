"""Offline contract tests: all contents and archives in this file are synthetic."""
import copy
import hashlib
import io
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import socket
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import handover
handover._backend()
from memory import connect, fingerprint
from journal_projection import prepare_source
from human_decisions import record


def observation(title, quote, **changes):
    value = dict(kind='commitment', title=title, claim=quote, matter='Atlas',
                 owner='Komzin, Gleb', due_text=None, uncertainty=None,
                 action_uncertainty=None, required_review=False, quotes=[quote],
                 commitment_strength='explicit', work_state='open',
                 update='none', update_target=None)
    value.update(changes)
    return value


def document(source_id, title, day, body):
    export = body
    metadata = dict(source_id=source_id, title=title, event_date=day,
                    body_sha256=fingerprint(body), export_sha256=fingerprint(export),
                    body_offset_characters=0)
    raw = json.dumps(metadata, ensure_ascii=False)
    return dict(id=fingerprint(source_id + ':' + raw), source_id=source_id,
                title=title, event_date=day, observed_at=day + 'T12:00:00Z',
                body=body, export=export, body_hash=fingerprint(body),
                export_hash=fingerprint(export), metadata_json=raw,
                registered_revision=1, space_id='synthetic-space')


def fixture_records(owner_change=False):
    """Make accepted batches with original backend checksums, no provider."""
    db = connect(':memory:')
    journal, docs = [], []
    def source(sid, day, text, observations):
        h = fingerprint(text)
        pinned = dict(id=fingerprint(sid + ':' + h), source_id=sid,
                      content_hash=h, event_date=day, title='Atlas Modellrunde',
                      transcript=text, observed_at=day + 'T12:00:00Z')
        payload = prepare_source(db, pinned,
                                 dict(observations=observations, coverage_notes=[]),
                                 pipeline='synthetic-v1', model='synthetic', provenance={})
        from journal_projection import apply_saved
        apply_saved(db, pinned, payload)
        journal.append(dict(kind='source', revision=len(journal) + 1,
                            source_version=pinned['id'], source=pinned, payload=payload))
        docs.append(document(sid, pinned['title'], day, text))
        return fingerprint(fingerprint(pinned['id'] + ':synthetic-v1') + ':observation:0')
    first = 'Gleb erstellt das Atlas Datenmodell. Ada hat die Atlas Vorlage erstellt.'
    wid = source('fixture:first', '2026-01-02', first,
                 [observation('Atlas Datenmodell erstellen', 'Gleb erstellt das Atlas Datenmodell.'),
                  observation('Atlas Vorlage erstellen', 'Ada hat die Atlas Vorlage erstellt.',
                              owner='Ada Beispiel', work_state='done',
                              state_quotes=['Ada hat die Atlas Vorlage erstellt.'])])
    followup = 'Ada übernimmt das Atlas Datenmodell.' if owner_change else 'Das Atlas Datenmodell ist in Arbeit.'
    source('fixture:followup', '2026-01-04', followup,
           [observation('Atlas Statusbericht', followup, owner='Ada Beispiel' if owner_change else None, kind='status',
                        commitment_strength='not_applicable', update='owner_changed' if owner_change else 'progress',
                        update_target=wid)])
    source('fixture:other', '2026-01-05', 'Ada schreibt die Orion E-Mail Antwort.',
           [observation('Orion E-Mail Antwort schreiben', 'Ada schreibt die Orion E-Mail Antwort.',
                        matter='Orion', owner='Ada Beispiel')])
    manual = '20000000-0000-4000-8000-000000000001'
    command = dict(action='create_task', target_id=manual, reason='Synthetische Planung',
                   event_date='2026-01-06', patch=dict(title='Atlas Measure prüfen',
                       owner='Komzin, Gleb', note='naechster: Atlas Measure öffnen\n'
                       'fertig_wenn: Prüfergebnis dokumentiert\nscope: Nur Atlas\n'
                       'abnahme: Ada prüft das Prüfergebnis'))
    cid = '20000000-0000-4000-8000-000000000002'
    aid = '20000000-0000-4000-8000-000000000003'
    record(db, command_id=cid, actor_id=aid, command=command)
    journal.append(dict(kind='human', revision=4, command_id=cid, actor_id=aid, payload=command))
    db.close()
    docs.insert(0, document('fixture:earlier', 'Atlas Vorgespräch', '2026-01-01',
                            'Das Atlas Datenmodell nutzt die vorhandene Atlas Vorlage.'))
    docs.append(document('fixture:unrelated', 'Orion Reise', '2025-12-31',
                         'Ada Beispiel plant die Orion Reise.'))
    docs.append(document('fixture:future', 'Atlas Zukunft', '2027-01-01',
                         'Das Atlas Datenmodell wird später erweitert.'))
    for index, doc in enumerate(docs, 1):
        doc['registered_revision'] = index
    raw = json.dumps({'legacy_record': {'title': 'Atlas Notiz',
                                       'payload': {'topics': ['Atlas'],
                                                   'summary': 'Atlas Vorlage ist vorhanden.'}}})
    origin, origin_id = 'legacy_meetings', 'fixture:note'
    note = dict(document_id=docs[0]['id'], origin=origin, origin_id=origin_id,
                note_json=raw, note_hash=fingerprint(raw), registered_revision=20)
    note['id'] = fingerprint(':'.join([note['document_id'], origin, origin_id, note['note_hash']]))
    return journal, docs, [note], wid, manual


def mini_archive(path, records, wrapped=False):
    with tarfile.open(path, 'w:gz') as archive:
        for name, values in zip(('journal', 'documents', 'notes'), records[:3]):
            rows = []
            for i, value in enumerate(values, 1):
                if wrapped:
                    raw = json.dumps(value, ensure_ascii=False)
                    value = dict(kind=value.get('kind', name), sequence=i, record_json=raw,
                                 record_hash=fingerprint(raw))
                rows.append(json.dumps(value, ensure_ascii=False))
            data = ('\n'.join(rows) + '\n').encode('utf-8')
            info = tarfile.TarInfo('canonical/' + name + '.jsonl')
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


def assertions(value):
    if isinstance(value, dict):
        if value.get('reife') in ('belegt', 'Annahme', 'unbekannt') and 'wert' in value:
            yield value
        for child in value.values():
            yield from assertions(child)
    elif isinstance(value, list):
        for child in value:
            yield from assertions(child)


class HandoverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='.test-', dir=HERE)
        self.addCleanup(self.temp.cleanup)
        for name in ('socket.socket.connect', 'socket.socket.connect_ex',
                     'socket.create_connection', 'urllib.request.urlopen'):
            guard = patch(name, side_effect=AssertionError('Network forbidden in tests'))
            guard.start()
            self.addCleanup(guard.stop)
        self.records = fixture_records()
        self.path = Path(self.temp.name) / 'fixture.tar.gz'
        mini_archive(self.path, self.records)

    def load(self, wrapped=False):
        if wrapped:
            mini_archive(self.path, self.records, wrapped=True)
        memory = handover.load_archive(self.path)
        self.addCleanup(memory.db.close)
        return memory

    def package(self):
        memory = self.load()
        task = handover.select_task(memory, self.records[3])
        return memory, task, handover.build_package(memory, task)

    def test_reconstruction_direct_and_wrapped(self):
        for wrapped in (False, True):
            with self.subTest(wrapped=wrapped):
                memory = self.load(wrapped)
                task = handover.select_task(memory, self.records[3])
                self.assertEqual(task['title'], 'Atlas Datenmodell erstellen')
                self.assertEqual(task['owner'], 'Komzin, Gleb')
                self.assertEqual(task['status'], 'open')
                self.assertEqual(task['claim'], 'Das Atlas Datenmodell ist in Arbeit.')
                self.assertEqual(len(task['history']), 2)
                self.assertEqual(len(memory.tasks), 4)

    def test_manual_fields_are_not_invented(self):
        memory = self.load()
        package = handover.build_package(memory, handover.select_task(memory, self.records[4]))
        for key, text in [('naechster', 'Atlas Measure öffnen'),
                          ('fertig_wenn', 'Prüfergebnis dokumentiert'),
                          ('scope', 'Nur Atlas'), ('abnahme', 'Ada prüft das Prüfergebnis')]:
            self.assertEqual(package[key]['wert'], text)
            self.assertEqual(package[key]['reife'], 'belegt')
            self.assertTrue(package[key]['belege'])

    def test_required_fields_and_unknown_without_false_success(self):
        _, _, package = self.package()
        expected = {'worum', 'naechster', 'fertig_wenn', 'art', 'bearbeitungsweg', 'scope',
                    'wiederverwendung', 'alias_begriffe', 'kontext',
                    'vorarbeiten_und_vorgespraeche', 'offene_fragen', 'abnahme', 'belege', 'reife'}
        self.assertTrue(expected <= set(package))
        for key in ('naechster', 'fertig_wenn', 'scope', 'abnahme'):
            self.assertEqual(package[key]['wert'], 'unbekannt')
            self.assertEqual(package[key]['reife'], 'unbekannt')
        self.assertTrue(package['offene_fragen'])

    def test_rule_types_routes_confidence_and_ambiguity(self):
        cases = [('Power BI Measure berechnen', 'power-bi-'), ('Datenmodell erstellen', 'power-bi-'),
                 ('Bericht erstellen', 'power-bi-'), ('Review durchführen', 'review'),
                 ('E-Mail Antwort schreiben', 'entwurf'), ('Nachfassen', 'erinnerung')]
        for title, expected in cases:
            with self.subTest(title=title):
                art, route = handover.classify(dict(title=title, owner='Komzin, Gleb'))
                self.assertTrue(art['wert'].startswith(expected))
                self.assertEqual(art['reife'], 'Annahme')
                self.assertGreater(art['konfidenz'], 0)
                self.assertIn(route['wert']['weg'], ('selbst', 'ki'))
        art, route = handover.classify(dict(title='Atlas', owner=None))
        self.assertEqual(art['wert'], 'unbekannt')
        self.assertEqual(route['wert'], 'unbekannt')

    def test_terms_preserve_source_words_and_remove_stopwords(self):
        terms = handover.extract_terms('Das Atlas Datenmodell und Power BI prüfen. Atlas Datenmodell')
        self.assertEqual(len(terms), len(set(terms)))
        lowered = [s.casefold() for s in terms]
        self.assertIn('atlas', lowered)
        self.assertIn('datenmodell', lowered)
        self.assertNotIn('und', lowered)
        self.assertNotIn('das', lowered)
        self.assertTrue(all(s.casefold() in 'das atlas datenmodell und power bi prüfen. atlas datenmodell'
                            for s in terms))

    def test_evidence_assignment_and_no_bare_known_assertions(self):
        _, _, package = self.package()
        leaves = list(assertions(package))
        self.assertGreater(len(leaves), 10)
        for leaf in leaves:
            if leaf['reife'] == 'belegt':
                self.assertTrue(leaf.get('belege'))
        self.assertTrue(package['belege'])
        for proof in package['belege']:
            self.assertTrue(proof['quelle'])
            self.assertTrue(proof['aussage'])
        rendered = handover.render_package(package)
        self.assertIn('canonical/', rendered)
        self.assertIn('Atlas Datenmodell erstellen', rendered)

    def test_prior_meetings_literal_short_passages_and_no_future(self):
        memory, _, package = self.package()
        rendered = handover.render_package(package)
        self.assertIn('Atlas Vorgespräch', rendered)
        self.assertNotIn('Atlas Zukunft', rendered)
        self.assertNotIn('Orion Reise', rendered)
        passages = [x for x in assertions(package.get('vorarbeiten_und_vorgespraeche'))
                    if isinstance(x['wert'], str) and x.get('rolle') == 'passage']
        self.assertTrue(passages)
        for passage in passages:
            self.assertLessEqual(len(passage['wert']), 300)
            self.assertTrue(any(passage['wert'] in d.get('body', '') for d in memory.documents))
        stats = handover.package_stats(package, rendered)
        self.assertGreater(stats['vorgespraeche'], 0)

    def test_related_candidates_are_not_finished_work(self):
        _, _, package = self.package()
        rendered = handover.render_package(package)
        self.assertIn('Atlas Vorlage erstellen', rendered)
        # Open related work never becomes evidence of an existing artifact.
        for leaf in assertions(package['wiederverwendung']):
            self.assertNotEqual(leaf['wert'], 'Atlas Datenmodell erstellen')

    def test_length_and_numeric_stats(self):
        _, _, package = self.package()
        text = handover.render_package(package)
        self.assertTrue(text.startswith('---\n'))
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertLessEqual(len(text.encode('utf-8')), 20_000)
        self.assertLessEqual(max(map(len, text.splitlines())), 400)
        stats = handover.package_stats(package, text)
        self.assertEqual(stats['zeilen'], len(text.splitlines()))
        self.assertGreater(stats['belegt'], 0)
        self.assertGreater(stats['unbekannt'], 0)
        self.assertGreater(stats['Annahme'], 0)

    def test_search_exact_unique_and_ambiguous(self):
        memory = self.load()
        self.assertEqual(handover.select_task(memory, 'Atlas Datenmodell erstellen')['id'], self.records[3])
        with self.assertRaises(Exception):
            handover.select_task(memory, 'Atlas')
        with self.assertRaises(Exception):
            handover.select_task(memory, 'Nicht vorhanden')

    def test_corrupted_source_fails_closed(self):
        bad = copy.deepcopy(self.records)
        bad[0][0]['source']['transcript'] += ' Manipuliert.'
        mini_archive(self.path, bad)
        with self.assertRaises(Exception):
            handover.load_archive(self.path)

    def test_missing_member_fails_closed(self):
        with tarfile.open(self.path, 'w:gz') as archive:
            data = b'{}\n'
            info = tarfile.TarInfo('canonical/journal.jsonl')
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
        with self.assertRaises(Exception):
            handover.load_archive(self.path)

    def test_artifact_reuse_has_literal_evidence_and_unknown_suitability(self):
        _, _, package = self.package()
        leaves = list(assertions(package['wiederverwendung']))
        self.assertTrue(any(x['reife'] == 'belegt' and 'vorhanden' in str(x['wert'])
                            for x in leaves))
        self.assertTrue(any(x['reife'] == 'unbekannt' for x in leaves))

    def test_rule_conflict_missing_owner_and_word_boundaries(self):
        art, route = handover.classify(dict(title='Review einer E-Mail Antwort', owner='Ada Beispiel'))
        self.assertEqual(art['wert'], 'unbekannt')
        self.assertEqual(art['konfidenz'], 0)
        art, route = handover.classify(dict(title='Review durchführen', owner=None))
        self.assertEqual(art['wert'], 'review')
        self.assertEqual(route['wert'], 'unbekannt')
        art, route = handover.classify(dict(title='Review durchführen', owner='Ada Beispiel'))
        self.assertEqual(route['wert']['weg'], 'delegieren')
        art, route = handover.classify(dict(title='Mailbox administrieren', owner='Komzin, Gleb'))
        self.assertEqual(art['wert'], 'unbekannt')

    def test_unknown_nested_fields_are_not_marked_as_known(self):
        memory = self.load()
        task = copy.deepcopy(handover.select_task(memory, self.records[3]))
        task['owner'] = None
        task['matter'] = None
        task['subject'] = None
        package = handover.build_package(memory, task)
        self.assertEqual(package['aufgabe']['owner']['reife'], 'unbekannt')
        self.assertEqual(package['kontext']['thema']['wert'], 'unbekannt')

    def test_corrupted_document_and_note_fail_closed(self):
        for kind in (1, 2):
            with self.subTest(kind=kind):
                bad = copy.deepcopy(self.records)
                if kind == 1:
                    bad[1][0]['body'] += ' Manipuliert.'
                else:
                    bad[2][0]['note_json'] = json.dumps({'summary': 'Manipuliert.'})
                mini_archive(self.path, bad)
                with self.assertRaises(handover.HandoverError):
                    handover.load_archive(self.path)

    def test_wrapper_checksum_and_journal_gap_fail_closed(self):
        gap = copy.deepcopy(self.records)
        gap[0][1]['revision'] = 9
        mini_archive(self.path, gap)
        with self.assertRaises(handover.HandoverError):
            handover.load_archive(self.path)
        raw = json.dumps(self.records[0][0])
        row = json.dumps(dict(kind='source', sequence=1, record_json=raw, record_hash='0' * 64)).encode()
        with tarfile.open(self.path, 'w:gz') as archive:
            info = tarfile.TarInfo('canonical/journal.jsonl')
            info.size = len(row)
            archive.addfile(info, io.BytesIO(row))
        with self.assertRaises(handover.HandoverError):
            handover.load_archive(self.path)

    def test_accepted_generation_replaces_the_prior_projection(self):
        from generation_review import logical_entries, compile_generation
        changed = copy.deepcopy(self.records)
        base = logical_entries(changed[0])
        plan = copy.deepcopy(base)
        plan[0]['payload']['proposal']['observations'][0]['title'] = 'Atlas Datenmodell finalisieren'
        payload = compile_generation(base, plan, source_reviews={'fixture:first': 'Synthetische Präzisierung'},
                                     identity_links=[{'old_id': changed[3], 'new_id': changed[3],
                                                      'reason': 'Unveränderte synthetische Aufgabenidentität'}],
                                     reason='Synthetischer Generationstest')
        changed[0].append(dict(kind='generation', revision=5, payload=payload))
        mini_archive(self.path, changed)
        memory = handover.load_archive(self.path)
        self.addCleanup(memory.db.close)
        task = handover.select_task(memory, changed[3])
        self.assertEqual(task['title'], 'Atlas Datenmodell finalisieren')
        rendered = handover.render_package(handover.build_package(memory, task))
        self.assertIn('canonical/journal.jsonl:L5', rendered)

    def test_human_correction_has_its_own_source_and_preserves_identity(self):
        changed = copy.deepcopy(self.records)
        cid = '20000000-0000-4000-8000-000000000004'
        changed[0].append(dict(kind='human', revision=5, command_id=cid,
                              actor_id='20000000-0000-4000-8000-000000000003',
                              payload=dict(action='correct', target_id=changed[3], reason='Synthetische Korrektur',
                                           patch={'title': 'Atlas Modell korrigiert', 'owner': 'Ada Beispiel'},
                                           event_date='2026-01-07')))
        mini_archive(self.path, changed)
        memory = handover.load_archive(self.path)
        self.addCleanup(memory.db.close)
        task = handover.select_task(memory, changed[3])
        self.assertEqual(task['id'], changed[3])
        self.assertEqual(task['title'], 'Atlas Modell korrigiert')
        self.assertEqual(task['owner'], 'Ada Beispiel')
        package = handover.build_package(memory, task)
        self.assertTrue(any(cid in r for r in package['worum']['belege']))

    def test_progress_does_not_prove_initial_title_or_owner(self):
        _, _, package = self.package()
        self.assertTrue(all('journal.jsonl:L1;' in r for r in package['worum']['belege']))
        self.assertTrue(all('journal.jsonl:L1;' in r for r in package['aufgabe']['owner']['belege']))
        # The latest claim and current status do come from the progress report.
        self.assertTrue(any('journal.jsonl:L2;' in r for r in package['aufgabe']['status']['belege']))

    def test_owner_change_updates_owner_evidence_without_changing_title(self):
        records = fixture_records(owner_change=True)
        mini_archive(self.path, records)
        memory = handover.load_archive(self.path)
        self.addCleanup(memory.db.close)
        task = handover.select_task(memory, records[3])
        package = handover.build_package(memory, task)
        self.assertEqual(package['aufgabe']['owner']['wert'], 'Ada Beispiel')
        self.assertTrue(all('journal.jsonl:L2;' in r for r in package['aufgabe']['owner']['belege']))
        self.assertTrue(all('journal.jsonl:L1;' in r for r in package['worum']['belege']))

    def test_manual_note_override_proves_labels_only_at_override(self):
        records = copy.deepcopy(self.records)
        cid = '20000000-0000-4000-8000-000000000005'
        records[0].append(dict(kind='human', revision=5, command_id=cid,
            actor_id='20000000-0000-4000-8000-000000000003',
            payload=dict(action='update_task', target_id=records[4], reason='Synthetische Präzisierung',
                         event_date='2026-01-07', patch={'note': 'naechster: Neue Prüfung'})))
        mini_archive(self.path, records)
        memory = handover.load_archive(self.path)
        self.addCleanup(memory.db.close)
        task = handover.select_task(memory, records[4])
        package = handover.build_package(memory, task)
        self.assertEqual(package['naechster']['wert'], 'Neue Prüfung')
        self.assertTrue(all(cid in r for r in package['naechster']['belege']))
        self.assertTrue(all('journal.jsonl:L4;' in r for r in package['worum']['belege']))
        self.assertEqual(package['fertig_wenn']['reife'], 'unbekannt')

    def test_event_local_sources_do_not_inherit_other_human_history(self):
        memory, task, _ = self.package()
        task = copy.deepcopy(task)
        cid = self.records[0][-1]['command_id']
        task['human_history'] = [{'command_id': cid, 'action': 'correct', 'patch': {}, 'event_date': '2026-01-06'}]
        package = handover.build_package(memory, task)
        for event in package['verlauf'][:2]:
            for leaf in assertions(event):
                self.assertTrue(all(cid not in ref for ref in leaf['belege']))

    def test_explicit_without_field_evidence_fails_closed(self):
        self.assertEqual(handover._explicit({'scope': 'Only Atlas'}, ('scope',), {})['reife'], 'unbekannt')
        self.assertEqual(handover._explicit({'note': 'scope: Only Atlas'}, ('scope',), {})['wert'], 'unbekannt')
        explicit = handover._explicit({'note': 'scope: Only Atlas'}, ('scope',), {'note': ['fixture:L1']})
        self.assertEqual(explicit['reife'], 'belegt')
        self.assertTrue(all('field=note' in ref for ref in explicit['belege']))

    def test_search_context_bounds_ranking_and_size_guard(self):
        memory, task, _ = self.package()
        original_docs = memory.documents
        earlier = next(d for d in original_docs if d['source_id'] == 'fixture:earlier')
        memory.documents = [{**earlier, 'id': 'synthetic-' + str(i),
                             'event_date': '2025-12-' + str(i + 10),
                             'source_id': 'synthetic-' + str(i), '_address': 'fixture:documents:L' + str(i)} for i in range(8)]
        memory.logical_entries = []  # Isolate canonical prior-document ranking.
        memory.tasks = [task] + [{**copy.deepcopy(task), 'id': 'synthetic-' + str(i)} for i in range(8)]
        package = handover.build_package(memory, task)
        self.assertEqual(len(package['verwandte_aufgaben']), handover.MAX_RELATED)
        self.assertEqual([v['id']['wert'] for v in package['verwandte_aufgaben']],
                         ['synthetic-' + str(i) for i in range(8)])
        self.assertEqual(len(package['vorarbeiten_und_vorgespraeche']), handover.MAX_MEETINGS)
        self.assertEqual([m['datum']['wert'] for m in package['vorarbeiten_und_vorgespraeche']],
                         ['2025-12-' + str(i) for i in range(17, 12, -1)])
        self.assertLessEqual(len(package['wiederverwendung']), handover.MAX_REUSE)
        self.assertEqual(package['suchmetadaten']['vorgespraeche']['ausgelassen'], 3)
        self.assertEqual(package, handover.build_package(memory, task))
        oversized = copy.deepcopy(package)
        oversized['worum']['wert'] = 'X' * handover.MAX_PACKAGE_BYTES
        rendered = handover.render_package(oversized)
        self.assertLessEqual(len(rendered.encode('utf-8')), 20_000)
        self.assertIn('gekuerzte_zeichen', rendered)

    def test_write_boundary_and_no_overwrite(self):
        path = Path(self.temp.name) / 'result.md'
        handover.write_package('synthetisch\n', path)
        self.assertEqual(path.read_text(), 'synthetisch\n')
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(handover.HandoverError):
            handover.write_package('anderer Inhalt', path)
        with self.assertRaises(handover.HandoverError):
            handover.write_package('synthetisch', HERE.parent / 'must-not-exist.md')
        link = Path(self.temp.name) / 'outside'
        link.symlink_to(HERE.parent, target_is_directory=True)
        with self.assertRaises(handover.HandoverError):
            handover.write_package('synthetisch', link / 'must-not-exist.md')

    def test_cli_emits_numeric_stats_and_content_only_in_file(self):
        result = Path(self.temp.name) / 'cli.md'
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = handover.main(['--archive', str(self.path), '--task', self.records[3],
                                  '--out', str(result)])
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), '')
        self.assertTrue(all(type(v) in (int, float) for v in json.loads(stdout.getvalue()).values()))
        self.assertNotIn('Atlas', stdout.getvalue())
        self.assertIn('Atlas', result.read_text())

    def test_yaml_flow_values_are_json_compatible_and_all_maturity_paths_counted(self):
        _, _, package = self.package()
        text = handover.render_package(package)
        frontmatter = text.split('---\n', 2)[1]
        parsed = {}
        field, rows = None, []
        def save():
            if field == 'belege':
                parsed[field] = [json.loads(row.strip()[2:]) for row in rows if row.strip().startswith('- ')]
            elif field:
                parsed[field] = json.loads('\n'.join(rows))
        for row in frontmatter.splitlines():
            if row and not row.startswith(' '):
                save()
                field, value = row.split(':', 1)
                rows = [value.strip()] if value.strip() else []
            else:
                rows.append(row)
        save()
        compact = handover.presentation_package(package)
        expected = dict(compact)
        expected['belege'] = [f'B{i} {p["quelle"]} → {p["aussage"]}'
                              for i, p in enumerate(compact['belege'], 1)]
        self.assertEqual(parsed, expected)
        counts = handover.package_stats(package, text)
        self.assertEqual(sum(counts[k] for k in ('belegt', 'Annahme', 'unbekannt')),
                         len(list(assertions(compact))))

    def test_compact_limits_unicode_long_tokens_and_all_required_fields(self):
        _, _, package = self.package()
        for token in ('Ä' * 30_000, '\\"' * 30_000, 'wort\n' * 30_000):
            with self.subTest(length=len(token)):
                oversized = copy.deepcopy(package)
                oversized['worum']['wert'] = token
                oversized['scope']['wert'] = token
                oversized['scope']['reife'] = 'Annahme'
                text = handover.render_package(oversized)
                self.assertLessEqual(len(text.encode('utf-8')), 20_000)
                self.assertLessEqual(len(text.splitlines()), 150)
                self.assertLessEqual(max(map(len, text.splitlines())), 400)
                compact = handover.presentation_package(oversized)
                self.assertTrue(set(handover.REQUIRED_FIELDS) <= set(compact))
                self.assertGreater(compact['worum']['gekuerzte_zeichen'], 0)
                self.assertEqual(compact['scope']['reife'], 'Annahme')
                self.assertEqual(compact['naechster']['wert'], 'unbekannt')
                self.assertEqual(compact['naechster']['reife'], 'unbekannt')

    def test_evidence_limit_count_and_direct_sources_before_latest_meetings(self):
        _, _, package = self.package()
        package['worum']['belege'] = ['fixture/journal:L1; field=title']
        package['vorarbeiten_und_vorgespraeche'] = [
            {k: handover.assertion(v, 'belegt', [f'fixture/meetings:L{i}'])
             for k, v in [('titel', f'Atlas Runde {i}'), ('datum', f'2026-01-0{5-i}'),
                          ('passage', 'Atlas ' * 100)]} for i in range(5)]
        package['wiederverwendung'] = [
            {'bestandsaussage': handover.assertion('Atlas Bestand', 'belegt', [f'fixture/reuse:L{i}'])}
            for i in range(5)]
        package['verwandte_aufgaben'] = [
            {'titel': handover.assertion(f'Atlas Arbeit {i}', 'belegt', [f'fixture/related:L{i}'])}
            for i in range(12)]
        compact = handover.presentation_package(package)
        self.assertEqual(len(compact['belege']), 12)
        self.assertGreater(compact['belege_weitere'], 0)
        self.assertEqual(compact['belege'][0]['quelle'], 'fixture/journal:L1')
        meeting_refs = [p['quelle'] for p in compact['belege'] if '/meetings:' in p['quelle']]
        self.assertEqual(meeting_refs, [f'fixture/meetings:L{i}' for i in range(5)])
        self.assertTrue(all(len(p['aussage']) <= 200 for p in compact['belege']))
        self.assertTrue(all(len(m['passage']['wert']) <= 300
                            for m in compact['vorarbeiten_und_vorgespraeche']))
        self.assertEqual(len(compact['verwandte_aufgaben']), 8)
        text = handover.render_package(package)
        self.assertIn(f'… und {compact["belege_weitere"]} weitere', text)
        self.assertEqual(sum(line.startswith('  - ') for line in text.splitlines()), 12)

    def test_maturity_is_bound_to_every_presented_assertion(self):
        _, _, package = self.package()
        compact = handover.presentation_package(package)
        for path, item in handover._assertion_paths(compact):
            self.assertEqual(compact['reife'][path], item['reife'])
            if item['reife'] == 'belegt': self.assertTrue(item['belege'])
        for name in handover.REQUIRED_FIELDS:
            invalid = dict(package)
            del invalid[name]
            with self.assertRaisesRegex(handover.HandoverError, 'E_SCHEMA'):
                handover.render_package(invalid)

    def test_dense_unicode_package_fits_without_dropping_selected_entries(self):
        _, _, package = self.package()
        for item in assertions(package):
            if item['reife'] != 'unbekannt' and isinstance(item['wert'], str):
                item['wert'] = 'Ä\\"' * 2_000
        compact = handover.presentation_package(package)
        text = handover.render_package(package)
        self.assertLessEqual(len(text.encode('utf-8')), 20_000)
        self.assertLessEqual(len(text.splitlines()), 150)
        self.assertLessEqual(max(map(len, text.splitlines())), 400)
        self.assertEqual(len(compact['vorarbeiten_und_vorgespraeche']),
                         len(package['vorarbeiten_und_vorgespraeche']))
        self.assertEqual(len(compact['verwandte_aufgaben']), len(package['verwandte_aufgaben']))
        package['worum']['belege'] = ['S' * 500]
        with self.assertRaisesRegex(handover.HandoverError, 'E_SOURCE_SIZE'):
            handover.render_package(package)


if __name__ == '__main__':
    unittest.main()
