# E4.14 — Live source/structure retrieval through the minimal report pipeline

E4.13 recovered the TOC only in saved-score replay. This stage connects that planner to an
explicitly opted-in live retrieval path and runs the frozen three-task selector/Writer suite.
Ordinary search and API/UI behavior remain unchanged. The switch is an internal
`_collect_local_documents(..., experimental_source_structure=True)` keyword and the evaluation
CLI's `--source-structure`; it is not a new public request-schema field or deployment flag.

## Runtime implementation

`app/rag/structure_retrieval.py` performs one ordinary hybrid candidate recall and one local
rerank with the original question. It then reads ready document metadata **only within the
requested knowledge bases**, resolves exact names, and scopes the complete scored pool before
the top-eight cutoff. Source names are not removed from the query or replaced with aliases.

For an affirmative TOC request with no more than two resolved sources, a second read inspects
their actual indexed chunks for a unique structural passage. It still may reserve only a chunk
already in the recalled pool. Inventory reads are bounded to **256 documents / 1,024 structural
chunks**, plus one overflow sentinel each. Source chunk reads require both the document and chunk
to belong to the allowed knowledge bases and the document to be ready. Ambiguity, unsupported
constraints, out-of-pool structure and inventory overflow are explicit diagnostic outcomes.

Document-inventory overflow or unresolved source identity preserves normal retrieval. Structural
inventory overflow disables structural reservation while preserving resolved document scoping.
Reranker unavailability preserves the ordinary fallback; the live evaluation rejects that run
before generator admission. Non-default rank thresholds/top-k disable the experimental planner
with an explicit unsupported-configuration diagnostic rather than silently using incompatible
hardcoded replay assumptions.

The normal Evidence adapter now optionally includes `retrieval_method` and
`semantic_score_gate_bypassed` metadata. Ordinary hits do not acquire new metadata keys. A TOC
hit is marked `explicit_toc_structure`: its original score remains visible, and `rerank_applied`
means it was scored, **not that it passed the semantic score gate**. The experimental Evidence
Tool preserves structural order instead of sorting it away by score. Existing six-hit and
10,000-character limits still apply, and IDs remain based on raw document/chunk/content identity.

The evaluation captures content-free stage diagnostics separately, hashes them alongside actual
retrieval/input files, and verifies their delivered chunk IDs before admitting the selector or
Writer. It does not load fixed-pool reference records or evaluator-only answer text.

## Reproduction

```powershell
# Default plan, no services or model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.rag_transfer --source-structure

# Three real local RAG queries against configured PostgreSQL/Qdrant; no generator yet.
.venv\Scripts\python.exe -m evals.reports_acceptance.rag_transfer --source-structure --retrieve

# Use the saved run from the previous command; at most six selector/Writer calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.rag_transfer --retrieved-run evals/results/rag_structure_assets_20261029T031933Z_57455c1eeb --execute
```

The flag applies when preparing retrieval, not when consuming an existing saved run. Without
`--source-structure`, prior CLI and runtime behavior remain unchanged. This execution used host
Python code against running Docker PostgreSQL/Qdrant services; the API container was not rebuilt
or deployed as part of this experiment. Generator calls used configured **qwen-flash**.

## Actual run and source-bound AI review

Retrieval run: `rag_structure_assets_20261029T031933Z_57455c1eeb`.
Generation run: `live_rag_transfer_20261029T032059Z_b088c04a04`.

The live corpus is still **2 documents / 117 chunks**, with canonical hash
`4f647f2fd3bda35b31ae8b8d58dcac4cc895ae6935fc5eb6ed787dfb90e909a3`, unchanged from the
earlier scoped corpus. Both manifests have identical implementation fingerprints and report
unchanged source/inputs; corpus snapshots before/after retrieval match. No label-based chunk
injection, query rewrite, additional source, retry or passing-result search was performed.

| Task | Actual retrieval / selection | Candidate output and initial AI review |
| --- | --- | --- |
| TOC chapter pairs | Real TOC delivered first; selector chooses it for both parts | Four requested chapter titles match the original TOC; both assertions cite that TOC |
| Survey year and adoption rates | Survey paragraph delivered third; selected for both parts | 2024 remains the survey year; 42% is overall, 64% is large retailers |
| Measured store uplift / sample size | Six topical passages retrieved; selector chooses none | Both parts remain unresolved; Writer is skipped; no corpus-wide absence claim |

The TOC is `ev1_local_document_4072a8b1a934c6f323e8aed5`, the same raw source identity as
before. Its original rerank position/score are not relabeled successful semantic relevance; the
new delivery is explicitly structural. The survey is
`ev1_local_document_33124c6985a61183e34ca2b0`. Selected quotes equal the entire original retrieved
chunks byte-for-byte; no model transcription or synthetic source summary replaces them.

Each retrieval batch returns **PARTIAL** with six records because eight pre-delivery hits are
limited to six. Context sizes are **3,538 / 2,409 / 2,603 characters**; none is truncated by
characters. PARTIAL is a retrieval-budget status, not a semantic rejection of the positive answers.
The negative task returns six records rather than zero: appropriate selection abstention is a
separate stage from empty retrieval.

Totals: **3 local RAG queries, 3 query embeddings, 3 local reranks, 5 generator calls** (three
selectors and two Writers), **0 Web searches/pages**. Scoped metadata/structure SQL reads occur
inside those RAG requests and are bounded as described above; these counts are not a count of
every individual PostgreSQL statement. Two positive tasks yield two candidate parts each; the
negative yields two unresolved parts. No assertions fail quote-link checks.

This corrects the earlier E4.7 TOC failure **in this repeatedly exposed three-task minimal
pipeline**. It does not establish full DeepAgent/report orchestration accuracy, an independent
holdout score, general TOC precision or broad document-name resolution. AI source review is not
human adjudication or a separate Judge score. Generated assertions retain their pending semantic
review status; human accuracy stays null. No earlier failed report is overwritten.

The private `AI_INITIAL_REVIEW.json` binds original retrieved records, selected excerpts and
assertions for reinspection. Raw reports, passages and responses remain ignored. The
[public record](../../evals/reports/e4-14-live-source-structure-2026-10-29.json) stores hashes,
methods, IDs, budgets, statuses and initial-review explanations without source passages.

## Verification and next stage

Focused regression: **48 passed**. Full regression: **630 passed, 6 skipped**. New tests cover
one-recall/one-rerank behavior, explicit score bypass and metadata, no hidden body reads on
unresolved sources, inventory overflow, out-of-pool structure, availability fallback, actual SQL
ready/knowledge-base isolation, ordinary-path compatibility, stable IDs, preserved structural
ordering, diagnostics hashing and rejection of rerank fallback before generation. Ruff lint and
format checks and `git diff --check` pass.

Next broaden structural negative/ambiguity cases and resolve the metadata/title coverage gap
identified by E4.13 using verified document metadata. Keep those checks separate from the three
exposed success examples. Only then consider exposing the option through a public request or
changing defaults; no promotion is justified by these three tasks alone.
