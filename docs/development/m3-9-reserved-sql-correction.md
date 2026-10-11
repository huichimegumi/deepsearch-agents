# M3.9 Reserved SQL correction admission

## Live validation finding

The post-M3.8 `s2sql_041` validation kept the one-task limits of two Tavily queries, two fetched
pages, and one research round. It used exactly two queries and two pages and completed in about
210 seconds. The run collected two Web Evidence records and eleven SQL schema records, but no
analytical SQL Evidence.

The Supervisor made five admitted SQL attempts. Three completed without usable rows, two failed
with the bounded `unknown_column` category, and one additional call was blocked. Because the last
two admitted queries failed consecutively, the M3.7 correction gate treated the normal repair
budget as exhausted and did not start the structured correction phase. The trace therefore showed
zero correction attempts even though roughly 90 seconds remained in the run-level budget.

This distinguishes the failure from the M3.8 timeout: the 60-second structured proposal path was
not entered at all. No broader subset run was started.

## One reserved recovery slot

M3.9 separates normal Supervisor repair from the deterministic post-Supervisor correction. Once
real schema or sample Evidence exists and no analytical `query_result` exists, the correction may
propose one query even when two consecutive Supervisor queries have failed.

The exception is intentionally narrow:

- only the backend-set `sql_evidence_correction` phase receives the recovery admission;
- a query whose digest matches any failed query is still rejected;
- the proposal still passes through the unified Evidence Tool's read-only checks, single-statement
  validation, database timeout, and bounded result handling;
- the correction model is still invoked once and the backend executes at most one proposed query;
- normal Supervisor calls remain blocked after two consecutive failures;
- Web-query, fetched-page, and research-round limits are unchanged.

This is a reserved correction slot, not a reset of the SQL repair counter. A failed correction is
recorded as another failed SQL outcome and cannot reopen research.

## Trace schema v6

Trace schema v6 adds `sql_correction_admission_overrides`. The counter increments only when the
reserved correction slot admits a query that the normal consecutive-failure rule would have
blocked. Hybrid smoke output exposes the metric per task and as
`total_sql_correction_admission_overrides` for the run. Query text and database error text remain
absent from the portable trace.

## Verification boundary

Deterministic tests verify that:

- ordinary SQL remains blocked after an original failure and one failed repair;
- the correction gate remains available after those failures when schema Evidence exists;
- the phase-marked correction can execute one different read-only query against SQLite;
- an already failed query remains blocked even in correction mode;
- the recovery admission is counted in schema-v6 telemetry;
- all existing search, phase, Evidence, and citation tests continue to pass.

The implementation validation uses no network search. A future live check should reuse the same
single-task, two-query Tavily cap before considering the balanced three-task smoke subset.
