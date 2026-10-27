# E3.8: two Web and two simple cross-source development reports

This stage extends the six local E3.7 cases with four predeclared tasks. Its purpose is to finish
the planned small report-evaluation coverage, preserving failures and inspecting actual Evidence.
No production Agent route, generation prompt or recovery policy is tuned in this experiment.

## Frozen tasks and source references

| ID | Sources | Required facts/behavior | Query/page allowance |
| --- | --- | --- | --- |
| report_web_001 | Web | Python 3.13.0 release date; experimental free-threaded status; optional build/install behavior | 3 / 3 |
| report_web_002 | Web | PostgreSQL 17.0 release date; JSON_TABLE capability; incremental backup and pg_combinebackup | 3 / 3 |
| report_cross_001 | Local + Web | Compare the local PBOC report's May 2025 reverse-repo rate change with official effective date/rates; preserve percentage-point/basis-point units | 4 / 4 |
| report_cross_002 | SQL + local | Query the actual indexed-chunk inventory and describe two digital-human scenarios; explain that chunk count does not prove exhaustive coverage | 0 / 0 |

Primary evaluator references were verified before model execution and saved privately:

- [Python 3.13.0 release](https://www.python.org/downloads/release/python-3130/) and
  [Python 3.13 free-threading documentation](https://docs.python.org/3.13/howto/free-threading-python.html):
  the release is dated 2024-10-07; free threading is experimental and opt-in for this version.
- [PostgreSQL 17 release announcement](https://www.postgresql.org/about/news/postgresql-17-released-2936/):
  dated 2024-09-26, with SQL/JSON support and incremental-backup/reconstruction capabilities.
- [PBOC 2025 first-three-quarter policy chronology](https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/5896228/index.html):
  confirms the 2025-05-08 change from 1.50% to 1.40%, a 0.1-percentage-point reduction.

These are historical, source-constrained questions rather than latest-version or financial advice
requests. The natural-language task names the subject and allowed sources, but receives neither
the reference passages nor reference answers. Sources fetched during the actual run, not these
evaluator snapshots, supply Web Evidence. Official source text may change; both reference and actual
retrieved material have their own hashes. Frozen annotations remain agent-verified pending human review.

The SQL task uses a read-only SQLite snapshot generated from the actual PostgreSQL/Qdrant corpus
inventory. It is not a synthetic transaction benchmark or a DABStep fee test. Unique document/chunk
identities are counted to avoid duplicate KB associations. The target whitepaper has **59** indexed
chunks in this snapshot. This answer is evaluator-only; the model must obtain it through SQL.
No existing knowledge base or database table is replaced. The original five-document corpus is unchanged.
Inventory metadata and document text originate from the same corpus: this tests two tool modalities,
not independent corroboration by two factual authorities.

## Execution and evaluation boundary

`extended.py --prepare` freezes the task-file hash, corpus file/fingerprint, inventory database,
independent SQL reference and primary-page snapshots under a unique ignored asset directory.
Preflight verifies every local/Web anchor and reruns the independent read-only inventory query.
Execution requires the frozen lock, `--execute` and `--allow-paid-search`. Preflight alone invokes
no project generator or Tavily search. Reference preparation uses direct HTTP downloads, separately
from the Agent's search requests.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.extended --prepare
.venv\Scripts\python.exe -m evals.reports_acceptance.extended --lock <asset-directory>/lock.json
.venv\Scripts\python.exe -m evals.reports_acceptance.extended --lock <asset-directory>/lock.json --execute --allow-paid-search
```

The backend is locked to Tavily. Fixed per-case query allowances sum to ten; unused or unobserved
capacity is never transferred to another case. This also avoids refunding an interrupted task's
possibly in-flight requests. Page allowances likewise sum to ten. The counters describe admitted
queries and fetched pages, not a verified credit invoice or transparent SDK-internal HTTP retries.
The existing project provider makes one search call per admitted query, with no advanced aggregation
or automatic backend fallback enabled in this runner.

The unchanged deep_report profile provides 300 seconds, a 75-second Writer reserve and configured
12-call allowance, plus the existing outer watchdog of 330 seconds per case. All effective limits
are recorded in the manifest. The default researcher is used, SQL entity-recovery opt-in remains
false, and the SQL task uses existing schema/query/correction support. Scoped environment settings
are restored after each case. Run/session names are unique and no old artifacts are deleted.

The shared `execute_case` receives optional explicit limits and a source-aware auditor. Existing
local callers retain zero network budgets and their previous audit. New checks distinguish all
observed sources, claim-eligible sources, collected/cited required sources, unexpected sources,
and individual reference-unit retrieval/citation. SQL schema/sample/semantic discovery cannot satisfy
the analytical-SQL requirement. Official Web hosts and exact local document identities are checked;
SQL count checks require the reference result field/value. These are conservative mechanical
signals, including a possible SQL-alias false negative; they do not prove semantic correctness.

Raw reports, Evidence, Trace, references and unapproved worksheets remain private. Input/source/
corpus/database drift invalidates the run. AI content review is labeled separately from human
adjudication. Report-generation outcomes and factual judgments must be read alongside the source
and reference coverage, including fallback/notice delivery.

## Actual results, 2026-10-27

Frozen assets: `extended_assets_20261027T052916Z_6051bf3cf6`; preflight-only run:
`extended_reports_20261027T053027Z_73c8a46d8f`; actual execution:
`extended_reports_20261027T053213Z_967bc25670`. The execution uses `qwen-flash`, default research
route and HEAD `bbc968f7` plus the new evaluation code. Its dirty flag and exact source-byte
fingerprint are recorded; this is not claimed as a clean pre-existing release. Source, task,
corpus, lock, reference snapshots and SQLite checks passed before/after generation.

| Task | Execution | Seconds | Queries / pages | Eligible sources collected / cited | Reference units retrieved / cited | Delivery / AI initial finding |
| --- | --- | ---: | --- | --- | --- | --- |
| Web 001 | degraded | 161.219 | 3 / 3 | Web / none | 3/3 · 0/3 | Misrouted local no-evidence notice; actual Web evidence not synthesized |
| Web 002 | degraded | 56.343 | 3 / 3 | Web / none | 2/3 · 0/3 | Same misrouting; incomplete backup Evidence as an additional gap |
| Cross 001 | degraded | 44.047 | 3 / 1 | Web / Web; local missing | 0/2 · 0/2 | Claim fallback; third-party figures, no official/local corroboration |
| Cross 002 | degraded | 61.906 | 0 / 0 | SQL + local / SQL + local | 1/2 · 1/2 | Claim fallback; verified count 59, specific scenarios not adequately answered |

All four results, snapshots and traces were saved, with actual Markdown artifacts matching the
delivered reports. The CLI exits 1 because rows are degraded, not because they were omitted or
inputs drifted. Median duration is **59.125 seconds**, range **44.047–161.219**. Recorded admitted
Tavily queries are **9**, fetched pages **7**, below the fixed batch allowances. No rerun, additional
search or extra project Judge API call was used for AI initial review. Instrumented LLM calls
total 22; nested-agent/provider calls are incompletely metered, so this is not a billing total.

The required eligible source types were collected on 3/4 tasks and cited on 1/4. Only Python's
complete finite reference set was retrieved; no task cited all required reference units. These
counts are mechanical coverage, not a factual correctness/acceptance score. All four final
citation checks fail at least once; the first two failures concern a substituted technical notice,
while the latter two follow actual Writer model outputs.

## What the failures establish

**Source-intent misclassification is the highest-priority isolated runtime defect.** Both Web
questions contain a natural negative constraint against local KB use. The existing
`_requires_local_knowledge_base_only` detects the local phrase plus an exclusivity phrase elsewhere
and returns true, despite the positive Web-only request. Both traces prove:

- `local_retrieval.required=true` and zero local records, although three Web records exist;
- the compression and final-report phases invoke no model and take the local-Evidence boundary;
- final delivery explains absent local evidence instead of answering the Web question.

For Python, all three source-reference units are already available in the real fetched official
release page. Thus missing Web evidence alone cannot explain this failure. The research phase
also timed out, but after it ends the incorrect local-only gate independently discards synthesis
of the available Web evidence. PostgreSQL additionally spends capacity on a 17.10 maintenance
page and mailing-list page; its bounded 17.0 text contains incremental-backup support but not
`pg_combinebackup`. Fixing intent classification alone therefore does not guarantee every keypoint.

**Cross 001 lacks required sources.** It returns a third-party financial-news page with the
correct date and rate figures, while local retrieval returns no record and no official page is
fetched. The fallback transparently admits these gaps in places, but its suggested outline also
asserts that the knowledge base does not contain the description. The frozen local reference
does contain that event. This is an unsupported absence assertion in mixed-source output, beyond
the existing local-only wording gate. The finite official-source unit correctly gives no credit
to the third-party page, even though its numerical statement agrees with the reference.

**Cross 002 establishes a real SQL/local handoff, with incomplete answering.** The model first
describes the inventory schema and executes an analytical query returning the independently
verified 59. It also collects/cites local passages. However, the local query is essentially the
document title: returned passages describe history, costs, consumer needs and technology rather
than the referenced concrete scenarios. The fallback offers benefit/need categories instead of
clearly answering two concrete applications. It unnecessarily treats the question as requiring
an official canonical two-category taxonomy. Writer generated unknown citation IDs, so its body
was replaced with the Claim package. A source-filename `.pdf` mention also triggers the existing
artifact detector's incidental PDF conversion; no new PDF behavior was added here.

The private worksheet `evals/results/e3-8-ai-triage-20261027/AI_REVIEW.md` preserves exact delivered
and actual Evidence quotations. It explicitly distinguishes an evaluator-only local reference,
which the agent did not retrieve, from an actual retrieved Evidence ID. AI findings are selective,
provisional and not submitted to the human-attestation workflow. Human accuracy and claim-support
rates remain null.

## Ten-task coverage now available

| Case | Preserved batch | Execution | Delivered content |
| --- | --- | --- | --- |
| Local 001 | E3.7 | completed | report |
| Local 002 | E3.7 | degraded | report |
| Local 003 | E3.7 | degraded | Claim fallback |
| Local 004 | E3.7 | degraded | Claim fallback |
| Local 005 | E3.7 | degraded | Claim fallback |
| Local 006 | E3.7 | degraded | bounded no-evidence notice |
| Web 001 | E3.8 | degraded | misrouted local notice inside citation fallback |
| Web 002 | E3.8 | degraded | misrouted local notice inside citation fallback |
| Cross 001 | E3.8 | degraded | Claim fallback |
| Cross 002 | E3.8 | degraded | Claim fallback |

This is ten distinct development questions across two preserved executions/dates, not one new
ten-task controlled run or pooled accuracy result. The six local rows are bound to the E3.7
record hash and retain their original clean execution provenance. The application source itself
is unchanged across these two stages; this stage adds only evaluation support and data.

The [content-free result record](../../evals/reports/e3-8-web-cross-source-reports-2026-10-27.json)
contains the frozen lock, manifests, per-task counts/hashes, AI-review hashes and ten-task coverage
inventory. Raw page/document passages and generated reports remain under ignored results.

Full regression: **448 passed, 6 skipped**; changed-file Ruff lint/format passes. Eighteen added
tests cover official-domain matching, discovery-versus-query eligibility, cited-source separation,
reference lock and SQL/corpus/page drift, safe paths, paid opt-in, no gold injection, fixed disjoint
query allowances, environment restoration and retention of degraded rows. Prior local tests pass.

## Next measured improvement

The second-phase coverage experiment is complete; quality gates are not passed. For E4, select
the source-intent misclassification as one bounded improvement: preserve the two original Web
questions and reference data, fix positive/negative source restriction handling without task-ID
special cases, protect local-only/mixed-source behavior with regression tests, then compare the
same two tasks under a separately recorded bounded run. Preserve this failed baseline. A corrected
gate must not imply that timeout, irrelevant retrieval, citation errors or factual support have
also been solved. Human review may continue alongside this work.
