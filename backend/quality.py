"""Live, auditable end-to-end AI evaluation, including a full-context LLM baseline."""
import argparse
import json
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .benchmark_data import natural_cases
from .engine import configuration, consume_trace, diagnostics, data_dir
from .evaluate import LABELS
from .extraction import iso, scope_for
from .memory import Memory

METHODS = ("context", "vector", "graph", "hybrid")


def normalize(value):
    if value is None:
        return "__none__"
    value = str(value).casefold().strip().replace("14th", "14")
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return "14 may" if value == "may 14" else value


def signature(fact):
    return (normalize(fact["subject"]), fact["relation"], normalize(fact["value"]))


def evaluate_ai(question_count=60, config=None, progress=None, cancelled=None, cache=True):
    config = config or configuration()
    if config["provider"] == "offline" or not diagnostics(config)["ready"]:
        raise ValueError("Live AI evaluation needs a ready language and embedding model. Open AI engine first.")
    if question_count not in (20, 60):
        raise ValueError("Choose 20 or 60 curated live-AI questions.")
    cases = natural_cases()[:10] if question_count == 20 else natural_cases()
    total = len(cases)*2 + question_count*len(METHODS)
    progress = progress or (lambda completed, total, message: None)
    cancelled = cancelled or (lambda: False)
    started, completed = time.perf_counter(), 0
    confusion = {label: Counter() for label in LABELS}
    extraction = Counter()
    metrics = {m: defaultdict(float) for m in METHODS}
    per_category = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    latencies = defaultdict(list)
    records, failures, calls, extraction_records = [], [], [], []
    safe_total, safe_retired, errors = 0, 0, []
    for case in cases:
        if cancelled():
            return None
        mem = Memory()
        wid = mem.create_workspace(case["id"])
        initial = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        try:
            for turn_index, turn in enumerate(case["turns"]):
                if cancelled():
                    return None
                sid = mem.rows("SELECT id FROM sessions WHERE workspace_id=? ORDER BY rowid DESC", (wid,))[0]["id"] if turn_index == 0 else mem.create_session(wid)
                consume_trace()
                try:
                    result = mem.ingest(wid, sid, turn, iso(initial + timedelta(days=turn_index)), provider="ai", config=config, cache=cache)
                except ValueError as exc:
                    result = {"decisions": [], "unsupported": [str(exc)]}
                    errors.append({"case": case["id"], "stage": "extraction", "error": str(exc)})
                calls.extend(consume_trace())
                predicted = Counter(signature(f) for f in result["decisions"])
                gold = Counter(signature(f) for f in case["gold_assertions"][turn_index])
                extraction.update(tp=sum((predicted & gold).values()), fp=sum((predicted - gold).values()), fn=sum((gold - predicted).values()))
                # Align by assertion identity, rather than arbitrary extraction order.
                actual = {signature(d): d["label"] for d in result["decisions"]}
                extraction_records.append({"case": case["id"], "turn_index": turn_index, "turn": turn, "predicted": result["decisions"], "gold": case["gold_assertions"][turn_index], "gold_labels": case["gold_labels"][turn_index], "unsupported": result.get("unsupported", [])})
                for fact, label in zip(case["gold_assertions"][turn_index], case["gold_labels"][turn_index]):
                    confusion[label][actual.get(signature(fact), "MISSING")] += 1
                completed += 1
                progress(completed, total, "%s · extracting session %d" % (case["id"], turn_index+1))
            state = mem.state(wid, "2026-01-03T12:00:00+00:00")
            for preserved in case["preserved"]:
                safe_total += 1
                found = [f for f in state["facts"] if signature(f) == signature(preserved)]
                safe_retired += int(bool(found) and any(f["status"] in ("invalid", "superseded") for f in found))
            for q_index, question in enumerate(case["questions"]):
                for method in METHODS:
                    if cancelled():
                        return None
                    consume_trace()
                    error = None
                    try:
                        answer = mem.query(wid, question["text"], method=method, as_of="2026-01-03T12:00:00+00:00", k=3, config=config, cache=cache)
                        actual_value = answer["answer_value"]
                        expected_values = [question["expected"]] + question["aliases"]
                        correct = any(normalize(actual_value) == normalize(v) for v in expected_values)
                    except ValueError as exc:
                        error = str(exc)
                        answer = {"answer": error, "answer_value": None, "used_ids": [], "retrieved": [], "latency_ms": 0, "context_tokens_estimate": 0}
                        actual_value, correct = None, False
                        errors.append({"case": case["id"], "stage": method, "error": error})
                    calls.extend(consume_trace())
                    stale = question["evolved"] and any(normalize(actual_value) == normalize(v) for v in question["stale"])
                    t = metrics[method]
                    t["n"] += 1; t["correct"] += correct; t["evolved"] += question["evolved"]; t["stale"] += stale; t["errors"] += bool(error)
                    target_groups = []
                    for target in question["targets"]:
                        matches = {f["id"] for f in state["facts"] if signature(f) == signature(target) and (target["intent"] != "cancel" or f.get("intent") == "cancel")}
                        target_groups.append(matches)
                    retrieved_ids = [f["id"] for f in answer["retrieved"]]
                    if method == "context":
                        retrieved_ids = [f["id"] for f in state["facts"] if f["event_id"] in {e["id"] for e in answer.get("context_events", [])}]
                    hits = [any(fid in retrieved_ids for fid in group) for group in target_groups]
                    hit_ranks = [i+1 for i, fid in enumerate(retrieved_ids) if any(fid in group for group in target_groups)]
                    t["recall"] += sum(hits)/max(1, len(hits))
                    t["mrr"] += 1/min(hit_ranks) if hit_ranks else 0
                    t["tokens"] += answer["context_tokens_estimate"]
                    latencies[method].append(answer["latency_ms"])
                    per_category[case["category"]][method][0] += correct
                    per_category[case["category"]][method][1] += 1
                    row = {"id": "%s-q%d" % (case["id"], q_index+1), "category": case["category"], "method": method, "turns": case["turns"], "question": question["text"], "expected": question["expected"], "actual": actual_value, "answer": answer["answer"], "correct": correct, "stale": stale, "used_ids": answer["used_ids"], "latency_ms": answer["latency_ms"], "error": error}
                    records.append(row)
                    if method == "hybrid" and not correct:
                        failures.append(row)
                    completed += 1
                    progress(completed, total, "%s · %s · question %d" % (case["id"], method, q_index+1))
        finally:
            mem.close()
    div = lambda a, b: a/b if b else 0
    f1 = lambda p, r: div(2*p*r, p+r)
    per_label = {}
    for label in LABELS:
        tp = confusion[label][label]
        p, r = div(tp, sum(row[label] for row in confusion.values())), div(tp, sum(confusion[label].values()))
        per_label[label] = {"precision": p, "recall": r, "f1": f1(p, r), "support": sum(confusion[label].values())}
    summary = {}
    for method, t in metrics.items():
        summary[method] = {"answer_accuracy": div(t["correct"], t["n"]), "smer": div(t["stale"], t["evolved"]), "recall_at_5": div(t["recall"], t["n"]), "mrr": div(t["mrr"], t["n"]), "mean_latency_ms": statistics.mean(latencies[method]), "p95_latency_ms": sorted(latencies[method])[int((len(latencies[method])-1)*.95)], "mean_context_tokens_estimate": div(t["tokens"], t["n"]), "instances": int(t["n"]), "evolved_questions": int(t["evolved"]), "stale_answers": int(t["stale"]), "errors": int(t["errors"])}
    ep, er = div(extraction["tp"], extraction["tp"]+extraction["fp"]), div(extraction["tp"], extraction["tp"]+extraction["fn"])
    report = {"suite": "live_ai", "title": "Curated natural-language end-to-end AI", "count": question_count, "cases": len(cases), "seed": 42, "generated_at": datetime.now(timezone.utc).isoformat(), "duration_ms": round((time.perf_counter()-started)*1000), "engine": config, "metrics": summary, "retrieval_k": 3, "extractor": config["chat_model"], "vector_representation": config["embedding_model"], "answer_engine": "same live LLM for all methods", "extraction": {"precision": ep, "recall": er, "f1": f1(ep, er), **dict(extraction)}, "reconciliation": {"accuracy": div(sum(confusion[l][l] for l in LABELS), sum(sum(v.values()) for v in confusion.values())), "macro_f1": statistics.mean(v["f1"] for v in per_label.values() if v["support"]), "per_label": per_label, "confusion": {l: dict(v) for l, v in confusion.items()}}, "false_invalidation": {"rate": div(safe_retired, safe_total), "retired": safe_retired, "considered": safe_total}, "gate": None, "categories": {c: {m: {"accuracy": div(v[0], v[1]), "n": v[1]} for m, v in methods.items()} for c, methods in per_category.items()}, "splits": {"curated": {m: {"accuracy": summary[m]["answer_accuracy"], "n": question_count} for m in METHODS}}, "failures": failures, "records": records, "extraction_records": extraction_records, "labels_evaluated": [l for l in LABELS if per_label[l]["support"]], "absent_labels": [l for l in LABELS if not per_label[l]["support"]], "provider_calls": len(calls), "cache_hits": sum(c["cache_hit"] for c in calls), "measured_live_calls": sum(not c["cache_hit"] for c in calls), "actual_input_tokens": sum(c.get("input_tokens", 0) for c in calls if not c["cache_hit"]), "actual_output_tokens": sum(c.get("output_tokens", 0) for c in calls if not c["cache_hit"]), "errors": errors, "limitations": ["Curated internal set authored with explicit gold annotations; not a blind external or third-party human benchmark.", "The live set does not exercise SAME transitions; that label is evaluated in the gold-input policy suite.", "Only 20 or 60 questions; results have substantial sampling uncertainty and are not general-performance claims.", "All methods share the same live extractor and LLM reader. The full-context baseline receives raw user turns.", "Vector and graph methods do not receive reconciliation states; hybrid does. Graph uses personalized PageRank.", "Retrieval uses K=3; the legacy recall_at_5 field is retained for UI compatibility and must be labeled Recall@3 for this suite.", "Latency includes model inference and embedding-cache reads. Cache-hit counts are reported; cached calls are not cold inference measurements.", "Answer values are normalized exact matches with declared gold aliases. No unreported model judge is used.", "Model errors count as incorrect answers. Negative/cancellation evidence remains auditable."]}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--questions", type=int, choices=(20, 60), default=60)
    parser.add_argument("--output", default=None)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    def progress(done, total, message):
        print(json.dumps({"completed": done, "total": total, "message": message}), flush=True)
    report = evaluate_ai(args.questions, progress=progress, cache=not args.no_cache)
    provider = report["engine"]["provider"]
    filename = {"codex": "evaluation-codex.json", "openai": "evaluation-openai.json", "ollama": "evaluation-ollama-final.json"}[provider]
    file = Path(args.output or ("output/"+filename)); file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(report, indent=2))
    file.with_suffix(".jsonl").write_text("".join(json.dumps(c)+"\n" for c in natural_cases()[:10 if args.questions == 20 else 30]))
    folder = data_dir() / "reports"; folder.mkdir(parents=True, exist_ok=True)
    latest = folder / "live_ai.tmp"; latest.write_text(json.dumps(report, indent=2)); latest.replace(folder / "live_ai.json")
    print(json.dumps({"report": str(file), "metrics": report["metrics"], "errors": len(report["errors"])}), flush=True)
