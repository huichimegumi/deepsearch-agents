# HybridDeepResearch smoke evaluation

This adapter is an engineering smoke test for cross-source orchestration. It is not a benchmark
score and must not be compared with results on all 380 HybridDeepResearch tasks.

## Fixed inputs

- Tasks: `Snowflake/HybridDeepResearch` release revision
  `31304784b7aec82f22d59772a8afeb78567fd8b3`.
- Database: `birdsql/livesqlbench-base-lite-sqlite` revision
  `0664a2f28555faa0dd2947c8c23288df79bcc06b`.
- Smoke subset: `s2sql_041`, `sql2s_192`, and `parallel_053` from the upstream official subset.
- Database: all three tasks use `alien`, so the smoke run downloads only one SQLite domain.

The three IDs cover Search-to-SQL, SQL-to-Search, and Parallel Fusion once each. This is the
smallest balanced routing check. It can expose broken modality handoffs, but its correctness rate
has no statistical meaning.

Upstream tasks are encrypted with a public canary to reduce accidental benchmark contamination.
This adapter verifies and decrypts selected records in memory. Never commit decrypted questions,
gold answers, reference SQL, model outputs, or evaluation logs.

## Prepare and inspect the budget

```powershell
.\.venv\Scripts\python.exe -m evals.hybrid.download_dataset
.\.venv\Scripts\python.exe -m evals.hybrid.run_smoke --json
```

The second command is a dry run. It writes no agent answer and performs no Web search. The fixed
default limits are:

- three tasks total;
- at most two search queries per task;
- at most two fetched pages per task;
- at most six search queries and six fetched pages for the complete smoke run.

The default backend is hard-locked to `duckduckgo`, which does not use the configured Tavily API
key even if the model requests `advanced`. Modes that
may consume paid credits (`tavily`, `perplexity`, `auto`, and `advanced`) fail closed unless the
operator also passes `--allow-paid-search`.

For an explicit diagnostic run, the frozen two-query/two-page defaults can be overridden with
`--max-search-queries N` and `--max-fetched-pages N`. Each value is independently capped at 10 per
task. The output records both the effective limits and whether an override was used. Paid backends
still require the separate `--allow-paid-search` flag.

## Execute

```powershell
.\.venv\Scripts\python.exe -m evals.hybrid.run_smoke `
  --execute `
  --search-backend duckduckgo
```

To intentionally use Tavily:

```powershell
.\.venv\Scripts\python.exe -m evals.hybrid.run_smoke `
  --execute `
  --search-backend tavily `
  --allow-paid-search `
  --limit 1 `
  --max-search-queries 6 `
  --max-fetched-pages 6
```

Results are written under ignored `evals/results/`. They contain task IDs, statuses, budget usage,
evidence counts, citation validity, and correctness booleans, but not decrypted task or answer
content.

## Evaluation boundary

For Search-to-SQL, the runner extracts the submitted read-only SQL, executes it against the pinned
SQLite database, and compares result tables. SQL-to-Search and Parallel use conservative normalized
gold containment as a local smoke signal; the official benchmark uses an LLM judge. The local
metric is therefore named `strict_correct`, not official accuracy.

Every task also reports whether both SQL and Web Evidence were collected, whether final citations
passed backend validation, elapsed time, query/page usage, and accepted/rejected Claim counts.

## First DuckDuckGo baseline

The first post-fix execution on 2026-10-05 is recorded in
[`docs/development/m3-2-hybrid-smoke-baseline.md`](../../docs/development/m3-2-hybrid-smoke-baseline.md).
It used four of the six allowed queries and no intentionally authorized paid backend. All three
reports passed citation validation, two collected both source types, and none passed the strict
answer check. This is a diagnostic baseline, not a result to optimize by leaking task-specific gold
information into prompts.

M3.3 addresses the observed column-guessing failure mode. The evaluator now requires
`collect_evidence(source=sql, operation=describe_schema)` before query construction. The operation
returns stable Evidence for columns, keys, and indexes across the mounted SQLite database. A
separate `sample_table` operation accepts an exact catalog table name and returns at most three rows
when value-domain inspection is necessary. See
[`docs/development/m3-3-sqlite-schema-discovery.md`](../../docs/development/m3-3-sqlite-schema-discovery.md).

