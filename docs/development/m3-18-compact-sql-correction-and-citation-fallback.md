# M3.18 Compact SQL correction and validated citation fallback

## Post-M3.17 live validation

The first post-M3.17 single-task run used an explicitly authorized Tavily 6/6 limit and consumed six
queries plus five fetched pages. It completed with five Web Evidence records, six accepted Claims,
zero rejected Claims, and zero unknown Claim Evidence IDs. This confirms that the M3.16 Claim-safe
handoff and M3.17 physical-column grounding work across the live workflow.

Three SQL queries executed without database errors but returned no rows, so no analytical SQL
Evidence was produced. The SQL-only correction then spent its full 60-second budget waiting for the
structured model response and did not execute a correction query. The final Writer cited Claim IDs
rather than their Evidence IDs; the backend correctly withheld that Writer output, but trace citation
validity remained false even though the returned validated Claim package contained valid Evidence
citations.

Inspection exposed two avoidable context costs:

1. the task used the full metric name without its parenthesized acronym, so exact-name detection fell
   back to lexical mode and returned eight semantic records instead of the parent and two children;
2. SQL correction replayed the large full-database schema even though semantic Evidence already
   contained formulas, dependencies, physical mappings, and relevant table columns.

No decrypted task, gold answer, reference SQL, model output, or local evaluation log is committed.

## Metric-name aliases

Semantic exact matching now treats a trailing parenthesized acronym as an optional alias. A query
containing the full base name is an exact match even when it omits the acronym. Dependency expansion
therefore returns only the requested root and its required children before considering lexical
candidates.

A no-network check against the locked assets returned exactly three records for the base metric
name: the parent formula and its two dependencies.

## Compact SQL-correction context

When semantic formula Evidence exists, SQL correction no longer renders the full schema ledger. It
receives two bounded sections instead:

- up to eight semantic formula records, including dependency definitions, `resolved_columns`, and
  `relevant_table_columns`;
- up to 24 Claim-eligible records, Web-first, for entity resolution and filter construction.

Each section has a 16,000-character cap. Discovery-only schema records are omitted because the
semantic bundle already contains the required physical tables and columns. Tasks without semantic
formula Evidence retain the prior 32,000-character full-ledger fallback.

This change keeps the existing 60-second correction deadline, SQL read-only policy, proposal count,
and external retrieval budgets unchanged while reducing duplicated prompt content.

## Citation-safe fallback validation

If the Writer output fails citation validation, the backend still marks the run degraded and records
`final_report_citation_validation_failed`. It now validates the exact fallback report that will be
returned to the caller. When the validated Claim package contains only permitted Evidence IDs, trace
`report_citation_valid` becomes true because the delivered content is citation-safe. If the fallback
is also invalid, the failure remains visible as before.

This distinguishes model-format failure from delivered-report integrity: the run can be degraded
while the actual response still has a valid citation chain.

## Verification boundary

Tests cover base-name matching without an acronym, exact dependency closure, compact correction
context, schema exclusion, preservation of Web entity Evidence, and successful revalidation of a
backend-generated Claim fallback. Existing correction, Claim, Evidence, and budget behavior remains
covered by the full suite.

A later live run should verify whether the smaller correction prompt completes inside 60 seconds and
whether relaxed entity filtering converts the current valid-empty SQL into analytical Evidence.
