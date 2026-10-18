# M3.33 Full-budget entity recovery

## Live boundary after M3.32

The fixed post-M3.32 `s2sql_041` validation used Tavily under the unchanged 6/6 task ceiling. It
confirmed the complete M3.32 path: two recovery searches ran, four queries and four fetched pages
were consumed, and three structured entity resolvers received the accumulating Web Evidence. The
run produced fourteen SQL Evidence records, four Web Evidence records, and six validated Claims;
cross-source and citation validation passed.

SQL correction completed normally in about 26 seconds, and the complete workflow finished in about
63 seconds with nine LLM calls. There was no upstream or phase timeout. The third resolver still
failed closed at `sql_entity_resolution_clues_unsupported`, so no database value was accepted and no
analytical SQL was executed. Two authorized query slots and two authorized page slots remained
unused solely because M3.32 capped recovery at two rounds.

## Consume the authorized ceiling, not more

M3.33 raises the backend recovery boundary to three rounds and derives the resolver limit as one
more than that recovery limit:

```text
maximum recovery searches: 3
maximum resolver attempts: 4
maximum work per recovery: 2 queries / 2 fetched pages
maximum recovery retrieval under the fixed evaluation override: 6 / 6
```

The first recovery still uses the explicit reserve. Later recoveries still draw only from unused
capacity in the same run-level ledger. This means the expanded loop can reach 6/6 only when ordinary
Supervisor research leaves enough capacity. If the Supervisor already spent four queries and four
pages, the reserved first recovery reaches 6/6 and subsequent rounds are denied automatically.

The additional round retains every M3.32 continuation gate. A retry requires a
`clues_unsupported` result, non-empty targeted recovery queries, remaining query and page capacity,
new current-run Web Evidence, phase time, and LLM-call budget. The fourth and final resolver cannot
start another search. Complete-clue support, known Evidence IDs, candidate agreement, semantic
catalog binding, unique database-value matching, analytical SQL admission, and citation validation
are unchanged.

## Verification

The iterative integration test now exercises the complete ceiling. Three recovery searches each
consume two queries and two fetched pages, the Evidence Ledger accumulates six stable Web Evidence
records, and the fourth resolver can ground a unique database value only after all three searches.
The assertions verify exactly six query debits, six page debits, four resolver attempts, three
search tool calls, and one successful database-value lookup.

Validation for this stage:

- focused entity-recovery and runtime tests: 46 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 189 passed, 6 skipped.

No post-fix Tavily run is performed in M3.33. The next fixed validation can determine whether using
the final authorized 2/2 allowance closes the clue gap and reaches analytical SQL.