M3.4 bounds SQL repair at the Evidence Tool boundary. A failed query may be replaced once; the
same failed query cannot be repeated, and a second consecutive failure blocks further SQL execution
for that run. A successful repair resets the counter. Smoke results include SQL attempts, failures,
blocked calls, and schema-discovery calls without storing SQL text in the trace. See
[`docs/development/m3-4-bounded-sql-repair.md`](../../docs/development/m3-4-bounded-sql-repair.md).

M3.5 moves the hybrid runner from the 180-second `standard` profile to the 300-second
`deep_report` profile after a one-task run timed out before its first research tool call. Search
remains capped at two queries and two fetched pages per task, with one research round, so the change
adds model execution time without increasing external-search use. See
[`docs/development/m3-5-hybrid-phase-budget.md`](../../docs/development/m3-5-hybrid-phase-budget.md).

The post-M3.5 one-task run reached schema discovery, three bounded samples, two DuckDuckGo pages,
and valid cross-source citations, but it executed no analytical SQL and remained strictly incorrect.
M3.6 therefore classifies schema and samples as discovery-only Evidence. They remain visible for
planning but cannot support final Claims; only explicit `operation=query` results are claim-eligible.
The hybrid runner marks a missing analytical query as an evidence requirement failure. See
[`docs/development/m3-6-analytical-sql-evidence-gate.md`](../../docs/development/m3-6-analytical-sql-evidence-gate.md).

M3.7 gives discovery-only runs one SQL-only correction before that failure is finalized. It uses a
single model call with only `collect_evidence` bound, admits exactly one analytical SQL tool call,
and cannot invoke Web search or consume a second research round. The existing two-query/two-page
external-search caps are unchanged. Smoke output includes `sql_correction_attempts` and
`sql_correction_successes` per task and in aggregate. See
[`docs/development/m3-7-sql-only-correction.md`](../../docs/development/m3-7-sql-only-correction.md).

M3.8 replaces model-selected correction tool calls with a structured `SQLCorrectionProposal` that
the backend deterministically maps to one read-only SQL Evidence call. This follows two live
`s2sql_041` checks: the first used zero searches and produced no correction tool call; the second
used exactly two Tavily queries and one fetched page, restored cross-source Evidence and citation
validity, but exhausted the 45-second correction window. Web Evidence is now ordered first in the
bounded correction ledger, the full frozen schema fits in the context allowance, and the single
correction call has a 60-second cap. See
[`docs/development/m3-8-structured-sql-correction.md`](../../docs/development/m3-8-structured-sql-correction.md).

M3.9 follows a third `s2sql_041` live check that used exactly two Tavily queries and two fetched
pages. The run retained cross-source Evidence but ended its Supervisor phase with two consecutive
unknown-column failures, so the existing repair gate prevented structured correction from starting
despite roughly 90 seconds of run budget remaining. The correction phase now has one reserved SQL
admission: it may cross the exhausted consecutive-failure limit, while duplicate failed SQL and all
read-only/runtime constraints remain enforced. Smoke output reports
`sql_correction_admission_overrides` per task and in aggregate. See
[`docs/development/m3-9-reserved-sql-correction.md`](../../docs/development/m3-9-reserved-sql-correction.md).

M3.10 follows the first post-M3.9 validation, which used exactly two Tavily queries and one fetched
page. Structured correction started successfully but returned a query with an unknown column,
confirming that proposal repair—not scheduling or more retrieval—was the next boundary. When the
first correction query returns `ERROR`, the phase may now request one different structured query
against the same schema ledger. Valid empty results are not retried, and both attempts share the
existing correction deadline and external-search limits. Smoke output reports
`sql_correction_repair_attempts` and `sql_correction_repair_successes` per task and in aggregate.
See [`docs/development/m3-10-error-aware-sql-correction.md`](../../docs/development/m3-10-error-aware-sql-correction.md).

M3.11 follows a run that used exactly two Tavily queries and two fetched pages, completed three SQL
queries without errors, produced analytical SQL Evidence, and passed citation validation. Strict
scoring still failed because the report omitted the required SQL fence. The runner now explicitly
requests executed-SQL output. Runtime-only provenance selects the query associated with accepted
Claim Evidence when possible, removes model-written SQL fences, and appends exactly one query that
was actually executed. Portable traces continue to omit SQL text and report only
`report_sql_query_attached`; smoke output exposes `executed_sql_attached`. See
[`docs/development/m3-11-executed-sql-output.md`](../../docs/development/m3-11-executed-sql-output.md).

