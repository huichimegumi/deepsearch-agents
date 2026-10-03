# M1.2 Live Infrastructure Acceptance

M1.2 is accepted at two levels:

1. the default unit suite validates evidence schemas, stable identifiers, adapters, SQL guards,
   workflow integration, and tracing without external services;
2. an opt-in infrastructure suite validates the same public Evidence Tool against the real local
   MySQL, PostgreSQL, Qdrant, and pinned DABStep snapshot.

## Start the development stack

Run Compose from the repository root and pass the root `.env` explicitly:

```powershell
docker compose --env-file .env -f docker/docker-compose.yaml up -d
docker compose --env-file .env -f docker/docker-compose.yaml ps
```

The explicit `--env-file .env` is required for Compose interpolation. The service-level
`env_file` setting supplies variables inside containers, but it does not define host port
interpolation for the Compose command. Without this flag, defaults such as MySQL port `3306`
can diverge from the application setting in `.env` (the example configuration uses `3307`).

Qdrant server and `qdrant-client` are pinned to `1.18.0`. The acceptance suite rejects a major
version mismatch or a minor-version difference greater than one.

## Seeded local-document fixture

The local-document check expects an indexed knowledge base. The current development environment
uses the small `rag-test` knowledge base containing `测试文件.md`. Override the fixture when using
another environment:

```powershell
$env:EVIDENCE_TEST_KNOWLEDGE_BASE = "your-knowledge-base"
$env:EVIDENCE_TEST_DOCUMENT_QUERY = "a query with a known indexed answer"
```

The fixture is local runtime data and is not committed to Git. A missing knowledge base is an
acceptance failure rather than an automatic skip because the purpose of this suite is to prove the
real retrieval path.

## Run the acceptance suite

```powershell
$env:RUN_EVIDENCE_INFRASTRUCTURE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest tests/integration/test_evidence_infrastructure.py -v
```

The checks cover:

- Qdrant client/server compatibility;
- a live MySQL table listing and repeatable read-only query;
- deterministic rejection of a mutating SQL statement before execution;
- repeatable Fee Evidence against the pinned DABStep snapshot;
- repeatable local-document evidence across PostgreSQL lexical retrieval, Qdrant vector retrieval,
  reranking, and context bounding.

Every repeatability assertion compares `evidence_id`, `locator`, and content. Runtime scores and
timings may change and are deliberately excluded from evidence identity.

## Failure interpretation

- Connection errors indicate environment or Compose configuration failures and return no evidence.
- `NO_EVIDENCE` from the document check means the configured fixture is absent or not indexed.
- An SQL write attempt must return an `ERROR` batch with no records; it must never reach MySQL.
- Qdrant compatibility failures should be fixed by aligning the pinned client and server versions,
  not by suppressing the client's warning.
