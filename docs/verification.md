# Final-review verification

Validated on 14 October 2026 on macOS / Apple M4 Max, Python 3.9.6, Node.js 22.23.1, and Chrome.

## Automated checks

- `npm test`: **63 tests passed**. Coverage includes six-way reconciliation, independent preference/device scopes, entity-specific conflict isolation, uncertainty, cancellation, historical snapshots, future-dated updates, temporary extensions, provenance, persistence, PageRank mass/traversal, atomic corrupt-import rollback, credential permissions/redaction, actual adapter request contracts, HTTP behavior, background-job cancellation, persistence, and interruption after restart.
- `npm run build`: TypeScript and Vite production compilation passed.
- `npm run evaluate`: **600 gold-input policy questions** completed. Hybrid 600/600 exact answers, zero stale errors, zero false invalidations (0/180). No-graph ablation also scored 600/600; this does not prove graph advantage.
- Actual local-model evaluation: **60 curated questions**, Qwen3.5:9b + Nomic embeddings on Ollama 0.32.14. Hybrid 60/60, extraction F1 90%, reconciliation macro-F1 94.51%, zero stale errors (0/21), zero false invalidation (0/33), no provider/validation errors. Full-context/vector/graph QA: 95%/90%/93.33%.
- The measured local run used **197 live LLM calls and 100 cache hits**. Timings include this cache behavior. A final-source 20-question cache replay passed with hybrid 20/20 and no errors (0 live LLM calls, 99 cache hits); this replay is regression evidence, not new cold-inference performance evidence.
- Local `doctor --inference` passed storage, backup restoration, running server, report, actual structured model inference, and 768-dimensional embeddings.

## Browser checks

The compiled application was exercised on an isolated preview workspace/database with local models. Those checks used the local backup. The primary application now uses the user's requested Codex login with local embeddings.

- Completed all seven review steps using real extraction/query calls: initial facts, relocation/preference change, actual hybrid/vector/raw-context comparison, additive facts, uncertainty, explicit Chennai confirmation, and measured results.
- Confirmed review graph transitions from two current facts to two current/two superseded facts; final state has five current facts, two superseded facts, no unresolved facts, and four sessions.
- In this particular walkthrough, all three answer methods returned Chennai. The UI reports that actual result; the vector stress demonstration is not a guaranteed failure.
- Exported the review workspace (eight stored assertions, thirteen lifecycle transitions) and restored it through the UI into a new workspace with remapped IDs.
- Verified imported workspace, studio controls, and evaluation tables at **390 x 844** with **no document horizontal overflow**. Wide tables scroll inside their own containers.
- Started a live evaluation, reloaded the page, recovered the active job, requested cancellation, and observed the cancelled state. The previous completed 60-question report remained intact.
- Browser console after the completed review/import flow: **0 errors, 0 warnings**.
- Refreshed the actual Codex in-app browser to v1.0 and visibly verified the OpenAI engine/key-entry screen.
- Production PDF endpoints on ports 8788 and 8790 returned HTTP 200 with `application/pdf`.

Earlier v0.1 browser checks also covered the studio, source inspector, Escape dismissal, timeline, ledger filtering, and historical snapshot controls. They are earlier evidence; the complete v1 review, import, experiments, and key-entry checks above were repeated against the upgraded build.

## Review artifacts

The generated report contains **10 pages**. All pages were rendered to PNG and visually inspected for pagination, clipping, tables, charts, and reference text. The architecture diagram was rendered from Mermaid source and inspected. Larger checks covered the measured-results and error-analysis pages. The report separates local-model evidence from unperformed OpenAI experiments.

Screenshots are under `output/playwright/`: `review-remember.png`, `review-comparison.png`, `review-conflict.png`, `review-final.png`, `experiments-final.png`, `experiments-final-mobile.png`, `imported-mobile.png`, and `engine-final.png`.

## Codex login integration

The user selected Codex login instead of an API key. The official CLI is installed (0.149.1), `codex login status` reports ChatGPT authentication, and an actual structured-output call passed using gpt-5.6-sol. Actual local Nomic embeddings returned 768-dimensional vectors.

The adapter uses ephemeral read-only `codex exec` runs, disables shell/command, app, browser, hook, and delegation capabilities, checks successful turn completion and schema output, and rejects tool-action events. Amnesia does not open or copy Codex credential files. Additional tests cover auth-mode distinction, private environment handling, completion/error validation, token accounting, local embedding routing, and capability configuration.

The separate Codex-login run completed all 20 questions across ten categories: hybrid 20/20, extraction F1 93.33%, reconciliation macro-F1 97.29%, zero stale errors (0/7), zero false invalidation (0/11), and no provider/validation errors. It recorded 87 live LLM calls and 12 cache hits. Raw output is `output/evaluation-codex.json`. Direct OpenAI API measurements remain optional and unperformed; Codex-login results are labeled separately from direct API and fully local results.

## Release check

The release archive was extracted into a fresh temporary directory and started on an available loopback port. Health/version/project ownership, the compiled frontend, both bundled measured reports, and the PDF endpoint all passed. Archive paths exclude credentials, runtime workspaces, caches, node_modules, and environment files. The package includes three synthetic demo screenshots, a per-file SHA256 manifest, and an archive checksum.

## Codex final browser check

The primary application completed all seven review steps through Codex CLI: initial extraction, scoped updates, actual three-method answer comparison, additive facts, unresolved uncertainty, explicit confirmation, and the completed 20-question Codex results table. The confirmed answer was Chennai. Final state: five current facts, two superseded facts, no unresolved alternatives, four sessions. The in-app browser console recorded no warnings or errors.

Screenshots: `docs/screenshots/engine-codex.png`, `review-codex-comparison.png`, `review-codex-conflict.png`, and `review-codex-final.png`. The updated ten-page PDF was re-rendered and visually inspected after replacing the prior API-key setup with Codex login instructions and measured Codex results. A single-paragraph pagination spill was corrected before packaging.

The launcher now matches both project and data directory when reusing a server, preventing the isolated local-model preview from being mistaken for the primary Codex configuration.
