# M3.8 Structured SQL correction execution

## Live validation findings

M3.8 began with two executions of the single `s2sql_041` Search-to-SQL task. Both retained the
existing cap of two search queries, two fetched pages, and one research round.

The first run authorized Tavily but made no network request. Supervisor research collected one
schema and three bounded samples, then stopped without analytical SQL. The M3.7 correction ran in
2.6 seconds but returned ordinary model text instead of the required tool call. The run recorded:

- zero Tavily queries and zero fetched pages;
- zero analytical SQL attempts;
- one correction attempt and zero correction successes;
- `sql_correction_requires_one_tool_call` as the first degradation reason.

The initial M3.8 change replaced that model-selected tool call with structured output. A second
live run then exercised the complete hybrid route:

- exactly two Tavily queries and one fetched page;
- one Web Evidence record and eleven SQL schema records;
- two Supervisor SQL attempts: one unknown-column error and one valid query with no rows;
- cross-source Evidence and final citation validation both succeeded;
- the structured correction reached its 45-second timeout before returning a proposal.

The second result proves that paid-search authorization and accounting work as intended, while
also showing that SQL completion—not additional retrieval—is still the limiting step. No further
live search was run during this stage.

## Deterministic proposal and execution

The correction model now returns one `SQLCorrectionProposal` containing only a non-empty `query`.
It is not given a menu of tools and cannot select a source or operation. Backend code maps the
proposal to fixed arguments:

```text
source=sql
operation=query
query=<validated structured proposal>
```

The unified Evidence Tool remains the enforcement boundary for read-only SQL, statement count,
query deadlines, duplicate failed queries, and the bounded repair policy. Query text is not added
to trace telemetry.

## Focused correction context

Correction uses a dedicated short system instruction instead of the general research-agent
instruction. Its bounded Evidence Ledger orders Web Evidence before SQL Evidence so a resolved
public entity is not displaced by the database catalog. The content allowance is 32,000
characters: enough for the frozen `alien` schema, whose eleven schema records contain roughly
24,000 characters, plus a small number of bounded Web or sample records.

The correction allocation is raised from 15% to 20% of the run budget. Under the Hybrid
`deep_report` profile this is at most 60 seconds. Compression and writer call reserves remain in
force, the correction still consumes no research round, and external query/page limits are
unchanged.

## Verification boundary

Deterministic tests verify that:

- structured output is requested with `SQLCorrectionProposal`;
- the backend always constructs `source=sql, operation=query` arguments;
- a real temporary SQLite query produces claim-eligible analytical Evidence;
- the correction uses no search query, fetched page, or research round;
- Web Evidence can be prioritized ahead of schema records in the bounded ledger;
- the 60-second allocation follows from the run-level budget without reducing writer reserves.

The live outcome after the final context and timeout adjustment has intentionally not been rerun in
this stage, avoiding another paid search. The next validation should reuse the same one-task cap and
measure whether a structured proposal completes within 60 seconds before considering any broader
subset run.
