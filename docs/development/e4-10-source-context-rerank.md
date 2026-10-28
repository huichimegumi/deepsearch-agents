# E4.10 — Source context improves aggregate retrieval metrics, with regressions

## Experiment

E4.9 rejected unconditional vector-head protection. This stage changes only reranker input
format: prepend actual source filename and available page/section metadata to the original
passage. `source_context_text` bounds metadata headers and preserves the passage bytes. It is
not connected to production search, and augmented text never becomes Evidence/scoring text.

Candidate membership comes from hash-verified saved pools: the two earlier original-query
diagnostics and the frozen 20-case development split. No new retrieval, query rewrite, source
addition, forced protection or generator call occurs. Both formats are freshly reranked on the
same candidate order with the same local model, threshold 1.0, retained top eight, delivered
maximum six and 10,000-character context budget. Labels are used only after ranking for scoring.

The development archive did not retain its original fusion input order. Complete membership is
reconstructed from the saved full rerank order; both formats receive that same sequence. Fresh
raw-input deliveries reproduce **all 22 cached controls**, including both diagnostics. This
checks the reconstruction without pretending that the original input order was archived.

The saved corpora contain filenames/pages but no section field. No heading is invented to fill
it. The formatter supports available section metadata, but this run tests filename/page context.
Prefixes can also affect the provider's token budget; truncation effects are not isolated.

## Reproduction

```powershell
# Default: verify private frozen inputs and create a plan; no model/service calls.
.venv\Scripts\python.exe -m evals.rag.run_context_rerank

# Two original-query diagnostic pools: four local rerank calls.
.venv\Scripts\python.exe -m evals.rag.run_context_rerank --diagnostic --execute

# Frozen 20-case development split: forty paired local rerank calls.
.venv\Scripts\python.exe -m evals.rag.run_context_rerank --execute
```

These commands require the earlier private candidate/corpus snapshots. Reranker ONNX/tokenizer
files are checked against the frozen v2 artifact hashes before and after execution; availability
fallback invalidates an experiment row. The test questions are not loaded or executed.

Total: **44 local rerank calls, 0 local retrieval queries, 0 generator calls, 0 Web searches/pages**.
No parameter search or retry for a passing result is performed. Raw/context models are evaluated
as pairs rather than comparing a current model only with historical cached scores.

## Diagnostic outcome

Run `context_rerank_diagnostic_20261028T084304Z_d8afabda86`:

| Reference | Raw rank / delivered | Source-context rank / delivered |
| --- | --- | --- |
| TOC | 29 / absent | 28 / absent |
| Survey paragraph | 3 / 3 | 1 / 1 |

The TOC score rises from 0.473 to 4.334, clearing the threshold, but it still misses the retained
top eight. Higher absolute scores do not establish support recovery. No chapter report is
regenerated or marked repaired. Survey source identity helps its ranking in this diagnostic.

## Broader development regression

Run `context_rerank_dev_20261028T084607Z_26daa73038` uses the existing five-document/305-chunk
snapshot and 20 fixed questions. All paired cases are valid; 19 answerable cases form the finite
evidence-unit metric denominators.

| Input format | Recall@6 | MRR@6 | All finite units found |
| --- | ---: | ---: | ---: |
| Raw passage | 0.702 | 0.480 | 12/19 |
| Source filename/pages + passage | 0.754 | 0.592 | 12/19 |

Coverage improves on `rag_local_zh_006`, `013` and `018`, but regresses on `007` and `019`:

- The AI-customer-service reference in `007` falls from matched coverage 1 to 0.
- Cross-document application coverage in `019` falls from 1 to 0.5.

The no-answer case returns **zero hits in both formats**. It remains outside Recall/MRR
denominators; no generator abstention, semantic precision or answer accuracy is measured. Finite
reference labels are provisional and need not enumerate every semantically valid alternative.
Unchanged all-unit coverage and the two regressions matter alongside the aggregate gains.

This is a promising development result, not a production default change. The earlier TOC failure
remains, the scores are not calibrated probabilities across formats, and one no-answer case
does not establish general refusal behavior. No old A/B/C rank-only @5 score or holdout result is
pooled with this threshold/context-bounded @6 comparison. Human accuracy remains null.

## Verification and next step

Full regression: **568 passed, 6 skipped**. Eight tests cover metadata/body separation, bounded
headers, shared candidate/query pairing, raw Evidence preservation, fallback invalidation,
offline plans, corrupt-source rejection, model-artifact integrity and archive-order reconstruction.
Ruff lint/format and `git diff --check` pass. Default diagnostic/development plans require no
new inference or services.

Diagnostic inference preceded a development-loader compatibility repair. Its original runner is
archived; substituting that one hash reconstructs its source fingerprint. Development inference
and final tests use the repaired source. The
[content-free record](../../evals/reports/e4-10-source-context-rerank-2026-10-28.json) preserves
both manifests, model-artifact hashes, controls, per-case metrics and rank diagnostics. Private
candidate text and complete outputs remain ignored under `evals/results/`.

Next inspect the two lost-reference cases and the structural evidence required by the TOC task
before enabling a runtime option. Separate source identification from whether a passage answers
the requested relation, and keep the known insufficient-evidence examples. Do not promote this
format solely on the mean metrics or retune a global threshold on the single no-answer case.
