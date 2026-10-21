AMNESIA — saved experimental results as CSV

These are exports of the saved reports used in the final-review presentation.
No model calls or experiments were rerun during export.

metrics-summary.csv: 14 records
run-summary.csv: 3 records
answer-records.csv: 320 records
extraction-audit.csv: 80 records
reconciliation-by-label.csv: 18 records
category-results.csv: 140 records
automated-tests.csv: 63 records

Reading the data:
- Rates, accuracy, F1, recall and MRR use 0–1 values (0.95 = 95%).
- Latencies and durations are milliseconds. Context-token estimates are estimates.
- Empty cells mean unavailable/not applicable, not zero.
- run identifies policy, ollama or codex; source and run_generated_at preserve provenance.
- Policy uses injected gold facts. Its extraction scores do NOT measure an NLP extractor.
- Policy has aggregate metrics only; no individual policy answers are invented.
- Live answer records contain 240 local-model and 80 Codex answers across four methods.
- The source key recall_at_5 is legacy: live retrieval uses K=3, policy K=5.
  Context-method recall is full-context evidence coverage and has no retrieval K.
- Reconciliation rows with support=0 are not evaluated; their source zeros are preserved.
- JSON-suffixed cells preserve lists/objects. Predicted and gold extraction lists are
  not positionally matched; one row represents one extraction turn.
- Cached calls are retained in the original live-run reports; see run-summary.csv.
- automated-tests.csv is parsed from the saved 63-test log, not a new test run.

Original reports and logs remain in output/. Dataset inputs remain in data/ and
the original output/*.jsonl files; these input cases are not answer-output records.
manifest.json records source SHA-256 hashes and export counts.
