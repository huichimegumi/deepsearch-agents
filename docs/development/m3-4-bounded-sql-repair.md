# M3.4 Bounded SQL repair and telemetry

M3.3 gives the model the schema needed to construct valid SQLite queries. M3.4 prevents a failed
query from turning into an unbounded guessing loop.

The policy is enforced at the unified Evidence Tool boundary whenever a research trace is active:

1. The first SQL query is admitted.
2. If it fails, the exact failed query cannot be submitted again.
3. One different repair query is admitted.
4. If that query also fails, further SQL queries are rejected without reaching the database.
5. A successful query resets the consecutive-failure counter, so a later independent query can
   still use the same original-plus-one-repair policy.

The limit applies only to `operation=query`. Schema discovery and exact-table sampling remain
available and have their own counters. Rejected calls return structured `ERROR` batches instructing
the researcher to stop querying and report the evidence gap.

## Trace schema v4

Trace schema v4 adds:

- admitted SQL query attempts, successes, failures, and blocked calls;
- schema-discovery and sample-table call counts;
- bounded error categories such as `unknown_column`, `unknown_table`, `ambiguous_column`,
  `syntax_error`, `unsafe_query`, and `timeout`;
- blocked SQL calls in the waste section.

The trace stores only a truncated SHA-256 digest for each query and a bounded error category. It
does not serialize SQL text or database error text. Audit events retain the existing operational
warning plus the policy decision so local debugging remains possible without placing query text in
the portable research trace.

The HybridDeepResearch result summary now surfaces SQL attempts, failures, blocked calls, and
schema-discovery calls. This lets the next frozen-subset run distinguish "the model never inspected
the schema" from "the schema was inspected but query construction still failed."

