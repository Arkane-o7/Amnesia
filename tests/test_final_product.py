import copy
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.engine import save_cloud_key, cloud_key, save_configuration, diagnostics
from backend.extraction import extract_ai
from backend.memory import Memory
from backend.retrieval import personalized_pagerank, answer_ai

T0, T1, T2, T3 = ["2026-01-%02dT12:00:00+00:00" % d for d in (1, 2, 3, 4)]


class FinalProductTests(unittest.TestCase):
    def setUp(self):
        self.mem = Memory()
        self.wid = self.mem.create_workspace("Final product test")
        self.sid = self.mem.rows("SELECT id FROM sessions WHERE workspace_id=?", (self.wid,))[0]["id"]

    def tearDown(self):
        self.mem.close()

    def add(self, text, at=T0):
        return self.mem.ingest(self.wid, self.sid, text, at)

    def test_independent_preference_scopes_prevent_false_invalidation(self):
        self.add("I prefer Python. I prefer coffee.")
        self.add("I now prefer Rust.", T1)
        current = [f for f in self.mem.facts(self.wid) if f["status"] == "active"]
        self.assertEqual({f["value"] for f in current}, {"Rust", "coffee"})
        self.assertEqual({f["scope"] for f in current}, {"programming_language", "beverage"})

    def test_explicit_confirmation_resolves_only_one_scope_and_preserves_snapshot(self):
        self.add("I live in Chennai. I prefer coffee.")
        self.add("Maybe I live in Pune.", T1)
        selected = next(f for f in self.mem.facts(self.wid) if f["value"] == "Chennai")
        self.mem.resolve_conflict(self.wid, self.sid, selected["id"], "Confirmed: my home is Chennai.")
        self.assertEqual(self.mem.query(self.wid, "Where do I live?")["answer_value"], "Chennai")
        self.assertEqual(self.mem.query(self.wid, "Where do I live?", as_of=T2)["answer_value"], "UNRESOLVED")
        coffee = next(f for f in self.mem.facts(self.wid) if f["value"] == "coffee")
        self.assertEqual(coffee["status"], "active")
        self.assertEqual(self.mem.state(self.wid)["facts"][0]["evidence_count"], 2)

    def test_conflict_alternatives_survive_top_one_retrieval(self):
        self.add("I live in Chennai.")
        self.add("Maybe I live in Pune.", T1)
        answer = self.mem.query(self.wid, "Where do I live?", k=1)
        self.assertEqual(answer["answer_value"], "UNRESOLVED")
        self.assertEqual(len(answer["used_ids"]), 2)

    def test_backup_import_roundtrip_preserves_provenance_with_new_identifiers(self):
        self.add("I live in Hyderabad. I prefer coffee.")
        self.add("I moved to Chennai.", T1)
        exported = self.mem.export_workspace(self.wid)
        restored = self.mem.import_workspace(exported)
        new = self.mem.export_workspace(restored)
        self.assertNotEqual(new["workspace"]["id"], exported["workspace"]["id"])
        self.assertFalse({f["id"] for f in new["facts"]} & {f["id"] for f in exported["facts"]})
        self.assertEqual(len(new["history"]), len(exported["history"]))
        self.assertEqual(len(new["evidence_links"]), len(exported["evidence_links"]))
        self.assertEqual(self.mem.query(restored, "Where do I live?")["answer_value"], "Chennai")
        self.assertEqual(self.mem.query(restored, "Where do I live?", as_of=T0)["answer_value"], "Hyderabad")

    def test_corrupt_import_rolls_back_every_row(self):
        self.add("I live in Chennai.")
        export = self.mem.export_workspace(self.wid)
        export["facts"][0]["subject_id"] = "missing-reference"
        before = len(self.mem.rows("SELECT id FROM workspaces"))
        with self.assertRaises(ValueError):
            self.mem.import_workspace(export)
        self.assertEqual(len(self.mem.rows("SELECT id FROM workspaces")), before)
        self.assertEqual(len(self.mem.facts(self.wid)), 1)

    def test_alias_resolution_reuses_entity_identity(self):
        self.add("I work at Meridian.")
        with self.mem.db:
            self.mem.register_alias(self.wid, "Meridian Labs", "Meridian", "Meridian Labs is the same company as Meridian.")
            one = self.mem.entity(self.wid, "Meridian")
            two = self.mem.entity(self.wid, "Meridian Labs")
        self.assertEqual(one, two)
        self.assertEqual(len(self.mem.export_workspace(self.wid)["aliases"]), 1)

    def test_pagerank_is_normalized_and_traverses_connected_entities(self):
        self.add("I work at Meridian.")
        batch = [{"subject": "Meridian", "relation": "located_in", "value": "Pune", "intent": "assert", "confidence": .95, "evidence": "Meridian is based in Pune.", "valid_until": None}]
        self.mem.ingest(self.wid, self.sid, "Meridian is based in Pune.", T1, assertion_batch=batch)
        facts = self.mem.state(self.wid)["facts"]
        scores, ranks = personalized_pagerank(facts, "Where is my employer based?", [0, 0])
        self.assertAlmostEqual(sum(ranks.values()), 1, places=8)
        self.assertTrue(all(score > 0 for score in scores))
        pune = next(f for f in facts if f["value"] == "Pune")
        self.assertGreater(ranks[pune["object_id"]], 0)

    def test_future_dated_update_does_not_retire_current_home_early(self):
        self.add("I live in Hyderabad.")
        batch = [{"subject": "You", "relation": "lives_in", "value": "Chennai", "intent": "update", "confidence": .95, "evidence": "I will move to Chennai on 4 January.", "valid_from": T3, "valid_until": None}]
        self.mem.ingest(self.wid, self.sid, "I will move to Chennai on 4 January.", T1, assertion_batch=batch)
        self.assertEqual(self.mem.query(self.wid, "Where do I live?", as_of=T2)["answer_value"], "Hyderabad")
        self.assertEqual(self.mem.query(self.wid, "Where do I live?", as_of=T3)["answer_value"], "Chennai")

    def test_temporary_support_extends_validity_without_conflict(self):
        self.add("I am in Delhi for 3 days.")
        r = self.add("I am still in Delhi for 7 days.", T1)
        self.assertEqual(r["decisions"][0]["label"], "SUPPORTS")
        self.assertEqual(len(self.mem.facts(self.wid)), 1)
        self.assertEqual(self.mem.query(self.wid, "Where am I staying temporarily?", as_of="2026-01-06T12:00:00+00:00")["answer_value"], "Delhi")

    def test_cancel_metadata_is_normalized_without_rejecting_valid_negative_evidence(self):
        old = {"subject": "Your dog", "relation": "name", "value": "Bruno", "scope": "", "intent": "cancel", "confidence": .95, "evidence": "We've renamed my dog to Milo.", "valid_from": T1, "valid_until": T1}
        new = dict(old, value="Milo", intent="update", valid_until=None)
        with patch("backend.engine.structured", return_value={"facts": [old, new], "aliases": [], "unsupported": []}):
            facts, _, _ = extract_ai("We've renamed my dog to Milo.", T1, [])
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["value"], "Milo")

    def test_source_quotes_cannot_be_fabricated_by_extractor(self):
        fact = {"subject": "You", "relation": "lives_in", "value": "Chennai", "scope": "", "intent": "assert", "confidence": .95, "evidence": "Invented quote", "valid_from": None, "valid_until": None}
        with patch("backend.engine.structured", return_value={"facts": [fact], "aliases": [], "unsupported": []}):
            with self.assertRaises(ValueError): extract_ai("I live in Chennai.", T0, [])

    def test_pet_rename_keeps_names_as_versions_instead_of_entity_aliases(self):
        prior = [{"subject": "Your dog", "relation": "name", "value": "Bruno"}]
        fact = {"subject": "Bruno", "relation": "name", "value": "Milo", "scope": "", "intent": "update", "confidence": .95, "evidence": "We've renamed my dog to Milo.", "valid_from": None, "valid_until": None}
        result = {"facts": [fact], "aliases": [{"alias": "Milo", "canonical": "Bruno"}], "unsupported": []}
        with patch("backend.engine.structured", return_value=result):
            facts, _, aliases = extract_ai(fact["evidence"], T1, prior)
        self.assertEqual(facts[0]["subject"], "Your dog")
        self.assertEqual(aliases, [])

    def test_device_scopes_keep_phone_replacement_separate_from_laptop(self):
        self.add("I own an iPhone. I own a MacBook.")
        self.add("I sold the iPhone. I bought a Pixel.", T1)
        phone = self.mem.query(self.wid, "Which phone do I use now?")
        laptop = self.mem.query(self.wid, "Which laptop do I own?")
        self.assertEqual(phone["answer_value"], "Pixel")
        self.assertEqual(laptop["answer_value"], "MacBook")
        self.assertEqual({f["scope"] for f in laptop["retrieved"]}, {"laptop"})

    def test_extractor_repairs_validation_once_but_never_retries_auth(self):
        fact = {"subject": "You", "relation": "lives_in", "value": "Chennai", "scope": "", "intent": "assert", "confidence": .95, "evidence": "I live in Chennai.", "valid_from": None, "valid_until": None}
        invalid = dict(fact, evidence="I LIVE IN CHENNAI.")
        with patch("backend.engine.structured", side_effect=[{"facts": [invalid], "aliases": [], "unsupported": []}, {"facts": [fact], "aliases": [], "unsupported": []}]) as model:
            self.assertEqual(extract_ai(fact["evidence"], T0, [])[0][0]["value"], "Chennai")
            self.assertEqual(model.call_count, 2)
        with patch("backend.engine.structured", side_effect=ValueError("OpenAI authentication failed.")) as model:
            with self.assertRaisesRegex(ValueError, "authentication"):
                extract_ai(fact["evidence"], T0, [])
            self.assertEqual(model.call_count, 1)

    def test_phone_conflict_does_not_block_independent_laptop_answer(self):
        self.add("I own an iPhone. I own a MacBook.")
        self.add("Maybe I own a Pixel.", T1)
        self.assertEqual(self.mem.query(self.wid, "Which phone do I own?")["answer_value"], "UNRESOLVED")
        self.assertEqual(self.mem.query(self.wid, "Which laptop do I own?")["answer_value"], "MacBook")

    def test_another_persons_conflict_does_not_block_my_home_answer(self):
        self.add("I live in Chennai.")
        for value, intent, at in (("Pune", "assert", T1), ("Kochi", "uncertain", T2)):
            self.mem.ingest(self.wid, self.sid, "Alice may live in " + value + ".", at, assertion_batch=[{"subject": "Alice", "relation": "lives_in", "value": value, "intent": intent, "confidence": .6 if intent == "uncertain" else .95, "evidence": "Alice may live in " + value + "."}])
        self.assertEqual(self.mem.query(self.wid, "Where do I live?")["answer_value"], "Chennai")
        self.assertEqual(self.mem.query(self.wid, "Where does Alice live?")["answer_value"], "UNRESOLVED")


class CredentialsTests(unittest.TestCase):
    def test_saved_key_is_private_and_diagnostics_never_return_it(self):
        with tempfile.TemporaryDirectory() as tmp, patch("backend.engine.data_dir", return_value=Path(tmp)), patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            key = "sk-test-" + "x"*40
            save_cloud_key(key)
            self.assertEqual(cloud_key(), key)
            self.assertEqual((Path(tmp)/"credentials.json").stat().st_mode & 0o777, 0o600)
            self.assertNotIn(key, json.dumps(diagnostics({"provider": "openai", "chat_model": "test", "embedding_model": "test"})))

    def test_remote_local_engine_url_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, patch("backend.engine.data_dir", return_value=Path(tmp)):
            with self.assertRaises(ValueError): save_configuration({"ollama_url": "http://example.com"})


if __name__ == "__main__":
    unittest.main()
