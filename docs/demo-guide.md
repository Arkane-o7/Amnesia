# Final-review demonstration and viva

## Before entering the room

1. Run `npm run review`, open AI engine, select **Codex · ChatGPT login**, and click **Save & test engine**. Confirm language inference and embedding dimensions both pass.
2. Run `npm run doctor`. If the server uses another port, pass `python3 -m backend.doctor --port PORT`.
3. Read the engine/provider badge on every saved experiment. Codex-login, direct OpenAI API, and fully local Ollama results must remain separately labeled.
4. Keep the generated PDF and release archive available locally. The PDF contains saved evidence even if conference-room internet is unavailable.
5. For an offline live demonstration, explicitly select installed Ollama models beforehand and test them. Codex requires internet, an active ChatGPT login, and available Codex plan usage. The optional OpenAI API provider requires its own key.

## Eight-minute script

**0:00 - Problem.** Open Final review. “Semantic relevance does not say which fact is current. I represent memory as evolving state with source evidence.”

**0:45 - Extract.** Start the live review. Explain that the model converts the first conversation into atomic assertions. Select a node to show its source quotation and observation time.

**1:45 - Update.** Advance to the relocation. Point to superseded Hyderabad/Python and current Chennai/Rust. “The earlier evidence stays; only the compatible scope changes.”

**2:45 - Retrieve.** Advance to the actual baseline comparison. Read the displayed answers. The vector stress demo uses K=1; do not promise a stale answer. Show lifecycle filtering and citation links in the studio if asked.

**3:45 - Preserve.** Add employer, project, and beverage facts. “New tea preference should not invalidate Rust, because beverage and programming language are separate domains.”

**4:45 - Clarify.** Introduce a speculative move to Pune. Show both alternatives as unresolved. Click **Confirm Chennai and resolve**, then show the recorded confirmation and preserved history.

**5:45 - Evaluate.** Show policy and live-AI results separately. State the model, question count, exact-match criterion, SMER, FIR, and cache counts. Show the error notebook even if the selected completed run has no failures.

**6:45 - Limits and handoff.** Open the PDF and explain the internal curated dataset, bounded identity/temporal inference, and lack of independent held-out testing. Demonstrate workspace export and import if time permits.

## Likely viva questions

**Why a graph?** Entities and relations allow associative traversal and inspectable evidence links. Personalized PageRank contributes graph relevance. However, the current policy ablation does not establish an independent graph advantage; stronger held-out multi-hop cases are needed.

**What is new?** The proposed contribution is conservative relation/scope-aware reconciliation plus evaluation of stale answers and false invalidation. Temporal graphs themselves are established prior work.

**Did you train a classifier?** No. The LLM extracts fact intent and evidence. Deterministic conservative rules assign the six reconciliation labels within compatible scopes. Model-assisted reconciliation or supervised training is future work.

**How do you distinguish a correction from an update?** Explicit correction cues mark an earlier statement as invalid. Explicit real-world change supersedes it. Uncued/uncertain incompatible assertions remain unresolved instead of choosing certainty.

**Does the latest statement always win?** No. An uncertain claim can create an unresolved conflict. A temporary visit uses a separate relation. Additive facts and separate preference/device scopes remain compatible.

**What is the difference between valid time and observation time?** Valid time says when a fact applies in the world. Observation time says when the system learned it. The snapshot control reconstructs earlier observed belief states and respects explicit validity intervals.

**How are baselines compared?** The live suite shares extracted assertions and the same LLM reader. Full context receives raw conversation turns; vector and graph receive top-3 facts without lifecycle states; hybrid receives temporally filtered facts with states. The policy suite separately supplies gold assertions and uses a deterministic reader.

**What do SMER and FIR mean?** SMER is stale-value answers divided by evolved-fact questions. FIR is preserved gold facts incorrectly retired divided by preserved facts considered. They measure different failure modes.

**Why are some policy scores perfect?** That controlled suite supplies exact assertions and exercises the rules they were designed to test. It isolates state management; it does not demonstrate perfect natural-language AI.

**Can citation checks prevent hallucination?** They reject citation IDs outside the context. They do not prove that a sentence is semantically entailed. Stronger entailment checks and independent evaluation remain open.

**How were annotations produced?** The project includes explicit developer-curated gold facts, transitions, and answer aliases. They are not generated by the evaluated model, but the set is internal development evaluation, not independent blind annotation.

**How is long-term memory stored?** SQLite persists sessions, entities, facts, supporting evidence, decisions, aliases, and append-only lifecycle transitions. Backup imports use new identifiers and a single transaction; invalid references roll back.

**What if the API fails?** The app displays the error and retains committed memory. It does not silently change providers. You can explicitly select a tested local Ollama engine or use the saved report for the review.

**What comes next?** A frozen held-out real-conversation set, independent annotation, richer graph traversal cases, model-assisted reconciliation comparisons, and context-cost measurements across retrieval budgets.

## Review materials

- `output/pdf/amnesia-final-report.pdf`: generated academic report.
- `docs/evaluation-results.md`: measured results with interpretation.
- `docs/verification.md`: exact automated/browser verification.
- `data/`: frozen gold annotations.
- `output/evaluation-policy.json`, `output/evaluation-ollama-final.json`, and any completed `output/evaluation-codex.json`: auditable raw results.
- `release/Amnesia-final-review.zip`: source, compiled app, datasets, and report. API keys and private workspaces are deliberately excluded.

**Why do embeddings run locally with Codex?** The integration uses Codex's supported structured-response workflow for language tasks. It does not treat the ChatGPT login as an embeddings API credential. Nomic provides actual dense vectors locally.

**Does Amnesia copy my Codex token?** No. It invokes the signed-in official CLI. Login and refresh remain inside Codex. The release archive contains neither Codex credentials nor private runtime state.
