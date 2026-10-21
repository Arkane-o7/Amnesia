import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import jobs


class JobTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = patch('backend.jobs.data_dir', return_value=Path(self.directory.name))
        self.path.start()
        self.registry = patch.dict(jobs.JOBS, {}, clear=True)
        self.registry.start()

    def tearDown(self):
        self.registry.stop()
        self.path.stop()
        self.directory.cleanup()

    def finish(self, jid):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            job = jobs.get(jid)
            if job['status'] not in ('running', 'queued'):
                return job
            time.sleep(.005)
        self.fail('Job failed to finish within its bounded local work.')

    def test_completed_result_survives_registry_reload(self):
        def work(progress, cancelled):
            progress(1, 1, 'Measured case')
            return {'count': 1, 'measured': True}
        started = jobs.start('policy', work)
        job = self.finish(started['id'])
        self.assertEqual(job['status'], 'completed')
        jobs.JOBS.clear()
        restored = jobs.get(job['id'])
        self.assertEqual(restored['result'], {'count': 1, 'measured': True})
        self.assertNotIn('cancel', restored)

    def test_cancellation_never_reports_partial_result_complete(self):
        entered, release = threading.Event(), threading.Event()
        def work(progress, cancelled):
            progress(1, 2, 'In progress')
            entered.set()
            release.wait(2)
            return {'partial': True}
        started = jobs.start('live_ai', work)
        self.assertTrue(entered.wait(1))
        with self.assertRaises(ValueError):
            jobs.start('policy', work)
        jobs.cancel(started['id'])
        release.set()
        final = self.finish(started['id'])
        self.assertEqual(final['status'], 'cancelled')
        self.assertNotIn('result', final)

    def test_server_restart_marks_unfinished_run_interrupted(self):
        jobs.save({'id': 'unfinished', 'status': 'running', 'completed': 1, 'total': 2})
        self.assertEqual(jobs.get('unfinished')['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()
