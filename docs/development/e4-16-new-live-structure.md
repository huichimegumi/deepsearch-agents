# E4.16 — New live source and structure checks

## Scope and frozen inputs

E4.15 left source resolution and TOC planning supported by authored component checks and
three repeatedly exposed report examples. This stage adds five **new, exposed development
prompts** in [`source_structure_live_v1.json`](../../evals/rag/suites/source_structure_live_v1.json).
Their questions, expected resolution and document hashes were written before the first run.
The dataset and unchanged two-knowledge-base corpus hashes are bound in the
[public record](../../evals/reports/e4-16-new-live-structure-2026-10-29.json).

The new runner performs one original-query PostgreSQL/Qdrant recall and local rerank per case,
then checks the experimental Evidence delivery. It records full diagnostics and passages only
under ignored `evals/results`; the public report contains statuses, counts and hashes. A run
without `--execute` writes a plan and makes no retrieval calls. No selector, Writer, Web search,
answer-key label or report generation participates. The five checks cover:

| Case | Frozen boundary | Final result |
| --- | --- | --- |
| `toc_new_chapters` | Positive request for chapters 03/04 in an explicitly named source | Unique indexed TOC first, from the requested document and recalled candidate pool |
| `toc_polite_negative` | `请勿列出目录` after a named source | Source scoped; no TOC reservation |
| `excluded_named_source` | Explicitly exclude a named document | `NO_EVIDENCE`, zero records and a specific unsupported-constraint warning |
| `pbc_attested_title` | Financial filename without its attested `63页` suffix | Resolved by indexed-page suffix; all six delivered records from the target document |
| `blackrock_attested_title` | Financial filename without its attested `17页` suffix | Resolved by indexed-page suffix; all six delivered records from the target document |

All four nonempty batches are `PARTIAL` because the existing six-hit answer limit truncates
the eight-hit retrieval selection. This is a budget status, not answer correctness. The checks
verify reranker execution, stable unique Evidence IDs, candidate membership, delivery binding,
source hashes and structure status. They do **not** verify that a delivered paragraph answers
the question or that a Writer can produce a faithful report.

## Failures, changes and final run

The first five-query pilot exposed two separate problems. The new check compared the runtime
document-hash tuple with a list, causing four false failures. More importantly, `请勿列出目录`
was not recognized as a negative structural request, so the TOC was reserved. Both original
sources are archived in the ignored pilot run and their hashes reconstruct its manifest.
The repaired lexical rule recognizes `请勿`, `勿列`, `勿生成`, `勿给出`, `勿提供`, `勿展示` and `勿输出`;
it remains a bounded lexical heuristic.

The second five-query run made all five *then-current* harness checks pass. A direct audit
revealed that its explicit source-exclusion case returned six chunks, all from the forbidden
document. The reason was an unsafe fallback to ordinary retrieval for
`unsupported_source_constraint`. The experimental path now returns zero records on that status.
It does not claim to search and enforce arbitrary alternative-source constraints. A third run
confirmed zero records, then exposed a misleading generic "no relevant chunks" warning. The
fourth run confirms the single specific suppression warning. Each run and its source fingerprint
is preserved; the public record distinguishes the pilot, the incomplete harness pass, safe
delivery and final warning correction. No failed run was overwritten or counted as final success.

Final live run: `source_structure_live_20261029T073039Z_ec97a5bfce`, **5/5 checks pass**.
Final component run: `structure_challenges_20261029T073214Z_d8618ac167`, **21/21 pass**.
The corpus and dataset hashes match across all four live runs. Total experimental cost is
**20 local RAG queries, 20 embeddings and 20 local reranks**, zero generator calls, zero Tavily
or other Web queries and zero fetched pages. These calls used host Python against the actual
Docker-backed PostgreSQL/Qdrant services; API containers were not rebuilt. The experiment
remains off by default in the ordinary API/UI path.

## Verification and interpretation

```powershell
# Plan only; no services or model calls.
.venv\Scripts\python.exe -m evals.rag.run_source_structure_live

# Explicit five-query local retrieval check.
.venv\Scripts\python.exe -m evals.rag.run_source_structure_live --execute

# Planner-only old challenges.
.venv\Scripts\python.exe -m evals.rag.source_structure_challenges
```

Full regression: **658 passed, 6 skipped**. Tests cover the new negative phrases, runtime
zero-delivery boundary, accurate warning, tuple/list harness regression, source-scope check and
five-case limit. Ruff lint/format and `git diff --check` pass. The result is a small development
boundary check, **not an independent holdout, retrieval recall benchmark or report accuracy
score**; human accuracy remains null. Before considering a public experimental switch, add
independently reviewed semantic support and report outcomes on a modest new task set, including
explicit exclusions and insufficient evidence. Do not infer general negation handling from
these lexical cases.
