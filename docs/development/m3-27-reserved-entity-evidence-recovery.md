# M3.27 Reserved entity-evidence recovery

## Live boundary after M3.26

The post-M3.26 validation reused the fixed `s2sql_041` task and the explicitly authorized Tavily
ceiling of six queries and six fetched pages. Paid-search preflight passed. The run consumed the full
6/6 allowance through four network-subagent dispatches and finished in about 164 seconds without an
upstream timeout.

The workflow retained fourteen SQL Evidence records, including three semantic records, and six Web
Evidence records. It validated four Claims, passed citation validation, and passed the cross-source
Evidence check. The structured entity gate still returned
`sql_entity_resolution_clues_unsupported`; consequently no database value match or analytical SQL
was admitted. M3.26 improved retrieval behavior, but a prompt contract alone could not guarantee
that the final queries targeted the exact unsupported clues.

## Backend-owned recovery budget

M3.27 reserves the final two search-query slots and two fetched-page slots for multi-clue entity
tasks. The ordinary Supervisor and network researcher cannot consume either reserve through normal
`research_search` calls. All recovery work continues to count against the original run-level hard
caps.

The first structured `EntityResolutionProposal` can now return at most two `recovery_queries` when
one or more clues lack fetched-page support. The resolver prompt requires these queries to preserve
the unsupported clue's discriminating names or literal phrases and forbids generic background
requests.

Recovery is admitted only when all of the following are true:

- the first rejection category is exactly `clues_unsupported`;
- the structured proposal supplies at least one non-empty recovery query;
- a reserved search allowance remains;
- the correction phase still has time;
- the recovery fetch creates at least one new Web Evidence ID.

The backend then performs one direct, bounded `research_search` call with full-page fetching and
reruns structured entity resolution once against the updated Evidence Ledger. Other rejection
categories do not trigger search. No new Evidence means no retry. The existing checks for complete
clue agreement, real current-run Web Evidence IDs, catalog-bound table/column names, and one unique
database value remain unchanged.

## Verification

Automated coverage proves that query and page reserves are hidden from ordinary search, become
available only after explicit release, and never permit total use to exceed the original limits. The
end-to-end resolver test starts with one unsupported clue, returns one recovery query, registers a
new fetched Web Evidence record, reruns resolution, uniquely matches the SQLite value, and records
two resolution attempts without bypassing any gate.

Validation for this stage:

- focused runtime and correction tests: 41 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 184 passed, 6 skipped.

No post-fix Tavily run is performed in M3.27. The next one-task 6/6 validation should show at most
four ordinary queries/pages plus at most two backend-directed recovery queries/pages. Its final
content-free entity category—or a successful value match and analytical query—will define the next
stage.
