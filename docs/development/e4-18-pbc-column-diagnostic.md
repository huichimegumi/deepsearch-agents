# E4.18 — Fixed-stage diagnosis of the PBC column question

## Why this question was audited

In E4.17, the E4.16 retrieval for the new People's Bank of China question resolved the named
document and delivered six chunks, but the selector chose no quote for “专栏讨论了哪些政策传导问题”.
It would be premature to change the reranker, top-eight retention or source planner without
knowing where the relevant indexed material went. The question has **no independently verified
semantic answer reference**; this stage therefore records structural positions, not answer
recall or a claim that any particular column answers the question.

Five fixed probes in [`pbc_column_probes_v1.json`](../../evals/rag/suites/pbc_column_probes_v1.json)
identify the indexed column table of contents and the four actual column-body starts. The
probe IDs and heading markers are checked against the hash-bound archived E4.9 corpus. Its
finance-only subset reproduces the exact E4.16 finance corpus hash. The audit also verifies
E4.16's question, full hybrid candidate membership, rerank scores/order, source-scoped
threshold/top-eight retention, final six-hit delivery, and the E4.17 selector's empty choice.
All input files are hash-bound in the [public record](../../evals/reports/e4-18-pbc-column-diagnostic-2026-10-29.json).
No live database, vector search or model is called.

## Observed gates

| Structural probe | Vector rank | Hybrid candidate | Rerank rank / score | First losing gate |
| --- | ---: | ---: | ---: | --- |
| Column TOC | 24 | 33 | 1 / 3.235 | Delivered first |
| Column 1 body | 22 | 7 | 2 / 2.817 | Delivered second |
| Column 2 body | absent | absent | absent | Candidate pool |
| Column 3 body | absent | absent | absent | Candidate pool |
| Column 4 body | absent | 22 | 12 / 1.045 | Scoped top-eight retention |

The saved run had **33 hybrid candidates, eight source-scoped retained hits and six delivered
records**. The delivered TOC and column 1 body show that “retrieval found nothing” is false.
The missing column 2/3 bodies and column 4's rank also show why all four bodies were not
available to the selector. Its zero-quote decision is a separate observation: even the
delivered excerpts do not by themselves define which *policy transmission problems* the
question intends. Column headings cover different subjects. Treating those headings as a
semantic gold answer would fabricate a benchmark label.

The audit records each probe's first losing stage; a heading match is **not** evidence that a
passage supports the requested answer. No E4.17 output, source document, reference label,
threshold, ranking or ordinary API/UI behavior was changed. Human accuracy remains null.

## Reproduction and next decision

```powershell
# Requires the ignored E4.9 corpus, E4.16 retrieval and E4.17 selection artifacts.
# Offline only: no local RAG, generator or Web calls.
.venv\Scripts\python.exe -m evals.rag.audit_pbc_columns
```

Actual audit: `pbc_column_audit_20261029T080122Z_ca6bf7b362`, status `audited`, source and
inputs unchanged. Seven portable tests check stage attribution and rejection of a changed
retention gate. Full regression: **671 passed, 6 skipped**; Ruff lint/format and
`git diff --check` pass. This stage uses **zero** new local retrieval, embedding, rerank,
generator, Tavily or page-fetch calls.

Next freeze two unambiguous questions before any new run: one explicitly requests the four
column *headings*, the other asks about the fiscal/monetary coordination mechanism in column
1. Review the exact source support for each, then use a small live paired evaluation to see
whether candidate coverage and selector behavior change. Keep the current broad question as
an exposed failure/abstention case; do not tune a default on it alone.
