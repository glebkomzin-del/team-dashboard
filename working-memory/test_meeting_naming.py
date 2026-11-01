import unittest

from meeting_naming import (is_ambiguous_source_title, resolve_display_title,
                            teams_metadata, title_from_response)


TEAMS = '''Meeting Titel: Gieselberg, Jan Philipp
Teilnehmer: Gleb Komzin; Jan Philipp Gieselberg
Datum: 18.09.2026
Beginn: 09:46:30 +02:00 Ende: 18.09.2026 10:25:58 +02:00
[09:46:30] Gleb Komzin: Hallo.
[09:47:10] Jan Philipp Gieselberg: Wir müssen das Power BI Modell und RLS prüfen.
[09:48:20] Gleb Komzin: Das Thema ist die Freigabe des Power BI Modells.
'''


class MeetingNamingTests(unittest.TestCase):
    def test_observed_teams_header_and_person_title(self):
        self.assertEqual(teams_metadata(TEAMS),{
            'source_title':'Gieselberg, Jan Philipp','participants':['Gleb Komzin','Jan Philipp Gieselberg'],
            'event_date':'18.09.2026','started_at':'09:46:30 +02:00 Ende: 18.09.2026 10:25:58 +02:00'})
        self.assertTrue(is_ambiguous_source_title('Gieselberg, Jan Philipp',TEAMS))
        self.assertFalse(is_ambiguous_source_title('Power-BI-Modell und RLS',TEAMS))

    def test_same_call_title_requires_exact_source_evidence(self):
        originals={'U0001':{'text':'Wir müssen das Power BI Modell und RLS prüfen.'}}
        accepted=title_from_response({'text':'Power-BI-Modell und RLS prüfen','evidence_ids':['U0001']},originals,TEAMS)
        self.assertEqual(accepted['method'],'same_call_source_cited_title')
        self.assertIsNone(title_from_response({'text':'SAP-Migration beschließen','evidence_ids':['U0001']},originals,TEAMS))
        self.assertIsNone(title_from_response({'text':'Gieselberg, Jan Philipp','evidence_ids':['U0001']},originals,TEAMS))

    def test_stored_grounded_title_wins_without_new_model_call(self):
        note={'display_title':{'text':'Power-BI-Modell und RLS prüfen',
              'passages':['Wir müssen das Power BI Modell und RLS prüfen.'],
              'method':'same_call_source_cited_title'}}
        result=resolve_display_title('Gieselberg, Jan Philipp',TEAMS,'2026-09-18',note_payloads=[note])
        self.assertEqual(result['text'],'Power-BI-Modell und RLS prüfen')
        self.assertEqual(result['method'],'same_call_source_cited_title')

    def test_existing_source_without_cited_title_stays_transparent(self):
        result=resolve_display_title('Gieselberg, Jan Philipp',TEAMS,'2026-09-18')
        self.assertEqual(result,{'text':'Thema offen · Gespräch mit Jan Philipp Gieselberg · 18.09.2026','method':'transparent_fallback','evidence':[]})

    def test_uncertain_existing_source_is_transparently_named(self):
        transcript='''Meeting Titel: Wietschorke, Caroline
Teilnehmer: Gleb Komzin; Caroline Wietschorke
Datum: 17.09.2026
[10:00:00] Gleb Komzin: Hallo, hörst du mich?
[10:00:03] Caroline Wietschorke: Ja, hallo.
'''
        result=resolve_display_title('Wietschorke, Caroline',transcript,'2026-09-17')
        self.assertEqual(result['text'],'Thema offen · Gespräch mit Caroline Wietschorke · 17.09.2026')
        self.assertEqual(result['method'],'transparent_fallback')

    def test_reviewed_empty_recording_gets_honest_dated_title(self):
        transcript='Meeting Titel: Teams Meeting\nDatum: 2026-09-18\n[10:00:00] Unknown: Bild\n'
        note={'display_title':{'text':'Aufzeichnung ohne Gesprächsinhalt · 18.09.2026',
              'passages':['[10:00:00] Unknown: Bild'],'method':'reviewed_no_topic',
              'exception':'no_transcribed_content'}}
        result=resolve_display_title('Teams Meeting',transcript,'2026-09-18',note_payloads=[note])
        self.assertEqual(result['text'],'Aufzeichnung ohne Gesprächsinhalt · 18.09.2026')
        self.assertEqual(result['method'],'reviewed_no_topic')

    def test_clear_source_title_and_identity_are_not_rewritten(self):
        result=resolve_display_title('Abstimmung ER Mapping',TEAMS,'2026-09-18')
        self.assertEqual(result,{'text':'Abstimmung ER Mapping','method':'source_title','evidence':[]})


if __name__=='__main__':unittest.main()
