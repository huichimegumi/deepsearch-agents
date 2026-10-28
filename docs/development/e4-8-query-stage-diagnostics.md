# E4.8 — Query comparison and retrieval-stage diagnosis

## Implemented

The E4.7 chapter-title failure is now traceable through the actual retrieval stages. Optional
`diagnostics` arguments on the local RAG search/Evidence collector record vector/hybrid candidate
IDs, full rerank order/scores, retained IDs, and context-budget delivery IDs. No source text is
copied into this diagnostic dictionary. Ordinary callers do not enable capture, and ranking,
thresholds, Evidence construction and context limits remain unchanged. Tests compare traced and
ordinary outputs directly.

The evaluation runner freezes an original/concise query plan before any service call. Concise
queries use only the source title explicitly present in the question, question-part labels and
the directory cue when it appears in the question. No answer names, known source IDs, evaluator
reference text or generated model rewrite is used. Both policies use one local query per task,
the same scoped corpus and unchanged retrieval configuration.

```powershell
# Default: freeze a plan only, no service/model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.query_compare

# Three questions × two query policies; no selector/Writer or Web search.
.venv\Scripts\python.exe -m evals.reports_acceptance.query_compare --execute
```

Run: `rag_query_compare_20261028T034913Z_c55944dd11`.
Total: **6 local RAG queries, 0 generator calls, 0 searches, 0 fetched pages**. Local embedding
and reranking inference still execute. Corpus/source fingerprints stay unchanged. Original-query
delivery IDs match all three saved E4.7 retrieval batches exactly.

## What the comparison establishes

The reference chunks are inspected after retrieval for rank auditing. They never enter query
construction or candidate filtering. These are two known finite support references, not a recall
score over the whole corpus or a correctness label for the negative task.

| Reference / query | Vector rank | Hybrid rank | Rerank rank | Rerank score | Retained / delivered |
| --- | ---: | ---: | ---: | ---: | --- |
| TOC / original | 3 | 17 | 29 | 0.473 | absent / absent |
| TOC / concise | 2 | 19 | 29 | 1.551 | absent / absent |
| Survey / original | 7 | 1 | 3 | 5.984 | 3 / 3 |
| Survey / concise | 19 | 2 | 3 | 7.813 | 3 / 3 |

The TOC **already reaches candidate recall** in both policies. Reranking demotes it to rank 29.
The original score also falls below the configured relevance threshold 1.0. The concise score
passes that threshold but still falls outside the retained top eight. Context delivery of six
records happens downstream; increasing that delivery limit alone would not restore this chunk.

The concise query therefore does **not** fix delivered TOC support. No new Writer call is made,
and the incorrect E4.7 chapter answer remains preserved. This failed improvement prevents
misdiagnosing the problem as insufficient initial recall or treating a higher vector rank as
successful answer generation.

The survey paragraph provides a counterexample to a simple vector-only replacement: it reaches
delivery at rerank position three for both queries, while its vector ranks are seven and nineteen.
Taking only the vector top six would omit that known support. This is an offline rank observation,
not an executed alternative delivery policy or a general proof that one ranker is superior.

All six query batches are bounded partial results with reranking applied. The corpus remains
the same scoped two-document/117-chunk corpus. Each question/policy is run once on an exposed
development group, so no general accuracy, latency or holdout claim follows. Human accuracy
remains null. The negative task has no complete finite support reference to score; returned
topical material must not be called a correct answer.

## Verification and next work

Full regression: **549 passed, 6 skipped**. Six new tests cover source-bound query construction,
traced/ordinary rank equivalence and score cutoff, context delivery capture, plan isolation,
exactly six planned calls and retained failures without retry. Ruff lint/format and
`git diff --check` pass. The default CLI smoke path creates a plan without service/model calls.

The [content-free result record](../../evals/reports/e4-8-query-stage-diagnostics-2026-10-28.json)
preserves stage counts, reference ranks/scores, E4.7 delivery equality, fingerprints and artifact
hashes. Private source text, full diagnostic ID lists, query plans and `REFERENCE_AUDIT.json`
stay ignored under `evals/results/`. No retrieval policy, thresholds or production query default
changes; only explicit diagnostic capture is added.

Next evaluate a bounded retention policy that preserves a small vector head alongside reranked
results, with a fixed total delivery budget. Use these failures as exposed diagnostics and
regress against the existing broader RAG development set before selecting parameters or adopting
a default. Preserve both the TOC and survey counterexample; do not tune a chapter-name exception,
expand query loops, or report the earlier four mechanically linked answer parts as correctness.
