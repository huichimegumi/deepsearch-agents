# M3.23 Web Evidence kind contract and entity-rejection diagnostics

## Motivation

The first live validation after M3.22 used the explicitly authorized one-task Tavily 6/6 ceiling.
It consumed six queries and five fetched pages, collected five Web Evidence records, three grounded
semantic records, and five validated Claims with valid delivered citations. SQL correction still
stopped before a query, reporting `sql_entity_resolution_context_missing`.

The trace proved that both source families existed, so this was not a retrieval failure. The Web
adapter created stable `ev1_web_...` records but did not assign `evidence_kind=web_page`. M3.22 used
that kind to build its bounded entity ledger, causing all real Web records to be filtered out. Its
offline fixtures had supplied the missing metadata manually and therefore failed to expose the
cross-module contract mismatch.

## Canonical Web Evidence typing

Fetched public pages now receive `evidence_kind=web_page` at the adapter boundary. Evidence IDs do
not change because metadata is intentionally excluded from the content-addressed identity payload.
Search snippets and provider-generated answers remain candidate-only and do not receive Evidence
records.

The runtime also canonicalizes an absent kind to `web_page` when—and only when—the record source is
`web`. This keeps previously constructed or externally supplied schema-v1 Web records usable while
preserving explicit kinds and the existing SQL defaults. The same canonical function is used for:

- trace Evidence classification;
- exact Web Evidence ID admission;
- kind-filtered Evidence Ledger rendering.

The M3.22 integration test now creates its Web record through the production
`web_results_to_evidence` adapter instead of a hand-built object. A separate runtime test covers a
legacy Web record with no explicit kind.

## Bounded rejection diagnostics

The post-fix live validation again used one task and the authorized 6/6 ceiling. It consumed six
queries and six pages, collected six Web Evidence records and three semantic records, produced four
validated Claims with valid citations, and changed the entity failure from `context_missing` to
`unverified`. This confirms that real Web Evidence reached the structured resolver. The run still
failed closed before SQL and produced no query failures or guessed fields.

A single `unverified` label cannot distinguish safe but operationally different rejection paths.
M3.23 therefore classifies proposals into content-free categories:

- invalid structured output;
- unsupported or insufficient clues;
- missing entity or candidate;
- conflicting candidates;
- missing or unknown Web Evidence IDs;
- unknown semantic table or column.

Only the category is written to failure telemetry. Clue text, candidate names, Evidence content,
prompts, SQL, and database values remain absent. Database zero/multiple-match failures continue to
use the separate `sql_entity_value_not_unique` category.

## Verification

Focused tests cover production-adapter metadata, stable Web IDs, production-adapter use in the full
entity-to-SQL success path, fabricated Web ID rejection, legacy-record normalization, and
content-free candidate-conflict classification. The complete suite passes with **176 passed and 6
skipped**.

The two live runs consumed 12 Tavily queries in total, with no run exceeding the configured six-
query/six-page ceiling. No third paid run was started. Generated questions, answers, SQL, model
output, and evaluation logs remain ignored and uncommitted.

## Remaining boundary

The next single-task validation should use the new bounded rejection category to determine whether
the limiting factor is incomplete clue support, candidate convergence, Evidence ID selection, or
semantic field selection. The gate should not be relaxed until that category is observed. AST-level
formula-equivalence enforcement remains downstream because no analytical SQL proposal was admitted
in either M3.23 diagnostic run.
