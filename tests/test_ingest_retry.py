import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.memory import Memory


class IngestRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'memory.sqlite3'
        self.mem = Memory(self.path)
        self.wid = self.mem.create_workspace('Retry isolation')
        self.sid = self.mem.state(self.wid)['sessions'][0]['id']

    def tearDown(self):
        self.mem.close()
        self.tmp.cleanup()

    def test_failed_extraction_creates_no_session_event_or_receipt(self):
        with patch('backend.memory.extract_ai', side_effect=ValueError('Temporary service failure')):
            with self.assertRaises(ValueError):
                self.mem.ingest(self.wid, self.sid, 'I live in Chennai.', provider='ai', request_id='retry', new_session=True)
        state = self.mem.state(self.wid)
        self.assertEqual(len(state['sessions']), 1)
        self.assertEqual(state['facts'], [])
        self.assertEqual(state['events'], [])
        self.assertEqual(self.mem.rows('SELECT * FROM ingest_receipts'), [])

    def test_lost_response_replayed_after_restart_returns_identical_receipt(self):
        args = (self.wid, self.sid, 'I moved to Chennai.')
        result = self.mem.ingest(*args, request_id='stable', new_session=True)
        self.mem.close()
        self.mem = Memory(self.path)
        with patch('backend.memory.extract_local', side_effect=AssertionError('Do not extract committed request again')):
            replay = self.mem.ingest(*args, request_id='stable', new_session=True)
        self.assertEqual(replay, result)
        self.assertEqual(len(self.mem.state(self.wid)['sessions']), 2)
        self.assertEqual(len(self.mem.state(self.wid)['events']), 1)

    def test_same_key_with_different_payload_is_rejected(self):
        self.mem.ingest(self.wid, self.sid, 'I live in Chennai.', request_id='stable')
        with self.assertRaisesRegex(ValueError, 'different input'):
            self.mem.ingest(self.wid, self.sid, 'I live in Pune.', request_id='stable')
        self.assertEqual(len(self.mem.facts(self.wid)), 1)

    def test_failed_commit_rolls_back_new_session(self):
        with patch.object(self.mem, 'reconcile', side_effect=ValueError('Simulated commit failure')):
            with self.assertRaises(ValueError):
                self.mem.ingest(self.wid, self.sid, 'I live in Chennai.', request_id='stable', new_session=True)
        self.assertEqual(len(self.mem.state(self.wid)['sessions']), 1)
        self.assertEqual(self.mem.state(self.wid)['events'], [])
        result = self.mem.ingest(self.wid, self.sid, 'I live in Chennai.', request_id='stable', new_session=True)
        self.assertNotEqual(result['session_id'], self.sid)

