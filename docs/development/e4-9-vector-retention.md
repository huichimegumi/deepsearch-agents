# E4.9 — Vector-head protection fails broader development regression

## Prototype and fixed experiment

E4.8 showed that reranking removed a high-vector-rank TOC while preserving a survey paragraph
outside the vector top six. This stage tests one predeclared retention rule: reserve the first
three unique vector candidates, fill with threshold-qualified reranked candidates, and cap
delivery at six under the existing 10,000-character context limit. Protected candidates bypass
the reranker threshold. No protection-size sweep is performed.

`app.rag.retention.retain_vector_head` implements this deterministic prototype. Production search
does not import or enable it. The evaluation collects/reranks one shared candidate pool per
question, then compares baseline delivery with protected delivery through the actual existing
context-budget function. Answer anchors are used only for scoring, never candidate selection.

The frozen **20-case development split** is checked against its suite lock: 19 answerable cases
and one no-answer case. Test questions are not loaded or executed. Scope is both knowledge bases,
five documents/305 chunks. Labels remain source-verified drafts pending human review.

```powershell
# Default: frozen development plan only, no inference or services.
.venv\Scripts\python.exe -m evals.rag.run_retention

# Twenty shared recall/rerank calls; no generator or Web search.
.venv\Scripts\python.exe -m evals.rag.run_retention --execute

# Explicit post-hoc replay: reorder identical saved protected hits, no inference.
.venv\Scripts\python.exe -m evals.rag.run_retention --replay-ordering evals/results/rag_retention_dev_20261028T082206Z_ae60b12456
```

## Results and decision

Live run: `rag_retention_dev_20261028T082206Z_ae60b12456`.
Ordering replay: `rag_retention_order_replay_20261028T082826Z_c1bc62c619`.

| Policy | Recall@6 | MRR@6 | All finite units found |
| --- | ---: | ---: | ---: |
| Existing thresholded reranking/context delivery | 0.702 | 0.480 | 12/19 |
| Protect vector head, place it first | 0.649 | 0.182 | 11/19 |
| Same protected members/text, original rerank display order | 0.649 | 0.469 | 11/19 |

All 20 paired cases execute validly; the 19 answerable cases form the metric denominators.
Two cases lose finite-unit coverage: `rag_local_zh_010` falls from 0.5 to 0, and
`rag_local_zh_019` from 1 to 0.5. The no-answer case's delivered count changes from **0 to 3**
because protection bypasses the score threshold. That is a candidate-admission regression; no
generator abstention or answer precision is measured.

Putting the protected head first also delays useful reranked evidence. After observing that
development result, a separately labelled **post-hoc** replay sorts already-budgeted members by
their full original rerank order. It preserves every selected member, exact content and budget;
no source is added and no retrieval/model inference repeats. MRR recovers substantially, while
the coverage losses and negative-case admissions remain. All live protected cases fit the
character budget without character truncation.

**Do not enable unconditional vector-head protection.** Ordering alone cannot repair membership
displacement or justify threshold bypass. A local diagnostic success is insufficient grounds
to replace the existing retrieval policy.

## Earlier diagnostic replay remains separate

An offline ID-rank replay of the saved E4.8 candidates keeps the TOC within the six-member budget
at positions 3/2 and the survey reference at position 5 for both queries. It makes no new service
call and does not render a protected answer context or generate reports. These two known finite
references are exposed diagnostics, separate from the live 20-case experiment and its metrics.
Their survival does not offset the broader regressions.

Total new execution: **20 logical local retrieval calls, 0 generator calls, 0 Web searches/pages**.
Both policies share each query's recall/reranking computation. Corpus, dataset, suite lock and
live source fingerprints stay unchanged during execution. This run scores threshold/context-
bounded delivery at six, so it is not interchangeable with earlier rank-only A/B/C scores at five.

## Verification and provenance

Full regression: **560 passed, 6 skipped**. Eleven tests cover bounded unique retention, threshold
bypass limits, invalid budgets, position-six scoring, negative denominator exclusion, development
integrity, offline default, and source-preserving ordering replay. Ruff lint/format and
`git diff --check` pass. Real default/replay CLI paths complete without additional inference.

The ordering helper/replay code was added after the live prototype result. Its original two
source files are archived privately; replacing those two final hashes exactly reconstructs the
live fingerprint. Final-source validation comprises offline replay and tests, not another live
development execution. The
[content-free record](../../evals/reports/e4-9-vector-retention-2026-10-28.json) preserves both
manifests, per-case metrics, unchanged membership/budgets, diagnostic ranks and result hashes.
Full candidate/source text stays ignored in `evals/results/`. Human accuracy remains null.

Next assess the reranker input itself, such as supplying source identity/structural context
while keeping Evidence text unchanged. Use the same candidate pools and the broader development
regression to separate rerank changes from recall changes. Preserve the two coverage regressions
and the no-answer admission failure; do not compensate by tuning protection size on the TOC case.
