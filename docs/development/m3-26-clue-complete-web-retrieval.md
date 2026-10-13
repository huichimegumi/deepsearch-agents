# M3.26 Clue-complete Web retrieval contract

## Why this stage exists

The first live validation after M3.25 used the explicitly authorized one-task Tavily ceiling of six
queries and six fetched pages. The SQLite preflight passed, proving that the Windows path fix works
against the locked `alien` database and both semantic sidecars before paid retrieval begins.

The run used four queries and fetched four pages. It produced fourteen SQL Evidence records,
including three semantic records, plus four Web Evidence records. Citation validation and the
cross-source Evidence check both passed. Entity resolution then failed closed with
`sql_entity_resolution_clues_unsupported`: one resolution attempt was made, but no unique database
value or analytical SQL was allowed. This is the intended M3.22 safety behavior. The new bottleneck
is incomplete Web coverage, not SQLite access, routing, timeout, or the SQL gate.

## Retrieval contract

M3.26 keeps the entity gate unchanged and strengthens the bounded network-research contract:

- preserve each clue's proper nouns and most discriminating literal phrases;
- issue one independent query for every uncovered clue before attempting an intersection query;
- prioritize uncovered clues when the remaining query budget is smaller than the desired plan;
- reject broad country, ethnicity, or regional-background searches as substitutes for concrete
  person, building, work, or event clues;
- return a `Clue Coverage` row for every clue with its query, candidate, fetched Web Evidence IDs,
  and `covered` state;
- declare a shared entity verified only when every clue has at least one fetched `ev1_web_...`
  record; provider summaries and `CANDIDATE_ONLY` results do not count.

The Supervisor contract repeats these requirements at the delegation boundary so they are present
both when the subtask is written and when the network researcher executes it. Existing run-level
query and page caps remain the hard limit; this stage does not add retries or bypass budget
accounting.

## Validation policy

Prompt-contract tests assert the per-clue query order, uncovered-clue priority, explicit coverage
table, and prohibition on replacing concrete clues with broad background. The full automated suite
is run after the change.

No second Tavily run is used in this stage. The next single-task validation should reuse the 6/6
ceiling and determine whether the new contract produces complete clue coverage. A successful run
should advance to a unique `database_value_match` and analytical SQL; a remaining content-free
entity rejection category should define the next fix without weakening the gate.
