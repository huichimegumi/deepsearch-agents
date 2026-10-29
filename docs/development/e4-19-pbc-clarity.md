# E4.19 — Clarified PBC questions, column index and paired Writer check

## Frozen questions and pilot

E4.18 showed that the broad “专栏讨论了哪些政策传导问题” question had no verified semantic
reference. This stage freezes two narrower, source-verified development questions in
[`pbc_clarity_v1.json`](../../evals/reports_acceptance/pbc_clarity_v1.json): list the four numbered
column titles from the report's index, and state the three policy-coordination methods that
column 1 explicitly describes. Each has an exact indexed chunk ID, content hash and document
hash. The finance corpus matches the previously published E4.16 hash.

For each question, one **ordinary** and one **opt-in experimental** PostgreSQL/Qdrant retrieval
use the same original query and normal limits. Each saved retrieval then passes through the
same frozen ID selector and Writer. The pilot had four local queries and eight qwen-flash logical
calls. The title-index chunk reached both candidate pools but ranked **11** and was not
delivered. The experimental planner reported `structure_missing` because it recognized a
generic “目录” page but not this report's separate `专栏` index. Writer still emitted candidate
titles by treating column 1's numbered policy measures as later column headings. This is a
real source-semantic failure despite structurally valid Evidence IDs; the pilot is preserved.

## Narrow experimental repair and actual result

The structural detector now recognizes a standalone `专栏` index header with at least three
unique, consecutive numbered entries and printed dotted page leaders. A body paragraph headed
`专栏 1`, a duplicate/missing number, a missing header or leader, and a single listed item are
not accepted. Across the five-document archived corpus, this identifies only the actual PBC
column index in addition to the existing ecommerce TOC. The source must still be explicitly
resolved, the question must request a directory, and the unique structural chunk must already
belong to the recalled candidate pool; normal API/UI routing does not use this experiment.

The second paired retrieval again placed the PBC index **11th** in the ordinary rerank. The
experimental path selected it structurally and delivered it **first**, with the original
Evidence ID and explicit retrieval-method metadata. Its actual score was about **1.235**, above
the configured score threshold; the reservation bypassed the top-eight ranking cutoff, not a
failed numeric score gate. The other question's reference body remained rank/delivery **1** in
both retrieval variants. Corpora and frozen questions were unchanged between the pilot and
repair. The existing 21 structural component challenges still pass.

The offline, hash-bound [literal review](../../evals/reports/e4-19-pbc-clarity-2026-10-29.json)
extracts the four numbered titles from the original indexed page and verifies each Writer
assertion's number, exact title string and citation to that page:

| Question / condition | Pilot | Repaired run |
| --- | --- | --- |
| Four column titles, ordinary | Index not delivered; 1 exact title string, no index citation | Index not delivered; 1/4 exact title strings, no index citation |
| Four column titles, experimental | Index not delivered; 1/4 exact strings, no index citation | Index first; 4/4 exact strings, each cites the index |
| Three column-1 methods, ordinary | Reference first; 2/3 whole statements literal in their cited excerpts | Reference first; 3/3 literal in their cited excerpts |
| Three column-1 methods, experimental | Reference first; 3/3 literal | Reference first; 2/3 literal; third sentence appears in another delivered chunk, not the cited continuation |

The Writer's method-citation difference flips across the two model runs. It is a **citation
assignment problem**, not loss of the method sentence from the delivered evidence. The
existing ID-link audit permits such a mismatch. Exact-string checks are narrow source-text
checks, **not general entailment, report accuracy or an independent holdout score**. A human
has not adjudicated the candidates; human accuracy remains null. The repaired experimental
index result is promising for this exposed case, but the varying method citations and other
unreviewed document shapes do not justify a production default change.

## Provenance, cost and reproduction

Both paired retrievals, both Writer runs and their offline reviews are preserved. The first
planner source is archived privately; its hash reconstructs the pilot's implementation
fingerprint. The [public record](../../evals/reports/e4-19-pbc-clarity-2026-10-29.json) has
case IDs, statuses, ranks, literal checks, hashes and call counts, without source passages or
model responses. Each live run reports unchanged source, dataset and corpus; each Writer run
reports unchanged source and inputs.

```powershell
# Plan only.
.venv\Scripts\python.exe -m evals.reports_acceptance.pbc_clarity

# Four actual local queries, no generation.
.venv\Scripts\python.exe -m evals.reports_acceptance.pbc_clarity --retrieve

# Up to eight selector/Writer logical calls on a verified saved retrieval.
.venv\Scripts\python.exe -m evals.reports_acceptance.pbc_clarity `
  --retrieved-run evals/results/pbc_clarity_assets_20261029T081513Z_906740335f --execute

# Offline literal/structural review of the saved paired outputs.
.venv\Scripts\python.exe -m evals.reports_acceptance.pbc_clarity_review `
  evals/results/pbc_clarity_assets_20261029T081513Z_906740335f `
  evals/results/pbc_clarity_writer_20261029T081636Z_fa2b881d1b
```

Across pilot and repaired runs: **eight local queries, eight embeddings, eight local reranks,
16 qwen-flash logical calls, zero Web queries/pages**. Final full regression: **677 passed,
6 skipped**. Tests cover strict index recognition, malformed index negatives, corpus/hash
binding, four-title checking, cited-passage literal checking and unknown citation rejection.
Ruff lint/format and `git diff --check` pass. Next isolate and prevent the Writer's wrong
assertion-to-passage citation when the correct sentence is present in a different delivered
chunk, without pretending literal matching proves semantic support.
