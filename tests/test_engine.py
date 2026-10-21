import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.engine import structured, embeddings, consume_trace
from backend.retrieval import answer_ai

CONFIG = {'provider': 'openai', 'chat_model': 'gpt-4.1-mini', 'embedding_model': 'text-embedding-3-small'}
SCHEMA = {'type': 'object', 'properties': {'ready': {'type': 'boolean'}}, 'required': ['ready'], 'additionalProperties': False}


class EngineTests(unittest.TestCase):
    def test_openai_strict_schema_call_and_cache_are_auditable(self):
        with tempfile.TemporaryDirectory() as directory, patch('backend.engine.data_dir', return_value=Path(directory)), patch('backend.engine.cloud_key', return_value='fake-private-key'), patch('backend.engine.request_json', return_value={'choices': [{'message': {'content': '{"ready":true}'}}], 'usage': {'prompt_tokens': 12, 'completion_tokens': 4}}) as request:
            consume_trace()
            for _ in range(2):
                self.assertTrue(structured([{'role': 'user', 'content': 'ready'}], SCHEMA, 'test', CONFIG, cache=True)['ready'])
            self.assertEqual(request.call_count, 1)
            self.assertTrue(request.call_args.args[1]['response_format']['json_schema']['strict'])
            traces = consume_trace()
            self.assertEqual([c['cache_hit'] for c in traces], [False, True])
            self.assertEqual(traces[0]['input_tokens'], 12)
            self.assertNotIn('fake-private-key', json.dumps(traces))

    def test_openai_embeddings_preserve_provider_order(self):
        with patch('backend.engine.cloud_key', return_value='fake-private-key'), patch('backend.engine.request_json', return_value={'data': [{'index': 1, 'embedding': [0, 1]}, {'index': 0, 'embedding': [1, 0]}]}):
            self.assertEqual(embeddings(['one', 'two'], CONFIG), [[1, 0], [0, 1]])

    def test_grounded_reader_rejects_unknown_citation(self):
        with patch('backend.retrieval.structured', return_value={'answer': 'Chennai', 'answer_value': 'Chennai', 'status': 'answered', 'cited_ids': ['invented']}):
            with self.assertRaisesRegex(ValueError, 'outside'):
                answer_ai('Where?', [{'id': 'fact1', 'subject': 'You', 'relation': 'lives_in', 'value': 'Chennai', 'evidence': 'I live in Chennai.', 'observed_at': '2026-01-01', 'valid_from': '2026-01-01', 'effective_status': 'active'}], CONFIG)


if __name__ == '__main__':
    unittest.main()
