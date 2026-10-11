# M3.15 Pinned SQL semantic context

## Post-M3.14 validation finding

The post-timeout-recovery single-task diagnostic used the explicitly authorized 6/6 Tavily
override and consumed six queries and six fetched pages. All workflow phases completed, so M3.14
successfully removed the workflow-level timeout failure. The run still produced no analytical SQL
Evidence: five of seven SQL attempts returned no rows, and both correction proposals failed with
unknown-column errors. Citation validation passed, but strict evaluation remained false.

The correction model treated a named derived metric as a physical database column even though the
physical schema was available. This was not a need for more Web retrieval. The locked database
release already contains two semantic sidecars that the runner verified by byte size and SHA-256
but did not mount:

- `alien_column_meaning_base.json` maps physical columns to business meanings;
- `alien_kb.jsonl` defines named domain metrics and their formulas.

The implementation never records decrypted questions, reference SQL, gold answers, or model output
in the repository.

## Semantic schema Evidence

When `EVIDENCE_SQLITE_COLUMN_MEANINGS_PATH` is configured, `operation=describe_schema` merges the
matching business description into each physical column as `semantic_description`. The sidecar is
read-only, capped at 2 MiB, parsed as a strict `database|table|column` mapping, and content-hashed.
The sidecar hash participates in the schema Evidence identity, so changing a description produces a
new stable `evidence_id`; repeated reads of unchanged database and metadata produce the same ID.

The Hybrid runner mounts the already locked `alien_column_meaning_base.json` beside the SQLite
database. Trace schema v11 reports `sql_semantic_schema_columns` without copying descriptions into
portable telemetry.

## Bounded domain-formula discovery

`collect_evidence` now supports the SQLite-only operation `search_semantic_knowledge`. It searches
the configured JSONL sidecar with deterministic exact-name and lexical-overlap ranking and returns
at most eight `database_semantics` records. Their stable identity includes the database fingerprint,
sidecar hash, and upstream entry ID.

The research workflow instructs the Supervisor to use this operation before querying a named
derived metric. More importantly, the backend-controlled SQL correction phase automatically
prefetches semantic knowledge using the original task before rendering its Evidence Ledger. This
keeps the recovery path effective even when the Supervisor omitted the discovery call.

Schema, samples, and semantic rules remain discovery-only. `database_semantics` IDs are deliberately
excluded from the Claim gate: they may guide query construction, but the final business result must
still come from a successful `operation=query` result. Formula discovery consumes no Web search,
fetched-page budget, or research round and shares the existing SQL-correction deadline.

Trace schema v11 adds `sql_semantic_discovery_calls` and retains the per-kind SQL Evidence counts.
Hybrid results expose semantic schema columns, discovery calls, semantic records, and aggregate
totals. The dry-run report also confirms whether both pinned sidecars are mounted.

## Verification boundary

Deterministic tests cover:

- semantic descriptions merged into schema Evidence with content-sensitive stable IDs;
- exact-name formula retrieval, irrelevant-entry filtering, and stable semantic Evidence IDs;
- discovery-only exclusion from Claim-eligible Evidence;
- backend prefetch of a named formula before structured SQL correction;
- no change to Web-query, fetched-page, or research-round usage;
- Hybrid dry-run reporting for both locked sidecars.

No additional paid search was used while implementing M3.15. A later one-task live diagnostic can
measure whether the pinned formula context converts the former unknown-column correction into a
successful analytical query.