M3.12 follows the first post-M3.11 run, which used exactly two Tavily queries and two fetched pages,
collected both source types, and passed citation validation. Its valid correction SQL returned zero
rows because of an over-constrained location filter, so no analytical Evidence or executed SQL was
available. The existing second structured proposal may now follow `NO_EVIDENCE` as well as
`ERROR`. Empty-result repair must preserve the requested entity and computation and may relax only
filters unsupported by the collected Evidence. It shares the same 60-second deadline and adds no
search or research-round capacity. Smoke results expose
`sql_correction_empty_result_repair_attempts` and
`sql_correction_empty_result_repair_successes` per task and in aggregate. See
[`docs/development/m3-12-empty-result-sql-repair.md`](../../docs/development/m3-12-empty-result-sql-repair.md).

M3.13 follows a post-M3.12 run that used exactly two Tavily queries and two fetched pages. The run
completed with cross-source Evidence, valid citations, analytical SQL Evidence, and an attached
executed query, but entity resolution failed and strict SQLite comparison remained false. The
runner now supports explicit per-task query and fetched-page overrides capped at 10 while keeping
the frozen defaults unchanged. Reports disclose the effective budget and whether it was
overridden; paid backends still fail closed without separate authorization. See
[`docs/development/m3-13-evaluation-retrieval-overrides.md`](../../docs/development/m3-13-evaluation-retrieval-overrides.md).

M3.14 follows the first expanded one-task run. With a 6/6 override it actually used five Tavily
queries and three fetched pages, but an upstream model request timed out before any analytical SQL
could run. Previously that provider-specific exception escaped the Supervisor boundary and ended
the complete workflow even though collected Evidence and roughly half the run budget remained.
Timeout wrappers are now recovered as a degraded `upstream_timeout` phase so SQL correction,
compression, and writing can continue. Smoke output exposes `upstream_timeout_recoveries` per task
and in aggregate. See
[`docs/development/m3-14-upstream-timeout-recovery.md`](../../docs/development/m3-14-upstream-timeout-recovery.md).

The post-M3.14 6/6 validation consumed six Tavily queries and six pages and completed every phase,
but it still produced no analytical SQL Evidence: five of seven SQL attempts returned no rows and
both correction proposals used an invented physical column for a named derived metric. M3.15 mounts
the two semantic sidecars already covered by the dataset lock. `describe_schema` merges pinned
business meanings into physical columns, while `search_semantic_knowledge` retrieves at most eight
matching domain formulas. SQL correction prefetches those rules deterministically. These records
remain discovery-only and cannot support final Claims without a successful analytical query. The
runner reports whether both sidecars are mounted plus semantic columns, discovery calls, and record
counts. See
[`docs/development/m3-15-pinned-sql-semantics.md`](../../docs/development/m3-15-pinned-sql-semantics.md).

The first post-M3.15 live run used all six authorized Tavily queries and five of six fetched pages.
All five analytical SQL attempts succeeded, analytical Evidence was available, and one executed
query was attached. The previous unknown-column correction failure was therefore resolved. The run
still degraded because the Supervisor did not select formula discovery and Compression reused five
discovery-only schema IDs; all six proposed Claims were rejected and report citation validation
failed. M3.16 makes both boundaries deterministic: the backend prefetches task-relevant pinned
formulas before Supervisor research, while Compression receives a newly rendered ledger filtered to
Claim-eligible IDs rather than raw Supervisor prose. The prefetch consumes no external-search or
research-round budget. See
[`docs/development/m3-16-deterministic-semantic-handoff.md`](../../docs/development/m3-16-deterministic-semantic-handoff.md).

The post-M3.16 run authorized a 6/6 Tavily budget but issued no Web search. Both backend semantic
prefetches ran and Compression submitted no unknown Evidence IDs, confirming the deterministic
scheduling and Claim-safe handoff. Analytical SQL still failed because the exact top-level formula
referenced two `children_knowledge` formulas that were not returned; unrelated lexical matches used
the remaining semantic slots. M3.17 expands exact-match dependency graphs within the existing
eight-record cap and grounds every formula identifier to physical SQLite `table.column` pairs. Each
semantic record also carries the full physical columns for its relevant tables, so query construction
does not depend on a distant or truncated schema record. A no-network check of the locked assets
returned one parent and its two required dependencies with all inputs grounded across the relevant
tables. See
[`docs/development/m3-17-semantic-dependency-closure.md`](../../docs/development/m3-17-semantic-dependency-closure.md).
