import io,json,time,unittest
from processor import collect_stream

def events(*items):return io.BytesIO(''.join('data: '+json.dumps(item)+'\n\n' for item in items).encode())
START={'type':'message_start','message':{'id':'fixture','model':'fixture','content':[],'usage':{'input_tokens':100,'output_tokens':1}}}
BLOCK={'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}}
TEXT={'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':'Grüße'}}

class StreamTests(unittest.TestCase):
    def test_assembles_text_and_final_cumulative_usage(self):
        response=events(START,BLOCK,TEXT,{'type':'ping'},{'type':'message_delta','delta':{'stop_reason':'end_turn'},'usage':{'output_tokens':20}},{'type':'message_stop'})
        out=collect_stream(response,time.monotonic()+5)
        self.assertEqual(out['content'][0]['text'],'Grüße');self.assertEqual(out['usage'],{'input_tokens':100,'output_tokens':20});self.assertTrue(out['usage_final'])
    def test_truncated_stream_is_not_success_or_final_cost(self):
        out=collect_stream(events(START,BLOCK,TEXT),time.monotonic()+5)
        self.assertIsNone(out['stop_reason']);self.assertFalse(out['usage_final']);self.assertIn('Incomplete',out['error'])
    def test_overload_event_does_not_promote_partial_output(self):
        out=collect_stream(events(START,{'type':'error','error':{'type':'overloaded_error'}}),time.monotonic()+5)
        self.assertIsNone(out['stop_reason']);self.assertFalse(out['usage_final'])
    def test_total_deadline_is_enforced(self):
        out=collect_stream(events(START),time.monotonic()-1)
        self.assertIn('TimeoutError',out['error'])

if __name__=='__main__':unittest.main()
