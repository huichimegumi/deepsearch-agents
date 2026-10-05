# HybridDeepResearch smoke evaluation

This adapter is an engineering smoke test for cross-source orchestration. It is not a benchmark
score and must not be compared with results on all 380 HybridDeepResearch tasks.

## Fixed inputs

- Tasks: `Snowflake/HybridDeepResearch` release revision
  `31304784b7aec82f22d59772a8afeb78567fd8b3`.
- Database: `birdsql/livesqlbench-base-lite-sqlite` revision
  `0664a2f28555faa0dd2947c8c23288df79bcc06b`.
- Smoke subset: `s2sql_041`, `sql2s_192`, and `parallel_053` from the upstream official subset.
- Database: all three tasks use `alien`, so the smoke run downloads only one SQLite domain.

The three IDs cover Search-to-SQL, SQL-to-Search, and Parallel Fusion once each. This is the
smallest balanced routing check. It can expose broken modality handoffs, but its correctness rate
has no statistical meaning.

Upstream tasks are encrypted with a public canary to reduce accidental benchmark contamination.
This adapter verifies and decrypts selected records in memory. Never commit decrypted questions,
gold answers, reference SQL, model outputs, or evaluation logs.

## Prepare and inspect the budget

```powershell
.\.venv\Scripts\python.exe -m evals.hybrid.download_dataset
.\.venv\Scripts\python.exe -m evals.hybrid.run_smoke --json
```

The second command is a dry run. It writes no agent answer and performs no Web search. The fixed
default limits are:

- three tasks total;
- at most two search queries per task;
- at most two fetched pages per task;
- at most six search queries and six fetched pages for the complete smoke run.

The default backend is hard-locked to `duckduckgo`, which does not use the configured Tavily API
key even if the model requests `advanced`. Modes that
may consume paid credits (`tavily`, `perplexity`, `auto`, and `advanced`) fail closed unless the
operator also passes `--allow-paid-search`.

## Execute

```powershell
.\.venv\Scripts\python.exe -m evals.hybrid.run_smoke `
  --execute `
  --search-backend duckduckgo
```

To intentionally use Tavily:

```powershell
.\.venv\Scripts\python.exe -m evals.hybrid.run_smoke `
  --execute `
  --search-backend tavily `
  --allow-paid-search
```

Results are written under ignored `evals/results/`. They contain task IDs, statuses, budget usage,
evidence counts, citation validity, and correctness booleans, but not decrypted task or answer
content.

## Evaluation boundary

For Search-to-SQL, the runner extracts the submitted read-only SQL, executes it against the pinned
SQLite database, and compares result tables. SQL-to-Search and Parallel use conservative normalized
gold containment as a local smoke signal; the official benchmark uses an LLM judge. The local
metric is therefore named `strict_correct`, not official accuracy.

Every task also reports whether both SQL and Web Evidence were collected, whether final citations
passed backend validation, elapsed time, query/page usage, and accepted/rejected Claim counts.

## First DuckDuckGo baseline

The first post-fix execution on 2026-10-05 is recorded in
[`docs/development/m3-2-hybrid-smoke-baseline.md`](../../docs/development/m3-2-hybrid-smoke-baseline.md).
It used four of the six allowed queries and no intentionally authorized paid backend. All three
reports passed citation validation, two collected both source types, and none passed the strict
answer check. This is a diagnostic baseline, not a result to optimize by leaking task-specific gold
information into prompts.
