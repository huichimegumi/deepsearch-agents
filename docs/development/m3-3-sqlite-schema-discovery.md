# M3.3 SQLite schema discovery

M3.2 showed that the hybrid research agent repeatedly guessed nonexistent SQLite columns. Listing
table names was not enough: the three-task baseline contained repeated `no such column` failures
and exhausted model calls without converging on a valid query.

M3.3 adds two read-only operations to the unified Evidence Tool when `EVIDENCE_SQLITE_PATH` is
configured:

- `describe_schema` returns one stable SQL Evidence record per table. Each record contains column
  names and declared types, nullability, defaults, primary-key positions, generated/hidden flags,
  foreign keys, and index columns. A caller may provide `table_name` to inspect one exact table.
- `sample_table` accepts only an exact table name discovered from `sqlite_master` and returns at
  most three rows. It exists for bounded value-domain inspection, not for answering analytical
  questions that need an explicit query.

Both operations open the database with `mode=ro`, enable `PRAGMA query_only`, use the existing
query deadline, and produce content-addressed `ev1_sql_...` identifiers. Table names are validated
against the catalog before identifier quoting, so model-supplied SQL fragments cannot be used as a
table name. Full-database discovery is capped at 40 tables; callers can request an omitted table
individually.

The frozen `alien` database validation returned all 11 tables with 11 unique stable IDs. Focused
tests verify columns, a foreign key, an index, the three-row sample boundary, stable identities,
and rejection of an injected table name. The HybridDeepResearch prompt now requires schema
discovery before query construction.

This milestone intentionally targets the SQLite benchmark path. MySQL continues to support the
existing `list_tables` and read-only query operations; unsupported schema/sample operations fail
explicitly rather than silently falling through to an empty query.
