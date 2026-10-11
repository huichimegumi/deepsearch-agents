# M3.11 Executed SQL output provenance

## Live validation finding

The post-M3.10 `s2sql_041` validation used exactly two Tavily queries and two fetched pages. It
collected both source types, completed three analytical SQL queries without errors, produced five
`query_result` Evidence records, and passed final citation validation. Correction and correction
repair were not needed because the Supervisor produced analytical Evidence directly.

Despite that progress, the local strict check remained false. The final report did not contain the
required fenced SQL query, so the evaluator had no predicted query to execute. The failure was
therefore an output-contract failure before query-result equivalence could even be assessed. The
run also timed out while creating the optional research brief, but the deterministic fallback brief
allowed the remaining workflow to complete.

## Private executed-query provenance

M3.11 records an in-memory mapping from every analytical SQL Evidence ID to the exact read-only
query that produced it. After Claim validation, the backend selects a query in this order:

1. the executed query associated with Evidence used by an accepted Claim;
2. otherwise, the latest executed query that produced analytical Evidence.

The mapping is runtime-only. Query text is not added to the portable trace, metric output, or
Hybrid result JSON.

## Explicit output contract

When `INCLUDE_EXECUTED_SQL_IN_REPORT=1` is set, the backend appends exactly one
`Executed analytical SQL` fence to the completed report. Existing model-generated SQL fences are
removed first, preventing an invented or stale query from being scored instead of the query that
actually produced Evidence. Without the explicit flag, normal reports are unchanged.

The Hybrid runner enables this contract for its Search-to-SQL tasks. This is not a correctness
shortcut: the evaluator still executes the attached query against the pinned read-only SQLite
database and compares both columns and canonical rows with the frozen reference query.

## Trace schema v8

Trace schema v8 adds the boolean `report_sql_query_attached`. Hybrid smoke output exposes the same
state as `executed_sql_attached` per task and as a run-level count. The selected query itself remains
private unless the explicit final-output contract requests it.

## Verification boundary

Deterministic tests verify that:

- Evidence Tool execution registers successful SQL provenance;
- accepted-Claim Evidence is preferred over an unrelated later query;
- an existing model-generated SQL fence is replaced by exactly one executed query;
- SQL text remains absent from serialized trace data;
- schema-v8 metrics remain compatible with the Hybrid adapter;
- the complete existing suite continues to pass.

No further live search is used after implementation. The next single-task validation should first
confirm that the evaluator receives an executable SQL block. If result equivalence still fails, the
remaining issue is query semantics rather than orchestration or output formatting.
