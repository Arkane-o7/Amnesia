# Amnesia · final-review application

**An evolving knowledge graph agent for long-term AI memory.** Prepared for Abhilaksh Chauhan, Vellore Institute of Technology.

Amnesia extracts facts from conversations, reconciles changes within an entity/relation scope, preserves earlier evidence, and answers across sessions using dense semantic retrieval, personalized PageRank, and temporal lifecycle state. It includes a memory studio, searchable ledger, engine setup, experiments, backup restoration, a seven-step live review, and a generated academic report.

## Start the review

Requirements: **Python 3.9+ and Node.js 20.19+**. The application backend uses only the Python standard library. The review archive includes the compiled frontend.

```sh
# In the project directory:
npm run review
```

On macOS, you can also double-click **Start Amnesia.command**. The launcher reuses this project's running server or selects an available localhost port without stopping other apps. Open the printed URL, normally `http://127.0.0.1:8788/#review` on this machine. Stop a newly launched server with Ctrl+C in its terminal.

For a source-only checkout, build first:

```sh
npm install
npm run build
npm run review
```

For development, use `npm run dev`. It starts the Python API and Vite on available local ports. `npm start` serves the compiled app directly. Both bind to loopback.

## Use your Codex login

The default engine is **Codex · ChatGPT login**. The official Codex CLI performs structured fact extraction and answering through your existing ChatGPT sign-in. **No API key is needed in this mode.** Amnesia never opens or copies Codex credential files; the CLI owns authentication and token renewal.

Requirements: official **Codex CLI 0.149.1 or newer**, a ChatGPT login with Codex access, Ollama, and the installed **nomic-embed-text:latest** model for local dense embeddings. The tested language model is **gpt-5.6-sol**, with reasoning effort low. Temperature is not exposed by this adapter.

```sh
codex login status
# If not signed in with ChatGPT:
codex login
# If local embeddings are not already running:
npm run models:start
```

Open **AI engine**, choose **Codex · ChatGPT login**, and click **Save & test engine**. It checks actual Codex language inference and local embeddings. The review launcher starts Amnesia's private Ollama endpoint on port 11435 when needed; it reuses installed model files and does not download models automatically.

Codex calls send the supplied conversation/evidence to OpenAI and consume your Codex plan usage. Each request is a bounded `codex exec` invocation with structured JSON output, an ephemeral read-only working directory, and command, browser, app, hook, and delegation tools disabled. CLI startup and harness overhead are included in measured latency and token totals. The graph, source history, and embeddings stay on this Mac. This is a local application integration, not a public multi-user OAuth service.

