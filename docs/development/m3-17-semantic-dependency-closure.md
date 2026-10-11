# M3.17 Semantic dependency closure and physical-column grounding

## Post-M3.16 live validation

The first post-M3.16 single-task run authorized Tavily with a 6/6 limit, but the model issued no Web
search, so no Tavily credits were consumed. The run completed in about 30 seconds.

Both deterministic semantic-prefetch paths executed, proving the M3.16 scheduling change works.
Eight semantic Evidence records were available, the full schema contained 136 semantic column
descriptions, and Compression no longer submitted discovery IDs as Claims: unknown Claim Evidence
fell from five IDs in the prior run to zero.

The run still had no analytical SQL Evidence. The two correction queries failed, first with an
unknown derived-metric column and then with invalid SQL syntax. Inspection of the pinned semantic
sidecar showed why: the requested top-level formula references two child formulas through
`children_knowledge`, but `search_semantic_knowledge` returned only the parent plus seven unrelated
lexical matches. The parent formula alone did not expose the physical inputs needed to construct the
calculation.

No decrypted task, gold answer, reference SQL, model output, or local evaluation log is committed.

## Dependency-aware semantic retrieval

`search_semantic_knowledge` now distinguishes an exact metric-name match from ordinary token
overlap. When an exact match exists, it uses the exact records as roots and expands their
`children_knowledge` graph breadth-first within the existing eight-record cap. Unrelated lexical
matches no longer consume the remaining slots ahead of required formula dependencies.

When there is no exact name match, lexical ranking remains the fallback and each selected record's
dependencies are still expanded before lower-ranked candidates. Duplicate or missing child IDs are
handled deterministically, and cyclic references cannot duplicate records because selected upstream
IDs are tracked.

## Physical-column grounding

For every selected formula, the SQLite adapter extracts formula identifiers and matches them
case-insensitively against the live read-only database catalog. The semantic Evidence content adds:

- `resolved_columns`: formula identifier, physical table, and physical column triples;
- `relevant_table_columns`: complete physical column lists for every matched table.

The database fingerprint and content-addressed Evidence ID make this enrichment stable for an
unchanged database and sidecar while changing the ID when the grounded content changes. It remains
discovery-only and cannot pass the Claim gate.

The Supervisor and SQL-correction instructions now explicitly require dependency expansion and the
resolved physical mappings. Metric display names must never be treated as database columns.

## Verification boundary

Tests verify exact-root dependency expansion, exclusion of unrelated lexical records, physical
column grounding, relevant-table summaries, stable repeated Evidence IDs, and compatibility with
the existing semantic-prefetch and SQL-repair behavior.

A no-network check against the hash-locked `alien` assets returned exactly the requested parent and
its two dependencies. All formula inputs were grounded to physical columns in the two relevant
tables. A later live run should test whether this self-contained semantic bundle produces a
successful analytical query before any further work on Web entity resolution.
