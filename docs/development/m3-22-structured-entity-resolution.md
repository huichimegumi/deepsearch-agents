# M3.22 Structured cross-source entity resolution

## Motivation

M3.19 added a deterministic database value matcher, but invoking it still depended on the research
model. A model could therefore select a place mentioned by one clue, omit the other clues, or write
an unverified Web citation and continue to SQL correction. M3.21 made formulas executable and SQL
proposals preflightable, but neither safeguard proves that the filtered database entity is the
intersection of the task's Web clues.

M3.22 adds a fail-closed backend gate for tasks that explicitly contain `clue`, `clues`, or `线索`.
Before correction can propose analytical SQL, the gate requires a structured entity resolution and
a unique match against a physical database field.

## Structured resolution contract

The resolver receives only two bounded contexts:

- fetched `web_page` Evidence from the in-memory Evidence Ledger, including its stable
  `ev1_web_...` IDs;
- table and column names from grounded `database_semantics.relevant_table_columns`.

It returns one `EntityResolutionProposal` containing the resolved entity, at least two clue
assessments, the supporting Web Evidence IDs for every clue, and one catalogued table/column target.
The schema permits an explicit unresolved response with empty candidates and IDs. This prevents the
structured-output layer from forcing the model to invent an answer merely to satisfy minimum-length
constraints.

The backend accepts a proposal only when all of the following are true:

1. `all_clues_supported` is true and at least two clue assessments are present;
2. every clue is marked supported and names the same normalized entity;
3. every cited ID exists in the current trace and belongs to fetched Web Evidence;
4. the selected table and column exist in the grounded semantic catalog;
5. `match_column_value` returns exactly one `database_value_match` record.

Any missing context, unsupported clue, unknown ID, candidate disagreement, invented table/column,
zero database matches, or ambiguous database matches stops SQL correction. The gate never falls back
to a Web name as a database key and does not reuse an unrelated earlier value match.

## Workflow and telemetry

The gate runs after deterministic semantic prefetch and before `SQLCorrectionProposal`. A successful
flow is therefore:

1. prefetch pinned semantic Evidence;
2. resolve all clues with exact Web Evidence IDs;
3. bind the resolved entity to one physical database value;
4. propose SQL using the value-match Evidence and compiled formula;
5. preflight and execute the analytical query.

The entity resolver uses one existing SQL-correction LLM call. It does not add Web searches, fetched
pages, research rounds, or SQL proposal/repair slots. Trace schema v12 and Hybrid smoke aggregation
add these counters:

- `sql_entity_resolution_attempts`;
- `sql_entity_resolution_successes`;
- `sql_entity_value_match_successes`.

Trace output still excludes clue text, candidate text, prompts, SQL, database rows, and Evidence
content. Failure reasons expose only bounded categories such as
`sql_entity_resolution_unverified` and `sql_entity_value_not_unique`.

## Verification

Offline integration coverage creates a temporary SQLite database and pinned formula sidecar, records
fetched Web Evidence, resolves two clues to one entity, obtains a unique database value, preflights
the derived-metric query, and executes it successfully. A negative test supplies a fabricated Web
Evidence ID and verifies that the gate rejects it before any database matching tool call. Runtime
coverage verifies the grounded table/column catalog and schema-v12 counters.

The full test suite passes with **175 passed and 6 skipped**. No Tavily request was used in this
stage.

## Remaining boundary

The gate is deliberately activated only by explicit clue wording so ordinary SQL tasks do not pay an
extra model call or become dependent on Web Evidence. A later stage can replace this conservative
lexical trigger with task classification after live validation. M3.22 also verifies identity and
database uniqueness, not whether a valid SQL expression is algebraically equivalent to the compiled
formula; AST-level formula equivalence remains a separate hardening opportunity.
