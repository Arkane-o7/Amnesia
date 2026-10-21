import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from backend.server import Handler


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = patch("backend.server.DATA", Path(self.tmp.name))
        self.patch.start()
        self.env_patch = patch.dict("os.environ", {"AMNESIA_PROVIDER": "offline"})
        self.env_patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%s/api/" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    def request(self, path, body=None, headers=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base+path, data=data, headers={"Content-Type": "application/json", **(headers or {})})
        with urllib.request.urlopen(req) as response:
            return json.load(response)

    def test_http_end_to_end_and_export(self):
        self.assertEqual(self.request("health")["data_root"], str(Path(self.tmp.name).resolve()))
        wid = self.request("workspaces", {"name": "API test"})["id"]
        sid = self.request("state?workspace_id="+wid)["sessions"][0]["id"]
        for text in ("I live in Hyderabad.", "I moved to Chennai."):
            self.request("events", {"workspace_id": wid, "session_id": sid, "text": text})
        self.assertEqual(self.request("query", {"workspace_id": wid, "question": "Where do I live?"})["answer_value"], "Chennai")
        exported = self.request("export?workspace_id="+wid)
        self.assertEqual(len(exported["facts"]), 2)
        self.assertEqual(len(exported["events"]), 2)

    def test_cross_origin_write_and_invalid_input_are_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("workspaces", {"name": "blocked"}, {"Origin": "https://example.com"})
        self.assertEqual(caught.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request("workspaces", {"name": ""})
        self.assertEqual(caught.exception.code, 400)

    def test_ingestion_retry_deduplicates_through_http(self):
        wid = self.request('workspaces', {'name': 'Retry test'})['id']
        sid = self.request('state?workspace_id='+wid)['sessions'][0]['id']
        body = {'workspace_id': wid, 'session_id': sid, 'text': 'I live in Chennai.', 'request_id': 'http-retry', 'new_session': True}
        first = self.request('events', body)
        self.assertEqual(self.request('events', body), first)
        state = self.request('state?workspace_id='+wid)
        self.assertEqual(len(state['sessions']), 2)
        self.assertEqual(len(state['events']), 1)

    def test_evaluation_is_real_and_downloadable(self):
        report = self.request("evaluation", {"count": 10, "seed": 42})
        self.assertEqual(report["metrics"]["hybrid"]["instances"], 10)
        self.assertEqual(self.request("evaluation")["count"], 10)
        with urllib.request.urlopen(self.base+"dataset") as response:
            self.assertEqual(len(response.read().splitlines()), 10)


if __name__ == "__main__":
    unittest.main()
