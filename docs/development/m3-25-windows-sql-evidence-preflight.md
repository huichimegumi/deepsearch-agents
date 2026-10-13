# M3.25 Windows-safe SQLite Evidence paths and paid-run preflight

## Motivation

The first live validation after M3.24 used the explicitly authorized one-task Tavily 6/6 ceiling.
The stable `network_search` route worked: the run consumed six queries, fetched five pages, and
created five Web Evidence records. This confirms the M3.24 routing fix under the real workflow.

However, every SQL Evidence call returned an error. The run produced zero SQL records, zero semantic
records, and never reached SQL correction or the structured entity gate. The audit warning was a
Windows `PermissionError` on the locked SQLite file.

The file was present and readable: direct byte reads, SHA-256 hashing, and a read-only SQLite URI all
succeeded. The failure came specifically from `Path.resolve(strict=True)`, whose strict Windows
realpath probe was denied in the managed workspace even though ordinary read access was allowed.

## Windows-safe file validation

SQLite database and sidecar paths now share one resolver that:

1. expands the user component;
2. performs non-strict absolute canonicalization;
3. explicitly requires `is_file()`;
4. reads file metadata only after the file check.

This is applied consistently to the database, column-meaning JSON, and semantic-knowledge JSONL.
The change does not relax SQLite execution: connections still use `mode=ro`, enable
`PRAGMA query_only`, enforce the progress-handler timeout, and retain all read-only SQL validation
and result limits.

## Preflight before paid retrieval

The Hybrid runner now exercises the production SQLite Evidence path before invoking the Agent. With
the same temporary environment that will be used for the task, it:

- loads `describe_schema`, including the configured column-meaning sidecar;
- searches semantic knowledge using the in-memory task question;
- rejects any structured Evidence error;
- requires at least one schema record.

If preflight fails, `run_deep_agent` is never called. Consequently Tavily, other Web backends, model
research, and report generation cannot start while the required local SQL source is unavailable.
The decrypted task remains in memory and is not written by preflight.

## Verification

The production preflight succeeds against the hash-locked `alien` SQLite database and both real
sidecars on Windows. Unit coverage asserts that no file resolver requests `strict=True`, and a
runner-level negative test proves that preflight failure prevents the Agent entrypoint from being
called.

The complete suite passes with **180 passed and 6 skipped**, with Ruff and diff checks clean. The
single live diagnostic used six Tavily queries and five pages. No post-fix paid run was started, and
generated questions, answers, SQL, model output, audit logs, and result files remain ignored.

## Remaining boundary

The next one-task validation should first confirm nonzero SQL semantic Evidence alongside Web
Evidence, then observe the M3.23 bounded entity-rejection category or a successful unique database
value match. No entity-gate or formula-equivalence change should be made until that post-preflight
result is available.
