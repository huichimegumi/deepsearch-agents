# M3.12 Empty-result SQL correction repair

## Live validation finding

The first post-M3.11 `s2sql_041` validation used exactly two Tavily queries and two fetched pages,
completed in about 65 seconds, collected both Web and SQL Evidence, and passed citation validation.
The run still failed the strict check because it produced no analytical SQL Evidence, so there was
no executed query available for the M3.11 output contract to attach.

Audit data showed a different failure from M3.10. The correction query was valid and executed
without a database error, but an over-constrained location filter returned zero rows. The Evidence
Tool therefore returned `NO_EVIDENCE`; the error-only repair policy stopped immediately with one
correction attempt, zero repair attempts, and zero correction successes. More Web retrieval would
not address this SQL filtering failure.

## One bounded empty-result repair

M3.12 permits the existing second structured proposal when the first correction query returns
either `ERROR` or `NO_EVIDENCE`. The two cases receive different instructions:

- an error repair re-checks identifiers and derived expressions against the supplied schema;
- an empty-result repair preserves the requested entity and computation while relaxing only
  filters unsupported by the existing Evidence Ledger.

The empty-result path does not ask the model to invent a replacement value. It must use exact
schema identifiers, submit a different normalized query, and execute through the same unified
Evidence Tool.

All existing boundaries remain in force:

- at most two structured proposals and two SQL executions in the correction phase;
- both proposals and executions share the original 60-second correction deadline;
- a second empty result stops the phase instead of triggering a third proposal;
- duplicate failed or duplicate correction proposals remain blocked;
- every query remains read-only, single-statement, time-bounded, and result-bounded;
- no Web search, fetched page, subagent, or research round is added;
- compression and final-writer reserves are unchanged.

## Trace schema v9

Trace schema v9 retains the aggregate `sql_correction_repair_attempts` and
`sql_correction_repair_successes` counters and adds two diagnostic metrics:

- `sql_correction_empty_result_repair_attempts`;
- `sql_correction_empty_result_repair_successes`.

The Hybrid runner exposes both metrics per task and as aggregate totals. SQL text remains absent
from the portable trace and evaluation result JSON.

## Verification boundary

Deterministic tests cover:

- a valid but empty first query followed by a relaxed query that produces analytical Evidence;
- a second empty query stopping after exactly two proposals;
- distinct prompts and telemetry for database-error and empty-result repair;
- continued rejection of duplicate repair proposals;
- zero additional Web queries, fetched pages, and research rounds;
- schema-v9 serialization and Hybrid metric extraction;
- the complete existing test suite.

No additional live search is used after implementation. The next validation should rerun one task
with the same two-query/two-page Tavily cap and determine whether the repaired analytical query is
both attached to the report and equivalent to the frozen reference result.
