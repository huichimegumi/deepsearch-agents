# M3.32 Bounded iterative entity recovery

## Live boundary after M3.31

The fixed post-M3.31 `s2sql_041` validation used Tavily with the 6/6 task ceiling. It consumed only
two queries and two fetched pages, produced fourteen SQL Evidence records and two Web Evidence
records, completed two entity-resolution attempts, passed cross-source and citation validation,
and finished all workflow phases in about 46 seconds. SQL correction itself completed in about 14
seconds. This confirms that the M3.31 timeout change lets the recovery result reach the second
structured resolver without an upstream or phase timeout.

The run still degraded at `sql_entity_resolution_clues_unsupported`. It produced no grounded entity
value match and therefore correctly skipped analytical SQL. Four query slots and four page slots
remained unused. The remaining bottleneck is no longer phase time: the backend allowed exactly one
recovery search and stopped after the second resolver even though the Supervisor had left enough
global retrieval capacity for another targeted pass.

## Iterative recovery with layered caps

M3.32 permits one additional entity-recovery round when the second resolver still reports
`clues_unsupported` and supplies non-empty targeted recovery queries. The sequence is now bounded as
follows:

```text
resolver 1
  -> recovery 1 from the reserved allowance (at most 2 queries / 2 pages)
resolver 2
  -> recovery 2 from unused global capacity (at most 2 queries / 2 pages)
resolver 3
  -> accept a fully grounded entity or fail closed
```

The second recovery round does not create a new budget. It reads the remaining query and page
capacity from the same run-level ledger after the initial reserve has been released and consumed.
If ordinary Supervisor research plus the first recovery already reaches the task ceiling, the
second round receives zero capacity and no search occurs. If capacity remains, the per-round caps
restrict the additional work even when the global remainder is larger.

Every retry still requires all of the following:

- the current resolver rejection is exactly `clues_unsupported`;
- the resolver returns one or more specific recovery queries;
- both query and fetched-page capacity are available;
- the search creates at least one new current-run Web Evidence ID;
- the SQL-correction phase deadline and LLM-call budget remain open.

The final resolver cannot trigger a third search. Complete-clue support, known current-run Evidence
IDs, candidate agreement, semantic catalog selection, unique database-value matching, analytical
SQL admission, and citation validation remain unchanged.

## Budget API and verification

`ResearchBudget.available_search_queries` now exposes the same reserve-aware admission view already
used for fetched pages. `take_search_queries` delegates to that property, so inspection and
consumption cannot drift into different calculations.

Tests cover reserve visibility before and after release and a complete three-resolver path in which
the first search uses its reserved capacity, the second search reclaims otherwise-unused global
capacity, and the grounded database value succeeds only after both new Evidence records are present.

Validation for this stage:

- focused runtime and entity-recovery tests: 46 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 189 passed, 6 skipped.

No post-fix Tavily run is performed in M3.32. The next fixed validation can determine whether the
second targeted recovery closes the remaining clue gap while remaining inside the unchanged 6/6
evaluation ceiling.
