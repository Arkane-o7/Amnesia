import json
import tempfile
import unittest
from pathlib import Path
from backend.memory import Memory, SCENARIOS, load_scenario
from backend.evaluate import dataset, run

T0, T1, T2, T3 = ["2026-01-%02dT12:00:00+00:00" % d for d in (1, 2, 3, 15)]


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.mem = Memory()
        self.wid = self.mem.create_workspace("Test")
        self.sid = self.mem.rows("SELECT id FROM sessions WHERE workspace_id=?", (self.wid,))[0]["id"]

    def tearDown(self):
        self.mem.close()

    def add(self, text, at=T0):
        return self.mem.ingest(self.wid, self.sid, text, at)

    def ask(self, q, **kwargs):
        return self.mem.query(self.wid, q, **kwargs)

    def test_location_update_retains_history_and_retrieves_current(self):
        self.add("I live in Hyderabad.")
        decision = self.add("I moved to Chennai.", T1)["decisions"][0]
        facts = self.mem.facts(self.wid)
        self.assertEqual(decision["label"], "SUPERSEDES")
        self.assertEqual(facts[0]["status"], "superseded")
        self.assertEqual(facts[0]["superseded_by"], facts[1]["id"])
        self.assertEqual(facts[0]["valid_until"], T1)
        answer = self.ask("Where do I live now?", as_of=T2)
        self.assertEqual(answer["answer_value"], "Chennai")
        self.assertFalse(next(f for f in answer["candidates"] if f["value"] == "Hyderabad")["eligible"])

    def test_historical_snapshot_reconstructs_previous_belief(self):
        self.add("I live in Hyderabad.")
        self.add("I moved to Chennai.", T1)
        self.assertEqual(self.ask("Where do I live?", as_of=T0)["answer_value"], "Hyderabad")
        self.assertEqual(self.ask("Where do I live?", as_of=T1)["answer_value"], "Chennai")
        self.assertIsNone(self.ask("Where do I live?", as_of="2025-12-01")["answer_value"])

    def test_additive_relations_are_not_invalidated(self):
        self.add("I work at Company X.")
        self.add("I lead Project Y.", T1)
        self.assertTrue(all(f["status"] == "active" for f in self.mem.facts(self.wid)))
        self.assertEqual(self.ask("Where do I work?")["answer_value"], "Company X")
        self.assertEqual(self.ask("What project do I lead?")["answer_value"], "Project Y")

    def test_duplicates_attach_provenance_without_new_edges(self):
        self.add("I live in Hyderabad.")
        self.assertEqual(self.add("I live in hyderabad.", T1)["decisions"][0]["label"], "SAME")
        self.assertEqual(self.add("I still live in Hyderabad.", T2)["decisions"][0]["label"], "SUPPORTS")
        state = self.mem.state(self.wid)
        self.assertEqual(len(state["facts"]), 1)
        self.assertEqual(state["facts"][0]["evidence_count"], 3)

    def test_uncertain_conflict_requires_clarification(self):
        self.add("I live in Pune.")
        self.add("Maybe I live in Mumbai.", T1)
        self.assertEqual(self.ask("Where do I live?", as_of=T2)["answer_value"], "UNRESOLVED")
        self.assertEqual(self.ask("Where do I live?", as_of=T0)["answer_value"], "Pune")
        self.assertTrue(all(f["status"] == "unresolved" for f in self.mem.facts(self.wid)))
        self.add("Actually, I live in Pune.", T2)
        self.assertEqual(self.ask("Where do I live?")["answer_value"], "Pune")

    def test_uncued_incompatible_claim_is_not_assumed_update(self):
        self.add("I live in Pune.")
        result = self.add("I live in Mumbai.", T1)
        self.assertEqual(result["decisions"][0]["label"], "CONTRADICTS")
        self.assertEqual(self.ask("Where do I live?")["answer_value"], "UNRESOLVED")

    def test_correction_is_invalid_and_history_remains(self):
        self.add("My meeting is Tuesday.")
        result = self.add("Correction: Wednesday.", T1)
        self.assertEqual(result["decisions"][0]["label"], "UPDATES")
        self.assertEqual(self.mem.facts(self.wid)[0]["status"], "invalid")
        self.assertEqual(self.ask("When is my meeting?")["answer_value"], "Wednesday")
        self.assertEqual(self.ask("When is my meeting?", as_of=T0)["answer_value"], "Tuesday")

    def test_cancellation_does_not_answer_as_active_plan(self):
        self.add("I will visit Mumbai.")
        self.add("The trip is cancelled.", T1)
        self.assertIsNone(self.ask("What trip do I have planned?")["answer_value"])
        self.assertTrue(all(f["status"] == "invalid" for f in self.mem.facts(self.wid)))

    def test_uncertain_cancellation_does_not_invalidate(self):
        self.add("I will visit Mumbai.")
        self.add("Maybe the trip is cancelled.", T1)
        self.assertFalse(any(f["status"] == "invalid" for f in self.mem.facts(self.wid)))
        self.assertEqual(self.ask("What trip do I have planned?")["answer_value"], "UNRESOLVED")

    def test_scoped_cancellation_preserves_other_plans(self):
        self.add("I will visit Mumbai. I will visit Pune.")
        result = self.add("The trip is cancelled.", T1)
        self.assertEqual(result["assertions"], 0)
        self.add("The trip to Mumbai is cancelled.", T2)
        current = [f for f in self.mem.facts(self.wid) if f["status"] == "active"]
        self.assertEqual([f["value"] for f in current], ["Pune"])

    def test_temporary_stay_expires_without_changing_home(self):
        self.add("I live in Hyderabad.")
        self.add("I am in Delhi this week.", T1)
        self.assertEqual(self.ask("Where do I live?", as_of=T2)["answer_value"], "Hyderabad")
        self.assertEqual(self.ask("Where am I staying temporarily?", as_of=T2)["answer_value"], "Delhi")
        self.assertIsNone(self.ask("Where am I staying temporarily?", as_of=T3)["answer_value"])
        self.assertEqual(self.ask("Where do I live?", as_of=T3)["answer_value"], "Hyderabad")

    def test_ownership_can_be_additive_then_explicitly_replaced(self):
        self.add("I use an iPhone.")
        self.add("I own a MacBook.", T1)
        self.assertEqual(len([f for f in self.mem.facts(self.wid) if f["status"] == "active"]), 2)
        self.add("I sold my iPhone.", T2)
        self.assertEqual([f["value"] for f in self.mem.facts(self.wid) if f["status"] == "active"], ["MacBook"])

    def test_explicit_device_replacement(self):
        self.add("I use an iPhone.")
        result = self.add("I sold it and bought a Pixel.", T1)
        self.assertEqual(result["assertions"], 2)
        self.assertEqual(self.ask("What phone do I use?")["answer_value"], "Pixel")

    def test_pet_rename_keeps_entity_identity(self):
        self.add("My dog is Bruno.")
        self.add("We renamed him Milo.", T1)
        facts = self.mem.facts(self.wid)
        self.assertEqual(facts[0]["subject_id"], facts[1]["subject_id"])
        self.assertEqual(self.ask("What is my dog's name?")["answer_value"], "Milo")

    def test_unsupported_input_is_recorded_without_inventing_facts(self):
        result = self.add("The moon reminds me of summer.")
        self.assertEqual(result["assertions"], 0)
        self.assertEqual(len(result["unsupported"]), 1)
        self.assertEqual(len(self.mem.state(self.wid)["events"]), 1)

    def test_unknown_question_abstains_instead_of_answering_with_unrelated_fact(self):
        self.add("I live in Hyderabad.")
        self.assertIsNone(self.ask("What is my bank PIN?")["answer_value"])
        self.assertEqual(self.ask("What do you remember about me?")["used_ids"], [self.mem.facts(self.wid)[0]["id"]])

    def test_memory_gate_and_vector_baseline_are_observable(self):
        self.add("I live in Hyderabad.")
        self.add("I moved to Chennai.", T1)
        self.assertTrue(self.ask("Explain photosynthesis.")["gate_bypassed"])
        self.assertEqual(self.ask("Explain photosynthesis.")["retrieved"], [])
        self.assertTrue(self.ask("Why do people live in cities?")["gate_bypassed"])
        vector = self.ask("Where do I live?", method="vector")
        self.assertEqual(len(vector["retrieved"]), 2)
        self.assertTrue(any(f["effective_status"] == "superseded" for f in vector["retrieved"]))

    def test_workspace_session_isolation_and_invalid_inputs(self):
        other = self.mem.create_workspace("Other")
        with self.assertRaises(ValueError): self.mem.ingest(other, self.sid, "I live in Pune.")
        with self.assertRaises(ValueError): self.add("")
        self.add("I live in Pune.", T2)
        with self.assertRaises(ValueError): self.add("I moved to Mumbai.", T0)
        self.assertEqual(self.mem.facts(other), [])

    def test_all_guided_scenarios_execute(self):
        for name in SCENARIOS:
            wid = load_scenario(self.mem, name)
            self.assertGreaterEqual(len(self.mem.facts(wid)), 2)

    def test_file_persistence_after_reopening(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.db"
            first = Memory(path)
            wid = first.create_workspace("Persistent")
            sid = first.rows("SELECT id FROM sessions WHERE workspace_id=?", (wid,))[0]["id"]
            first.ingest(wid, sid, "I live in Chennai.", T0)
            first.close()
            second = Memory(path)
            self.assertEqual(second.query(wid, "Where do I live?")["answer_value"], "Chennai")
            second.close()


class EvaluationTests(unittest.TestCase):
    def test_dataset_is_seeded_balanced_and_gold_independent(self):
        a, b = list(dataset(100, 42)), list(dataset(100, 42))
        self.assertEqual(a, b)
        self.assertEqual(sum(x["split"] == "challenge" for x in a), 20)
        self.assertEqual(len({x["category"] for x in a}), 10)
        self.assertNotEqual(a, list(dataset(100, 43)))

    def test_measured_metrics_expose_coverage_failures(self):
        report = run(100)
        self.assertEqual(report["count"], 100)
        self.assertEqual(report["splits"]["template"]["hybrid"]["accuracy"], 1)
        self.assertLess(report["splits"]["challenge"]["hybrid"]["accuracy"], 1)
        self.assertGreater(report["metrics"]["hybrid"]["answer_accuracy"], report["metrics"]["vector"]["answer_accuracy"])
        self.assertEqual(report["false_invalidation"]["retired"], 0)
        self.assertGreater(report["false_invalidation"]["considered"], 0)
        self.assertTrue(report["failures"])
        json.dumps(report)


if __name__ == "__main__":
    unittest.main()
