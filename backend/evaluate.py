"""Reproducible, independently annotated synthetic smoke benchmark.

This is a controlled template suite, not evidence of general NLP ability. Twenty
percent of instances use challenging paraphrases to expose the local parser's
coverage limits. Gold assertions/answers are defined here, never by the engine.
"""
import argparse
import json
import random
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from .memory import Memory
from .extraction import key

LABELS = ["SAME", "SUPPORTS", "UPDATES", "CONTRADICTS", "SUPERSEDES", "UNRELATED"]
CATEGORIES = ["stable", "preference", "location", "correction", "cancellation", "replacement", "temporary", "additive", "rename", "ambiguous"]
BASE = "2026-01-01T12:00:00+00:00"
NEXT = "2026-01-08T12:00:00+00:00"
ASOF = "2026-01-09T12:00:00+00:00"


def dataset(count=600, seed=42):
    rng = random.Random(seed)
    cities = ["Hyderabad", "Chennai", "Pune", "Delhi", "Mumbai", "Kochi", "Jaipur", "Bengaluru", "Surat", "Lucknow"]
    languages = ["Python", "Rust", "Go", "Java", "TypeScript", "Kotlin"]
    for i in range(count):
        category = CATEGORIES[i % 10]
        challenge = (i // 10) % 5 == 4
        old, new = rng.sample(cities, 2)
        a, b = rng.sample(languages, 2)
        company, project = "Company %d" % (i+1), "Project %d" % (i+1)
        def gold(relation, value, subject="You"):
            return [subject, relation, value]
        expected, stale, changed, asof = None, [], True, ASOF
        if category == "stable":
            value = "%d May" % (i % 27 + 1)
            support = (i // 10) % 2 == 0
            turns = ["My birthday is %s." % value, ("I still confirm: " if challenge else "My birthday is ") + value + "."]
            if support and not challenge:
                turns[1] = "My birthday is still %s." % value
            facts = [[gold("birthday", value)], [gold("birthday", value)]]
            labels = [["UNRELATED"], ["SUPPORTS" if support else "SAME"]]
            question, expected, changed = "When is my birthday?", value, False
        elif category == "preference":
            turns = ["I prefer %s." % a, ("I've switched my preference to %s." if challenge else "I now prefer %s.") % b]
            facts, labels = [[gold("prefers", a)], [gold("prefers", b)]], [["UNRELATED"], ["SUPERSEDES"]]
            question, expected, stale = "What do I prefer?", b, [a]
        elif category == "location":
            turns = ["I live in %s." % old, ("I've relocated to %s." if challenge else "I moved to %s.") % new]
            facts, labels = [[gold("lives_in", old)], [gold("lives_in", new)]], [["UNRELATED"], ["SUPERSEDES"]]
            question, expected, stale = "Where do I live now?", new, [old]
        elif category == "correction":
            turns = ["My meeting is Tuesday.", "I got the date wrong; make that Wednesday." if challenge else "Correction: Wednesday."]
            facts, labels = [[gold("meeting_day", "Tuesday")], [gold("meeting_day", "Wednesday")]], [["UNRELATED"], ["UPDATES"]]
            question, expected, stale = "When is my meeting?", "Wednesday", ["Tuesday"]
        elif category == "cancellation":
            turns = ["I will visit %s." % old, "I've called off my visit." if challenge else "The trip is cancelled."]
            facts, labels = [[gold("plans_to", old)], [gold("plans_to", old)]], [["UNRELATED"], ["SUPERSEDES"]]
            question, expected, stale = "What trip do I have planned?", None, [old]
        elif category == "replacement":
            turns = ["I use an iPhone.", "I've traded my iPhone for a Pixel." if challenge else "I sold it and bought a Pixel."]
            facts, labels = [[gold("owns", "iPhone")], [gold("owns", "iPhone"), gold("owns", "Pixel")]], [["UNRELATED"], ["SUPERSEDES", "UNRELATED"]]
            question, expected, stale = "What phone do I use?", "Pixel", ["iPhone"]
        elif category == "temporary":
            expire = (i // 10) % 2 == 0
            turns = ["I live in %s." % old, ("I'm spending seven days in %s." if challenge else "I am in %s this week.") % new]
            facts, labels = [[gold("lives_in", old)], [gold("temporary_location", new)]], [["UNRELATED"], ["UNRELATED"]]
            question, expected = ("Where am I staying temporarily?", None) if expire else ("Where do I live?", old)
            stale = [new] if expire else []
            asof = "2026-01-20T12:00:00+00:00" if expire else ASOF
        elif category == "additive":
            turns = ["I work at %s." % company, ("I'm heading up %s." if challenge else "I lead %s.") % project]
            facts, labels = [[gold("works_at", company)], [gold("leads", project)]], [["UNRELATED"], ["UNRELATED"]]
            question, expected, changed = "Where do I work?", company, False
        elif category == "rename":
            turns = ["My dog is Bruno.", "Our dog goes by Milo from now on." if challenge else "We renamed him Milo."]
            facts, labels = [[gold("name", "Bruno", "Your dog")], [gold("name", "Milo", "Your dog")]], [["UNRELATED"], ["SUPERSEDES"]]
            question, expected, stale = "What is my dog's name?", "Milo", ["Bruno"]
        else:
            turns = ["I live in %s." % old, ("It's possible my residence is %s." if challenge else "Maybe I live in %s.") % new]
            facts, labels = [[gold("lives_in", old)], [gold("lives_in", new)]], [["UNRELATED"], ["CONTRADICTS"]]
            question, expected = "Where do I live?", "UNRESOLVED"
        preserved = facts[0] if category in ("stable", "temporary", "additive") else []
        yield {"id": "amnesia-%04d" % (i+1), "category": category, "split": "challenge" if challenge else "template", "turns": turns, "gold_assertions": facts, "gold_labels": labels, "question": question, "expected": expected, "stale_values": stale, "evolved": changed, "preserved": preserved, "as_of": asof, "seed": seed}


def run(count=600, seed=42, gold_inputs=False, progress=None, cancelled=None):
    start = time.perf_counter()
    methods = ["recent", "vector", "graph", "hybrid", "hybrid_no_temporal", "hybrid_no_graph"]
    tallies = {m: defaultdict(float) for m in methods}
    latencies = defaultdict(list)
    categories, splits = defaultdict(lambda: defaultdict(lambda: [0, 0])), defaultdict(lambda: defaultdict(lambda: [0, 0]))
    confusion = {label: Counter() for label in LABELS}
    extraction = Counter()
    failures = []
    safe_total, safe_retired, gate_tp, gate_fp, gate_fn = 0, 0, 0, 0, 0
    for index, item in enumerate(dataset(count, seed)):
        if cancelled and cancelled():
            return None
        mem = Memory()
        wid = mem.create_workspace(item["id"])
        sid = mem.rows("SELECT id FROM sessions WHERE workspace_id=?", (wid,))[0]["id"]
        results = []
        for idx, turn in enumerate(item["turns"]):
            batch = None
            if gold_inputs:
                batch = []
                for j, (subject, relation, value) in enumerate(item["gold_assertions"][idx]):
                    label = item["gold_labels"][idx][j]
                    intent = {"SAME": "assert", "SUPPORTS": "support", "UPDATES": "correct", "CONTRADICTS": "uncertain", "SUPERSEDES": "update", "UNRELATED": "assert"}[label]
                    if item["category"] == "cancellation" and idx == 1 or item["category"] == "replacement" and idx == 1 and j == 0:
                        intent = "cancel"
                    until = "2026-01-15T12:00:00+00:00" if relation == "temporary_location" else None
                    batch.append({"subject": subject, "relation": relation, "value": value, "intent": intent, "scope": "", "confidence": .58 if intent == "uncertain" else .96, "evidence": turn, "valid_until": until})
            result = mem.ingest(wid, sid, turn, BASE if idx == 0 else NEXT, assertion_batch=batch)
            results.append(result)
            predicted = Counter((d["subject"].casefold(), d["relation"], d["value"].casefold()) for d in result["decisions"])
            golds = Counter((s.casefold(), r, v.casefold()) for s, r, v in item["gold_assertions"][idx])
            extraction["tp"] += sum((predicted & golds).values())
            extraction["fp"] += sum((predicted - golds).values())
            extraction["fn"] += sum((golds - predicted).values())
            # Align by assertion index; missing extractions are explicit misses.
            for j, expected_label in enumerate(item["gold_labels"][idx]):
                actual = result["decisions"][j]["label"] if j < len(result["decisions"]) else "MISSING"
                confusion[expected_label][actual] += 1
        final = mem.state(wid, item["as_of"])["facts"]
        for subject, relation, value in item["preserved"]:
            safe_total += 1
            matching = [f for f in final if f["subject"] == subject and f["relation"] == relation and key(f["value"]) == key(value)]
            safe_retired += int(bool(matching) and any(f["status"] in ("superseded", "invalid") for f in matching))
        for method in methods:
            actual_method, weights = method, None
            if method.startswith("hybrid_no"):
                actual_method = "hybrid"
                weights = {"semantic": .4, "graph": 0 if method.endswith("graph") else .25, "temporal": 0 if method.endswith("temporal") else .2, "confidence": .15, "penalty": 0 if method.endswith("temporal") else .65}
                # no-temporal ablation also removes validity filtering.
                if method.endswith("temporal"):
                    original = mem.effective_status
                    mem.effective_status = lambda f, now, decisions: "active"
            answer = mem.query(wid, item["question"], method=actual_method, as_of=item["as_of"], k=5, weights=weights)
            if method == "hybrid_no_temporal":
                mem.effective_status = original
            correct = answer["answer_value"] == item["expected"]
            t = tallies[method]
            t["n"] += 1
            t["correct"] += correct
            t["evolved"] += item["evolved"]
            t["stale"] += item["evolved"] and answer["answer_value"] in item["stale_values"]
            gold_ids = {f["id"] for f in final if f["effective_status"] in ("active", "unresolved") and (f["value"] == item["expected"] or item["expected"] == "UNRESOLVED" and f["effective_status"] == "unresolved")}
            if gold_ids:
                t["retrieval_n"] += 1
                hit_ranks = [j+1 for j, f in enumerate(answer["retrieved"]) if f["id"] in gold_ids]
                t["recall"] += len(hit_ranks)/len(gold_ids)
                t["mrr"] += 1/min(hit_ranks) if hit_ranks else 0
            # Missing expected extraction must count as failed retrieval too.
            elif item["expected"] is not None:
                t["retrieval_n"] += 1
            latencies[method].append(answer["latency_ms"])
            t["tokens"] += answer["context_tokens_estimate"]
            categories[item["category"]][method][0] += correct
            categories[item["category"]][method][1] += 1
            splits[item["split"]][method][0] += correct
            splits[item["split"]][method][1] += 1
            if method == "hybrid" and not correct and len(failures) < 40:
                failures.append({"id": item["id"], "category": item["category"], "split": item["split"], "turns": item["turns"], "question": item["question"], "expected": item["expected"], "actual": answer["answer_value"], "unsupported": [u for r in results for u in r["unsupported"]]})
        for question, expected_gate in [(item["question"], True), ("Explain photosynthesis.", False)]:
            prediction = mem.query(wid, question)["memory_needed"]
            gate_tp += prediction and expected_gate
            gate_fp += prediction and not expected_gate
            gate_fn += not prediction and expected_gate
        mem.close()
        if progress:
            progress(index+1, count, "Policy case %d of %d" % (index+1, count))
    safe_div = lambda a, b: a/b if b else 0
    f1 = lambda p, r: safe_div(2*p*r, p+r)
    per_label = {}
    for label in LABELS:
        tp = confusion[label][label]
        precision = safe_div(tp, sum(row[label] for row in confusion.values()))
        recall = safe_div(tp, sum(confusion[label].values()))
        per_label[label] = {"precision": precision, "recall": recall, "f1": f1(precision, recall), "support": sum(confusion[label].values())}
    measures = {}
    for method, t in tallies.items():
        measures[method] = {"answer_accuracy": safe_div(t["correct"], t["n"]), "smer": safe_div(t["stale"], t["evolved"]), "recall_at_5": safe_div(t["recall"], t["retrieval_n"]), "mrr": safe_div(t["mrr"], t["retrieval_n"]), "mean_latency_ms": statistics.mean(latencies[method]), "p95_latency_ms": sorted(latencies[method])[int((len(latencies[method])-1)*.95)], "mean_context_tokens_estimate": safe_div(t["tokens"], t["n"]), "instances": int(t["n"]), "evolved_questions": int(t["evolved"]), "stale_answers": int(t["stale"])}
    ep, er = safe_div(extraction["tp"], extraction["tp"]+extraction["fp"]), safe_div(extraction["tp"], extraction["tp"]+extraction["fn"])
    gp, gr = safe_div(gate_tp, gate_tp+gate_fp), safe_div(gate_tp, gate_tp+gate_fn)
    return {"count": count, "seed": seed, "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(), "duration_ms": round((time.perf_counter()-start)*1000), "extractor": "bounded local grammar", "vector_representation": "sparse TF-IDF cosine; not dense semantic embeddings", "answer_engine": "shared evidence template (no LLM)", "limitations": ["Synthetic template smoke test; 20% challenging paraphrases, no natural-conversation validation.", "Exact-match answers and a shared deterministic evidence reader; not an LLM QA comparison.", "Recent baseline ranks extracted assertions by insertion order; it is not a full-context LLM.", "FIR covers gold preserved facts in stable/additive/temporary scenarios; missing extraction is counted separately.", "Recall denominator excludes no-evidence answers; missing expected evidence counts as a miss.", "Latency is in-process elapsed time including SQLite reads; no network or LLM costs.", "No-temporal ablation removes lifecycle filters and penalties; no-graph removes graph weight only."], "metrics": measures, "extraction": {"precision": ep, "recall": er, "f1": f1(ep, er), **dict(extraction)}, "reconciliation": {"accuracy": safe_div(sum(confusion[l][l] for l in LABELS), sum(sum(r.values()) for r in confusion.values())), "macro_f1": statistics.mean(r["f1"] for r in per_label.values()), "per_label": per_label, "confusion": {l: dict(v) for l, v in confusion.items()}}, "false_invalidation": {"rate": safe_div(safe_retired, safe_total), "retired": safe_retired, "considered": safe_total}, "gate": {"precision": gp, "recall": gr, "f1": f1(gp, gr)}, "categories": {c: {m: {"accuracy": safe_div(v[0], v[1]), "n": v[1]} for m, v in row.items()} for c, row in categories.items()}, "splits": {c: {m: {"accuracy": safe_div(v[0], v[1]), "n": v[1]} for m, v in row.items()} for c, row in splits.items()}, "failures": failures}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=600)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default="output/evaluation.json")
    parser.add_argument("--gold", action="store_true", help="Use gold assertions to isolate reconciliation and retrieval")
    args = parser.parse_args()
    if not 10 <= args.count <= 2000 or args.count % 10:
        parser.error("count must be a multiple of 10 between 10 and 2000")
    report = run(args.count, args.seed, gold_inputs=args.gold)
    report.update(suite="policy" if args.gold else "offline_regression", title="Gold-assertion policy and retrieval" if args.gold else "Offline bounded-parser regression")
    if args.gold:
        report["extractor"] = "Gold annotated assertions (extraction isolated)"
        report["limitations"] = ["Gold inputs isolate policy and retrieval; this is not a measurement of natural-language extraction.", "Synthetic controlled set, not an external blind benchmark.", "Evidence-template answering; live LLM results are reported separately."] + report["limitations"][3:]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    with out.with_suffix(".jsonl").open("w") as stream:
        for item in dataset(args.count, args.seed):
            stream.write(json.dumps(item)+"\n")
    print(json.dumps({"report": str(out), "instances": args.count, "metrics": report["metrics"], "extraction_f1": report["extraction"]["f1"]}, indent=2))
