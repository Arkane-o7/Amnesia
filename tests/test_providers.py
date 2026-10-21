import json
import os
import unittest
from unittest.mock import patch
from backend.memory import Memory
from backend.providers import dense_similarities, grounded_answer
from backend.extraction import extract_llm


class ProviderTests(unittest.TestCase):
    def test_dense_vectors_are_cached_and_rank_by_cosine(self):
        mem = Memory()
        with patch("backend.providers.post_openai", return_value={"data": [{"index": 0, "embedding": [1, 0]}, {"index": 1, "embedding": [0, 1]}, {"index": 2, "embedding": [1, 0]}]}) as remote:
            self.assertEqual(dense_similarities(mem.db, "home?", ["Chennai", "Rust"], "test-model"), [1, 0])
            self.assertEqual(dense_similarities(mem.db, "home?", ["Chennai", "Rust"], "test-model"), [1, 0])
            remote.assert_called_once()
        mem.close()

    def test_answer_adapter_rejects_citations_outside_context(self):
        facts = [{"id": "one", "subject": "You", "relation": "lives_in", "value": "Chennai", "evidence": "I live in Chennai", "effective_status": "active", "valid_from": "2026-01-01", "valid_until": None}]
        response = {"choices": [{"message": {"content": json.dumps({"answer": "You live in Chennai.", "cited_ids": ["invented"]})}}]}
        with patch("backend.providers.post_openai", return_value=response):
            with self.assertRaises(ValueError): grounded_answer("Where do I live?", facts, "test-model")
        response["choices"][0]["message"]["content"] = json.dumps({"answer": "You live in Chennai.", "cited_ids": ["one"]})
        with patch("backend.providers.post_openai", return_value=response):
            self.assertEqual(grounded_answer("Where do I live?", facts, "test-model")[1], ["one"])

    def test_llm_extraction_requires_explicit_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError): extract_llm("I live in Chennai.", "2026-01-01", [])

    def test_offline_evaluation_never_calls_external_provider(self):
        from backend.evaluate import run
        with patch.dict(os.environ, {"AMNESIA_EXTRACTOR": "llm", "AMNESIA_ANSWERER": "llm", "AMNESIA_EMBEDDING_MODEL": "test"}):
            with patch("backend.providers.post_openai", side_effect=AssertionError("No external calls allowed")):
                self.assertEqual(run(10)["count"], 10)


if __name__ == "__main__":
    unittest.main()
