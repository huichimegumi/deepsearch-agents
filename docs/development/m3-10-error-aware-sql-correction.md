# M3.10 Error-aware SQL correction repair

## Live validation finding

The first post-M3.9 `s2sql_041` run verified that the reserved correction path is reachable. The
single-task run used exactly two Tavily queries and one fetched page, completed in about 66 seconds,
and collected one Web Evidence record plus eleven SQL schema records. Structured SQL correction
started once and returned a proposal in about four seconds.

The proposal nevertheless failed with the bounded `unknown_column` category. Audit data showed
that it treated a requested derived metric as a physical database column even though that column
was absent from the supplied schema. The run therefore recorded one correction attempt, zero
correction successes, and no analytical SQL Evidence. The M3.9 admission override was not needed
in this particular run because the Supervisor had not exhausted the consecutive-error limit.

This closes the scheduling question: the remaining failure is proposal quality after a concrete
database error, not correction admission, timeout, or additional Web retrieval.

## One error-only repair

M3.10 permits one second structured proposal only when the first correction query returns an
`ERROR` Evidence batch. The repair call receives the rejected proposal and the same bounded
Evidence Ledger, and is instructed to re-check every identifier and express derived metrics with
SQL expressions rather than invented columns.

The backend enforces the following boundaries:

- at most two structured proposals and two SQL executions in the correction phase;
- the second normalized query must differ from the first;
- `NO_EVIDENCE`, `OK`, and `PARTIAL` results do not trigger a repair;
- both model calls and both Evidence Tool calls share the original correction deadline;
- each query still passes duplicate-failure, read-only, single-statement, database-timeout, and
  bounded-result enforcement;
- compression and writer LLM-call reserves remain intact;
- no Web search, fetched page, subagent, or research round is added.

The repair does not receive raw database error text. The trigger is the structured batch status,
and the model must diagnose its own rejected query against the schema already in context.

## Trace schema v7

Trace schema v7 adds `sql_correction_repair_attempts` and
`sql_correction_repair_successes`. The original `sql_correction_attempts` counter continues to
count correction phases, not individual proposals. Hybrid smoke output exposes both new metrics
per task and as aggregate totals. SQL text remains absent from the portable trace.

## Verification boundary

Deterministic tests cover:

- an unknown-column first proposal followed by a different successful derived query;
- production of claim-eligible analytical SQL Evidence after repair;
- no repair after a valid query returns no rows;
- preservation of zero Web-query, page, and research-round consumption;
- schema-v7 trace serialization and Hybrid metric extraction;
- the complete existing test suite.

No additional live search is used after implementing the repair. The next validation should reuse
the same one-task, two-query Tavily cap and require either analytical SQL Evidence or a precisely
classified remaining failure before considering the three-task smoke subset.
