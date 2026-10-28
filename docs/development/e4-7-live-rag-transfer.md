# E4.7 — Actual local RAG to ID selection and Writer

## Implemented boundary

The E4.6 fixed-pool experiment is now connected to the actual local RAG Evidence collector in an
opt-in evaluation path. It reuses the same three frozen questions, ID selector and Writer; it
does not execute the complete production Supervisor workflow or change production defaults.

Each original question is submitted once to `_collect_local_documents` for the explicitly scoped
`电商行业` knowledge base. The runner does not read fixed-pool snapshot contents, known record IDs
or answer anchors when preparing generation inputs. No filename filter, manual source addition,
query rewrite, second retrieval or targeted repair is applied after seeing results.

Retrieval and generation are separate steps. Retrieval writes a corpus snapshot, actual Evidence
batches and per-case inputs, including status/timing/rerank metadata. It compares corpus/source
fingerprints before and after the batch. Infrastructure failures or corpus drift make the run
ineligible for generation. The Writer step verifies hashes, frozen questions and exact
retrieval-to-input binding before admitting model calls; it can consume the saved retrieval
batch without querying the services again. Empty retrieval skips both selector and Writer.

Only returned Evidence is available to selection. The existing backend resolves selected IDs to
original chunks and checks Writer links; it does not establish relevance or entailment.

```powershell
# Default: plan only; no service/model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.rag_transfer

# Three local RAG queries, no generator calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.rag_transfer --retrieve

# Inspect/replay the verified batch offline; add --execute to admit up to six model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.rag_transfer --retrieved-run evals/results/rag_transfer_assets_20261028T033659Z_a8cacb2e19 --execute
```

`--execute` requires an explicit retrieved-run path. Search queries/page fetches are always zero;
provider retries are disabled and each selector/Writer call has a 90-second timeout.

## Actual infrastructure execution

Docker PostgreSQL, Qdrant and the supporting stack were running. The scoped corpus contains
**2 documents / 117 chunks**, and its fingerprint is unchanged across retrieval. It is a subset
of the earlier all-knowledge-base corpus, not a newly interchangeable corpus baseline.

Configuration: `BAAI/bge-small-zh-v1.5` embedding, `BAAI/bge-reranker-base` reranker, vector/lexical
candidate limits 24/24, rerank limit 8, minimum relevance score 1.0. All three returned batches
are `PARTIAL` under the existing context budget and each contains six Evidence records. All
18 returned records report `rerank_applied=true`; this does not characterize discarded candidates.

Retrieval run: `rag_transfer_assets_20261028T033659Z_a8cacb2e19`.
Generation run: `live_rag_transfer_20261028T033816Z_6db384a396`.
Total: **3 local RAG queries, 5 logical model calls, 0 searches, 0 fetched pages**. Generator
usage: 16,794 input tokens / 688 output tokens. These counts exclude local embedding/reranking
inference. One generation sample per case is retained; nothing is retried for a passing result.

| Task | Returned records | Linked candidate parts | Unresolved parts | AI initial content assessment |
| --- | ---: | ---: | ---: | --- |
| Chapter titles | 6 | 2 | 0 | Incorrect chapter identities/order |
| Survey year/subgroups | 6 | 2 | 0 | Complete within returned Evidence |
| Missing measured outcomes | 6 | 0 | 2 | Appropriate bounded nonanswer; Writer skipped |

## Failure localization

The chapter-title question does not retrieve the known actual table-of-contents chunk. Returned
pages are topically related, but the selector chooses foreword/history/policy/application pages
as support. The Writer then labels these page headings as the first four chapter titles. Both
assertions pass ID/link checks but are wrong. Each also names a second heading absent from its
one cited record. This exposes **retrieval omission, insufficient selection and unsupported
Writer ordering**, not a source-ID registration bug.

The frozen table-of-contents reference is inspected only after generation for evaluation. It
stays out of retrieval inputs, selector prompts and Writer context. No saved correct excerpt is
injected to make this live path appear successful.

The survey question retrieves the actual paragraph used in the earlier fixed-pool diagnostic.
Its year and overall/large-retailer proportions remain distinct in the candidate. The negative
question receives six related chunks, but the selector returns no supporting IDs; backend
delivery preserves both unresolved parts without a corpus-wide absence claim. That is selector
abstention plus backend handling, not successful negative-case Writer reasoning.

AI initial review covers all five delivered assertion entries, marking the two chapter-title
entries unsupported/incorrect and checking the survey statements against their source context.
The negative case's six returned chunks are also reviewed for the requested measured outcomes.
Judgements remain provisional AI work, not human acceptance or a trusted Judge score. Four
linked parts must not be reported as four correct answers; no pooled accuracy is calculated.

## Verification and next step

Full regression: **543 passed, 6 skipped**. Six new tests cover default plan isolation, one-query
original-question retrieval without old pools, infrastructure/corpus-drift rejection, retrieved
input integrity, and zero-model handling of truly empty retrieval. Ruff lint/format and
`git diff --check` pass. Both retrieval and generation source fingerprints match final Python
code; input/output/corpus/review hashes are verified. The
[content-free record](../../evals/reports/e4-7-live-rag-transfer-2026-10-28.json) retains the scoped
corpus, configuration, stage counts and failed outcomes. Raw source content and checked AI
worksheets remain ignored in `evals/results/`. Human accuracy remains null.

Next compare the original full question with concise question-part retrieval queries under a
fixed small local-query budget, using retrieval-only diagnostics first. Preserve this failed
chapter output to test whether the selector abstains when topic relevance lacks the requested
structural evidence. Do not add a chapter-name keyword exception or enable this path as the
production default merely because the survey example works.
