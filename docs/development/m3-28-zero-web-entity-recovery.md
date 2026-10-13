# M3.28 Zero-Web entity recovery bootstrap

## Live boundary after M3.27

The first post-M3.27 validation reused the fixed `s2sql_041` task and the authorized Tavily 6/6
ceiling. SQLite and semantic-sidecar preflight passed, but the Supervisor did not dispatch the
network researcher. The run therefore consumed zero Tavily queries and zero fetched pages, retained
fourteen SQL Evidence records including three semantic records, and reached SQL correction in about
28 seconds.

Entity resolution then stopped at `sql_entity_resolution_context_missing`. The backend required at
least one existing Web Evidence record before invoking the structured resolver, so the M3.27
`recovery_queries` field and reserved 2/2 retrieval capacity could not bootstrap a run whose
Supervisor produced no Web evidence. No analytical SQL ran. With no claim-eligible evidence, two
claim drafts were rejected and deterministic final-report citation validation also failed; that is
a downstream consequence rather than the recovery root cause.

## Bootstrap behavior

M3.28 separates the two kinds of missing context:

- a missing grounded semantic table/column catalog still fails immediately with
  `sql_entity_resolution_context_missing`;
- an empty Web Evidence Ledger now reaches the first structured resolution attempt with an explicit
  message that no fetched Web evidence exists.

The empty-ledger instruction requires `all_clues_supported=false`, prohibits entity inference, and
asks for at most two specific recovery queries. The M3.27 reserve can then fetch full pages. A second
resolution attempt is still admitted only when the recovery search registers a new current-run Web
Evidence ID.

This change does not create an evidence-free success path. The existing classifier still rejects a
proposal with unsupported clues, missing Evidence IDs, invented Evidence IDs, conflicting
candidates, unknown table/column names, or a non-unique database value. SQL remains unreachable
until every clue is bound to fetched Web Evidence and the resolved entity uniquely matches the
database.

## Verification

The entity-recovery integration test now runs in two modes: one starts with partial Web Evidence,
and one starts with no Web Evidence. Both must use the reserved search, register a newly fetched
record, perform exactly two resolution attempts, and pass the same SQLite unique-value gate. The
focused runtime and correction set reports 43 passed, and Ruff passes for the changed Python files.
The full repository suite reports 185 passed and 6 skipped.

No post-fix Tavily run is performed in M3.28. The next fixed 6/6 validation should verify that a
zero-Web Supervisor result leads to backend recovery instead of `context_missing`, while a normal
partial-evidence result continues to use the same bounded path.
