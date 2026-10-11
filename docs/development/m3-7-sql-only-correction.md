# M3.7 SQL-only analytical Evidence correction

## Why this stage exists

The post-M3.5 `s2sql_041` run successfully collected SQLite schema Evidence, three bounded table
samples, and two fetched Web pages, but the Supervisor stopped without executing an analytical SQL
query. M3.6 correctly prevented discovery records from supporting final Claims, but a hard failure
alone did not help the workflow complete the missing database step.

M3.7 adds one narrowly scoped correction between Supervisor research and the analytical-SQL gate.
Its purpose is to turn already collected database discovery material into one `query_result`, not
to reopen research or increase retrieval.

## Deterministic admission gate

The correction is attempted only when all of the following are true:

1. `REQUIRE_ANALYTICAL_SQL_EVIDENCE=1` is set by the calling workflow.
2. At least one real `database_schema` or `database_sample` Evidence record is registered.
3. No claim-eligible SQL `query_result` has been registered.
4. The two-consecutive-failure SQL repair limit has not been exhausted.
5. No correction has already been attempted in the run.
6. Run-level time and LLM-call budgets still admit the phase.

An unsuccessful schema call does not satisfy the gate. This matters because the model must not be
asked to invent a query when the database structure was never actually observed.

## Capability boundary

The correction is one direct model call, not another DeepAgent research loop. The model receives
the original question, completed research brief, and the bounded backend Evidence Ledger. Only the
unified `collect_evidence` tool is bound. Before invoking the tool, the backend verifies:

- exactly one tool call was returned;
- the tool name is `collect_evidence`;
- `source=sql`;
- `operation=query`;
- a non-empty query is present.

Any request for Web search, a researcher subagent, local documents, Fee Engine, `describe_schema`,
`sample_table`, or `list_tables` is rejected before tool execution. The existing Evidence Tool
still enforces read-only SQL, query deadlines, duplicate-failure rejection, and the one-repair
limit.

## Budget behavior

The phase receives at most 15% of the run-level time budget and preserves the compression and
writer LLM-call reserve. It does not consume a research round and has no access to the network
search tool. Therefore M3.7 does not change the Hybrid smoke limits of two search queries and two
fetched pages per task, and it cannot consume Tavily credits.

## Trace and evaluation

Trace schema v5 adds:

- `sql_correction_attempts`;
- `sql_correction_successes`;
- a separate `sql_evidence_correction` phase entry.

Hybrid smoke results expose both counters per task and as aggregate totals. The trace continues to
store only bounded counters and Evidence identities; SQL text, database error text, and Evidence
content are not copied into telemetry.

## Verification

Deterministic tests cover:

- successful correction against a real temporary read-only SQLite database;
- production of claim-eligible `query_result` Evidence;
- zero search-query, fetched-page, and research-round consumption;
- rejection of non-SQL Evidence arguments before tool execution;
- the one-attempt trace counter and schema-v5 serialization;
- preservation of the existing four-stage workflow order.

No live Web run was performed for M3.7. The stage changes only the local SQL completion path, so
the validation deliberately avoids additional DuckDuckGo traffic and uses zero Tavily credits.
