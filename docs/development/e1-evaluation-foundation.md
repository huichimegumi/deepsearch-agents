# E1 Evaluation foundation

The evaluation direction is now evidence-level local retrieval comparison followed by a small
report acceptance set. `s2sql_041` remains a development diagnostic; its recovery strategy is frozen.

## Changes

- Zero and negative streaming phase allocations stop before agent entry with
  `phase_time_exhausted`. Direct phases use the same admission meaning and do not consume or record
  an LLM call when no phase time is available.
- SQL recovery reservation requires explicit `sql_entity_recovery_enabled=True` at run admission
  plus a clue task. The Hybrid runner opts in. Ordinary Web clue tasks retain their full allowance.
- Reranking returns model identity, actual inference status, and sanitized error category. Invalid
  score cardinality and non-finite values also trigger observable fallback. Retrieved chunks and
  local Evidence metadata retain this status; stable Evidence identity is unaffected.
- Report runs have unique run/session IDs. Existing artifacts and logs are retained. Default CLI
  output lives in a run directory; existing explicit output paths are rejected before execution.
- Manifests contain Git revision/dirty status, dataset and dependency lock hashes, selected model,
  execution settings, and installed dependency versions. They exclude credentials.
- The text-only Judge can read artifact paths from a selected report result JSON. Legacy path
  discovery remains available for historical data.
- Old smoke runners declare their actual measurement scope. Report source constraints and partial
  Trace instrumentation are disclosed rather than reported as autonomous routing or billing totals.

## Verification

Focused evaluation boundary, RAG, entity recovery, Hybrid, Evidence, runner, and Judge tests:
68 passed; complete repository suite: 200 passed, 6 skipped. Boundary tests prove
that exhausted phases never start agents, Web clue tasks keep their allowance, SQL opt-in reserves
capacity, invalid/unavailable rerankers disclose fallback, and repeated report runs retain earlier
artifacts. Ruff checks for changed application/test files and `git diff --check` passed.

No Tavily or LLM evaluation calls were used for E1. Existing PostgreSQL inventory was read to
confirm that six documents have ready indexes and the local model cache exists. Model inference
and the first real A/B/C retrieval run belong to the pilot stage.
