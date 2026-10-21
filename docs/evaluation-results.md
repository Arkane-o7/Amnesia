# Measured final-review results

Measured on 14 October 2026. The primary product engine now uses the existing Codex ChatGPT login with local Nomic embeddings. The earlier full local run below remains labeled Ollama; the separate Codex-login run is recorded independently. Direct OpenAI API evaluation is optional and has not been performed.

## Gold-input policy suite

600 seeded synthetic questions (60 per category), gold assertions, and deterministic evidence-template answers. This isolates policy/retrieval; it does not measure natural-language extraction.

| Method | Exact QA | SMER | Recall@5 | MRR |
|---|---:|---:|---:|---:|
| Recent assertions | 75.0% | 18.8% | 100.0% | 0.912 |
| Vector | 25.0% | 81.2% | 100.0% | 0.686 |
| Graph | 25.0% | 81.2% | 100.0% | 0.686 |
| Amnesia hybrid | 100.0% | 0.0% | 100.0% | 1.000 |
| Without temporal policy | 25.0% | 81.2% | 100.0% | 0.686 |
| Without graph weight | 100.0% | 0.0% | 100.0% | 1.000 |

Reconciliation macro-F1: 100.0%. False invalidation: 0/180. The no-graph ablation matches hybrid; this suite does not establish a graph-scoring advantage.

## Codex-login integration run

Provider: **Codex CLI / ChatGPT login**. Model: **gpt-5.6-sol**; reasoning effort low, temperature not exposed. Embeddings: **local nomic-embed-text:latest**. Ten two-session scenarios, **20 questions**, all ten categories, K=3. This is the shorter integration run, separate from the 60-question local run below.

| Method | Exact QA | SMER | Recall@3 | MRR | Mean query ms |
|---|---:|---:|---:|---:|---:|
| Full-context LLM | 95.0% | 0.0% | 95.0% | 0.529 | 6581.6 |
| Vector | 95.0% | 0.0% | 90.0% | 0.875 | 6891.5 |
| Graph | 90.0% | 0.0% | 90.0% | 0.800 | 2583.7 |
| Amnesia hybrid | 100.0% | 0.0% | 95.0% | 0.925 | 6104.8 |

Extraction F1: **93.33%** (28 correct, 2 extra, 2 missing). Reconciliation macro-F1 over labels with support: **97.29%**. FIR: **0/11**. No provider/validation errors.

Measured duration **610.4s**, **87 live LLM calls**, **12 cache hits**, **694,950 input / 4,625 output tokens**. Latency includes CLI startup and harness overhead; timings include cache hits and are not cold-inference claims. Calls consume Codex plan usage. No API key or copied Codex token is used.

Hybrid answered 20/20 exact values correctly, with an approximate 95% Wilson interval of 83.9-100%. All methods had 0/7 stale-value errors, so this run does not establish an SMER advantage. Full context and graph selected Hyderabad when the correct behavior was to retain an unresolved conflict; vector/graph also abstained on a device question. The two extraction mismatches used “trip to Hyderabad” instead of the annotated “Hyderabad”. These remain in the raw audit, even though hybrid QA was correct.

This small internally curated run does not establish general performance, statistical superiority, or a 60-question Codex result. Raw report: output/evaluation-codex.json.

## Live local-model suite

Provider: **Ollama**. Language model: **qwen3.5:9b**. Embeddings: **nomic-embed-text:latest**. Temperature 0. Thirty developer-curated two-session scenarios, 60 questions, K=3. Same actual LLM reader for all methods; full context receives raw conversation turns.

| Method | Exact QA | SMER | Recall@3 | MRR | Mean query ms |
|---|---:|---:|---:|---:|---:|
| Full-context LLM | 95.0% | 0.0% | 95.0% | 0.529 | 2498.1 |
| Vector | 90.0% | 0.0% | 95.0% | 0.900 | 2654.7 |
| Graph | 93.3% | 0.0% | 91.7% | 0.700 | 1452.5 |
| Amnesia hybrid | 100.0% | 0.0% | 95.0% | 0.892 | 2251.5 |

Extraction precision/recall/F1: **90.0%** (81 correct, 9 extra, 9 missing gold assertions). Reconciliation macro-F1: **94.51%**, averaged over the five labels with support; SAME is absent. False invalidation: **0/33**.

Run duration 559.4s. **197 live LLM calls and 100 cache hits**; 135,780 input and 5,893 output tokens reported by the live model calls. Mean times include this cache behavior and are not cold-inference measurements. Embedding requests/cache behavior are not counted as LLM calls.

Hybrid answered 60/60 exact values correctly on this internal set. All methods had 0/21 stale-value errors; this run therefore does not establish a live SMER advantage. Full-context/vector/graph misses include uncertainty or concise-value selection errors. Hybrid 95% Wilson interval is approximately 94.0-100.0%; no statistical superiority claim is made.

## Errors and interpretation

- Extraction still produced destination labels such as “trip to Hyderabad” instead of “Hyderabad”, omitted some explicit sale assertions, and added pet-ownership assertions. The JSON extraction audit preserves these errors even when the final answer was correct.
- No hybrid QA failures or provider/validation errors were recorded in the selected completed local run.
- The policy suite is favorable to the designed lifecycle rules. Its perfect results do not generalize to live extraction.
- Inputs are internally curated development data, not an external blind or third-party annotated benchmark. Prompts and validation were refined during development.
- Citation IDs are checked, but semantic entailment is not formally guaranteed. Confidence is not calibrated.
- Recall for the full-context method measures gold evidence coverage in retained raw turns; it is not top-K retrieval. The legacy JSON key recall_at_5 represents Recall@3 in the live suite.
- Earlier v0.1 and intermediate development artifacts in output/ are retained for history; this document and the release use evaluation-policy.json and evaluation-ollama-final.json.

## Reproduce

```sh
npm run evaluate
AMNESIA_DATA_DIR=.amnesia-preview AMNESIA_PROVIDER=ollama AMNESIA_MODEL=qwen3.5:9b AMNESIA_EMBEDDING_MODEL=nomic-embed-text:latest python3 -m backend.quality --questions 60 --output output/evaluation-ollama-final.json
# Codex login with local embeddings:
python3 -m backend.quality --questions 20 --output output/evaluation-codex.json
```

Gold annotations: data/policy-gold-600.jsonl and data/live-ai-gold-30.jsonl. Raw results retain per-method answers, extraction records, confusion counts, cache metadata, and failures.
