# E2 RAG retrieval pilot

## Scope and implementation

The first experiment now runs through the real PostgreSQL/Qdrant/local-model stack. It uses five
existing development queries: `rag_local_zh_001`, `003`, `007`, `012`, and `020`. The final case is
unanswerable and is excluded from retrieval metric denominators. Labels contain literal anchors,
source-document hashes, answer keypoints, and an explicit pending-human-review status.

Application RAG and the runner now share global vector/lexical recall, RRF, ready-chunk hydration,
and corpus selection. A skips lexical retrieval. B/C share one in-memory candidate pool; each row
records its pool hash. C must actually run the configured reranker to receive a score. Rank-only
Top-5 evaluation does not apply the application's reranker-score threshold to other score scales.

The runner validates annotation anchors, fingerprints the indexed corpus, hashes local ONNX/JSON
model artifacts, and saves isolated configuration-level results and a Markdown summary. Changed
corpora invalidate results. Source hashing supplements a dirty Git revision, permitting the
pre-commit pilot's executed source content to be identified.

## First real result, 2026-10-18

Run `rag_20261018T102501Z_2e326ae4d5` used five documents and 305 chunks in the selected commerce and
finance knowledge bases. Embedding: `BAAI/bge-small-zh-v1.5`; reranker: `BAAI/bge-reranker-base`.
All fifteen configurations were valid, and BGE inference succeeded on every C row. Warmup was about
2.44 seconds and is excluded from per-query latency. No search credits or generative LLM calls were
used.

| Mode | Valid configurations | Answerable denominator | Anchor Recall@5 | MRR@5 | All evidence | Median ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A vector | 5/5 | 4 | 0.250 | 0.0625 | 0.250 | 181.776 |
| B hybrid RRF | 5/5 | 4 | 1.000 | 0.7083 | 1.000 | 778.215 |
| C hybrid + BGE | 5/5 | 4 | 0.250 | 0.2500 | 0.250 | 16538.751 |

On `001`, `007`, and `012`, the annotated evidence was in B's Top-5 but left C's Top-5 after
reranking. On `003`, C retained it at rank 1. On `012`, A's first relevant evidence ranked fourth;
B moved relevant evidence to rank 1. All no-answer modes returned candidates; no abstention outcome
is asserted. The installed FastEmbed implementation was checked: scores correspond to input
documents, so the experiment is not mistakenly treating pre-sorted output as original-order scores.

These are small development diagnostics with literal-anchor labels. The questions frequently name
documents, alternate valid evidence may still be unlabeled, and human review is outstanding. The
legacy index also lacks recorded original embedding provenance. The table establishes that the
experiment detects ranking changes and cost; it does not establish general answer accuracy or an
independent test result. The reranker default is not changed on the strength of these four queries.

The tracked [content-free result](../../evals/reports/e2-rag-pilot-2026-10-18.json) preserves individual
scores, candidate pool hashes, timing, model status, corpus/configuration/model hashes, and exact
denominators. Raw retrieved passages remain local in `evals/results/<run_id>/results.json`.

## Verification and remaining milestones

Focused RAG/Evidence/tool regression initially passed 18 tests. The final expanded repository suite
passed 206 tests with 6 skipped. Changed-file Ruff lint/format and `git diff --check` passed.
Independent checks confirmed all B/C pool hashes agree, the executed source hash still matches the
current application/evaluation source, and the annotation dataset hash is unchanged.

Whole-repository Ruff checks also exposed baseline issues: one existing import-order violation in
`tests/test_eval_datasets.py` and 22 pre-existing app/test files needing formatting. The original
revision's import violation was reproduced with `git show adf1c7f1:tests/test_eval_datasets.py`.
Those unrelated files were left untouched; this stage does not claim a clean whole-repository lint
or format baseline.

E1 is complete. E2's five-question executable pilot is complete; expanding to reviewed 20-question
development and approximately 10-question frozen test sets remains pending. E3 report acceptance
and E4 a single measured improvement have not been executed. Future work should validate evidence
alternatives and the index/model contract before attributing the observed drops solely to BGE.