See official [Codex authentication](https://learn.chatgpt.com/docs/auth) and [non-interactive structured-output documentation](https://learn.chatgpt.com/docs/non-interactive-mode).

**Fully local backup:** select **Local AI · Ollama**, with installed `qwen3.5:9b` and `nomic-embed-text:latest` models. After setup, this mode can run without internet. **Offline rules** is a bounded regression mode, explicitly labeled.

**Optional OpenAI API:** choose OpenAI API, enter a separate API key, and Save & test engine. Defaults for that provider are `gpt-4.1-mini` and `text-embedding-3-small`. The key is stored only in `.amnesia/credentials.json` with owner-only permissions and is excluded from exports/releases. API billing is separate from Codex login. Exported `OPENAI_API_KEY` is supported; `.env` files are not automatically loaded. Errors never silently switch providers.

## Present it

Open **Final review** and start the live walkthrough. It creates a separate workspace and executes actual model calls:

1. Extract home and programming-language preference from conversational prose.
2. Move to Chennai and switch to Rust; show earlier values retained as history.
3. Compare real hybrid, vector, and full-context LLM answers with inspectable evidence.
4. Add employer, project, and beverage preference without retiring compatible facts.
5. Introduce an uncertain move; show unresolved alternatives and request clarification.
6. Explicitly confirm Chennai and inspect the recorded resolution.
7. Show saved policy and live-AI measurements, including failures and limitations.

The vector walkthrough uses top-1 retrieval as a stress demonstration. The live benchmark uses top-3 for all retrieval methods. A vector answer is not guaranteed to fail; report the actual outcome shown.

See [docs/demo-guide.md](docs/demo-guide.md) for a timed script and viva answers, and [output/pdf/amnesia-final-report.pdf](output/pdf/amnesia-final-report.pdf) for the report.

Review materials committed with the source:

- [Final editorial PowerPoint](output/presentation/Amnesia-Final-Review-Editorial.pptx)
- [Successful screen recording](output/demo-recording-2026-10-21/final/Amnesia-live-demo.mp4) and [demo verification](output/demo-recording-2026-10-21/final/verification.json)
- [Evaluation CSV exports](output/csv/README.txt) and the original policy, local-model, and Codex result files under `output/`
- [Reliability checks from 21 October 2026](output/reliability-2026-10-21/checks.csv)

The successful recording uses **gpt-5.6-luna through Codex login** with synthetic example statements. It was recorded after the original `gpt-5.6-sol` model returned rate limits. Select that available model in AI engine to reproduce this configuration. The saved Codex benchmark and deck results remain the earlier **gpt-5.6-sol** measurements; the recording is not a new benchmark run. Runtime credentials, personal memory databases, temporary presentation builds, and raw recording frames are excluded from Git.

## Failure recovery

Codex requests have a 120-second execution budget and at most two attempts for recognized temporary transport/server failures. Rate limits receive an explicit 429 message and a five-second retry delay; other temporary failures use a one-second delay. Authentication, exhausted quota, configuration, invalid output, tool actions, and unclassified failures are not automatically retried. A recovered stream warning is accepted only when the process exits successfully, the final terminal event is completed, and a complete JSON object is returned; extraction/answer validation still runs afterward.

Private, rotating diagnostics are saved under `.amnesia/diagnostics/codex.jsonl` (or the configured data directory). Errors include a diagnostic ID. Records exclude prompts, reasoning and successful answers; provider error text and stderr are bounded and credential patterns are redacted. Keep these runtime logs private.

The guided review uses durable ingestion request IDs. Retrying the same input returns the original receipt after a lost response, and a new session commits together with its facts. Failed extraction leaves no new session or facts. `npm run review` now checks local-model startup even when reusing an existing Amnesia server; `npm run review -- --no-open` performs that startup without opening a browser.

## Implemented research kernel

- **Structured extraction:** typed atomic assertions, exact source quotations, heuristic confidence, intent, validity dates, and explicit aliases. Validation failures receive at most one repair call; authentication/network failures are not retried as extraction repairs.
- **Identity and scopes:** canonical entity identifiers; independent beverage/programming preferences and phone/laptop/tablet ownership. Pet names are versioned literals on a stable pet subject.
- **Six-way reconciliation:** `SAME`, `SUPPORTS`, `UPDATES`, `CONTRADICTS`, `SUPERSEDES`, `UNRELATED`. Conservative deterministic rules use model-extracted intent and compatible subject/relation/scope; no trained six-class classifier is claimed.
- **Temporal lifecycle:** current, superseded, invalid, unresolved; computed future/expired state. Corrections, cancellations, temporary extensions, future-dated changes, and earlier observation snapshots preserve provenance in append-only lifecycle history.
- **Conflict confirmation:** record an explicit user statement and resolve only alternatives in the matching scope.
- **Hybrid retrieval:** dense cosine similarity, weighted personalized PageRank (damping 0.85, 40 iterations), validity, confidence, and staleness. Historical queries can retrieve earlier evidence. Relevant unresolved alternatives survive top-k pruning.
- **Grounded answering:** the configured LLM supplies an answer value and citations validated against the supplied context. Citation validation is not a formal entailment guarantee.
- **Persistence:** SQLite workspaces, sessions, entities, facts, evidence links, decisions, aliases, and lifecycle history. Version-2 JSON backups restore transactionally into a new workspace with remapped identifiers.
- **Experiments:** background jobs with progress, cooperative cancellation, saved results, failure notebooks, raw JSON, and gold annotation downloads.

```text
Score = 0.40 semantic + 0.25 graph + 0.20 validity
      + 0.15 confidence - 0.65 staleness
```

Lifecycle filtering additionally excludes stale positive assertions from current hybrid context. Negative cancellation evidence remains available; unresolved conflicts trigger clarification. The optional memory gate is a bounded heuristic, not a trained classifier.

## Reproduce and inspect the evidence

```sh
npm test                 # Automated storage, policy, API, and provider-contract tests
npm run build            # TypeScript and production frontend
npm run doctor           # Storage, engine configuration, server, and report checks
python3 -m backend.doctor --inference  # Actual configured language/embedding calls
npm run evaluate         # 600 gold-input policy questions; no model calls
npm run evaluate:ai      # 60 curated questions through the configured AI engine
python3 -m backend.quality --questions 20  # All ten categories, shorter review run
# Cold language-model calls instead of the evaluation response cache:
python3 -m backend.quality --questions 60 --no-cache
```

`doctor` defaults to port 8788; pass `--port PORT` if the launcher selected another port. Environment overrides: `AMNESIA_DATA_DIR`, `AMNESIA_API_PORT`, `AMNESIA_WEB_PORT`, `AMNESIA_PROVIDER`, `AMNESIA_MODEL`, `AMNESIA_EMBEDDING_MODEL`, and `AMNESIA_OLLAMA_URL`.

| Suite | Inputs and reader | What it establishes |
|---|---|---|
| Policy | 600 seeded questions, gold assertions, deterministic evidence reader | Scoped reconciliation, safe invalidation, temporal retrieval, two ablations |
| Live AI | 30 internally curated conversations / 60 questions, actual extraction, embeddings, and same LLM reader | End-to-end behavior with full-context, vector, graph, and hybrid baselines |

The 10 categories cover stable facts, preferences, locations, corrections, cancellations, replacements, temporary states, additions, renames, and ambiguous conflicts. Frozen inputs are in `data/`; generators and annotations are in `backend/evaluate.py` and `backend/benchmark_data.py`. Results retain provider/model identity, cache-hit counts, actual reported model tokens, per-query answers, extraction records, and failures. Cached timings are not cold-inference measurements.

Metrics include extraction F1, reconciliation macro-F1, exact QA accuracy, stale-memory error rate (SMER), false invalidation rate (FIR), Recall@K, and MRR. See [docs/evaluation-results.md](docs/evaluation-results.md) and [docs/verification.md](docs/verification.md) for actual results and checks. Bundled completed runs appear in the app on a fresh installation; a completed local rerun replaces that suite's saved report.

## Boundaries to state in the review

These are internal synthetic/curated development sets, not blind external or third-party annotated benchmarks. Perfect policy results do not establish natural-language accuracy. The no-graph policy ablation currently matches hybrid, so that suite does not prove a graph-scoring advantage. The live set lacks `SAME` transitions; policy cases and tests cover duplicates.

Entity identity, scope classification, and temporal interpretation remain bounded. Confidence is not calibrated. Long full-context input is explicitly truncated at 16,000 characters. Ingestion requires monotonic observation times per workspace. The graph view shows at most 24 assertions and announces truncation; the ledger and export retain all assertions. The system is a complete local research application with no multi-tenant authentication, billing, cloud hosting, or production connectors.

Prior work already includes temporal knowledge graphs; novelty is the scoped reconciliation policy and failure-oriented evaluation framing. This implementation does not claim to reproduce published memory systems or train a reconciliation model.

## Files and API

| Path | Purpose |
|---|---|
| `backend/engine.py`, `codex_provider.py`, `extraction.py` | Provider configuration, private credentials, structured extraction |
| `backend/memory.py`, `storage.py` | Reconciliation, SQLite graph, history, backup restoration |
| `backend/retrieval.py` | Dense vectors, PageRank, grounded answering |
| `backend/evaluate.py`, `quality.py`, `benchmark_data.py` | Policy and actual AI experiments with gold annotations |
| `backend/jobs.py`, `server.py` | Persisted evaluation jobs and localhost API |
| `src/` | Studio, ledger, engine, experiments, notes, and final review |
| `docs/project-brief.txt` | Original Review 1 brief; retained as the original proposal |
| `scripts/build_report.py`, `package_review.py` | Report generation and secret-free release archive |

Core routes: `/api/health`, `/api/engine`, `/api/engine/test`, `/api/workspaces`, `/api/sessions`, `/api/state`, `/api/events`, `/api/query`, `/api/conflicts/resolve`, `/api/export`, `/api/import`, `/api/experiments/start`, `/api/jobs`, `/api/reports`, `/api/dataset?suite=policy`, `/api/review`, `/api/report`.

Writes require JSON and a local origin/host. Runtime data stays under `.amnesia/`; preserve this directory for your own memories. `npm run package:review` creates `release/Amnesia-final-review.zip` with source, compiled app, annotations, measured artifacts, and report, excluding keys, workspaces, model caches, and dependencies.

To regenerate the PDF from CLI evaluation artifacts, use a separate Python environment with `pip install -r requirements-report.txt`, then run `python scripts/build_report.py`. The generator prefers completed Codex-login measurements, then direct OpenAI API measurements, then explicitly labeled local-model measurements. The PDF is a saved review artifact; rerunning an experiment in the UI updates its JSON report, not this PDF automatically.
