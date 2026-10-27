# E4.3 — Saved-extract Writer fidelity comparison

## Scope and implementation

This stage implements the E4.2 next step: compare unchanged source extracts with bounded Writer
paraphrases, and inspect assertions separately from citation validity. It adds an evaluation-only
runner, not a production Writer change. There is no new retrieval, compression or Judge call.

`evals.reports_acceptance.writer_fidelity` consumes the saved E4.2 extraction experiment. Before
any model call, it verifies both cases' input/quote hashes, frozen questions and dataset hash,
rechecks every accepted quote as an exact substring of actual saved fetched-page Evidence, and
filters quotes by official host. It does not load answer keys or evaluator reference pages into
model prompts. Exact/subdomain hostname matching excludes lookalike domains.

Both comparison arms receive the **same filtered extracts**:

- **Source-extract baseline:** a deterministic document containing unchanged quotations, source
  URLs, Evidence IDs and stable `quote_id` values. No model call; explicitly an incomplete source
  artifact, not an answer claimed to be correct.
- **Structured Writer candidate:** at most ten assertion entries, each linking one or two supplied
  quote IDs, plus proposed unanswered-topic labels. The backend checks link membership and inline
  Evidence citations. Unsupported links are rejected; accepted links remain `pending_review` for
  semantics. The candidate visibly says factual support still requires review.

Python's question prefers official sources; this pilot deliberately narrows it to official-only
extracts. PostgreSQL explicitly requests official material. Both arms apply that same restriction.
The Writer prompt preserves scope, subject, modality, units and time, including the exposed
“also → only” and allocator/build errors. This is targeted development, not a hidden holdout.

## Execution and results

```powershell
# Default: verify saved inputs and write deterministic baselines; no model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.writer_fidelity evals/results/extractive_compression_20261027T062414Z_925eced641

# Explicit opt-in: one Writer call per case, two total, no retrieval.
.venv\Scripts\python.exe -m evals.reports_acceptance.writer_fidelity evals/results/extractive_compression_20261027T062414Z_925eced641 --execute
```

Run `writer_fidelity_20261027T064246Z_a6fbc6623d` uses qwen-flash with provider retries disabled
and a 90-second timeout per call. Both calls parse successfully; input/source hashes remain
unchanged. Recorded usage: **1,013 input tokens, 528 output tokens; 2 logical model calls,
0 searches, 0 fetched pages**. Failure/parse outcomes are retained without retries for success.

| Task | Shared official extracts | Excluded non-official extracts | Writer entries | Mechanically valid entries | AI completeness assessment |
| --- | ---: | ---: | ---: | ---: | --- |
| Python 3.13.0 | 3 | 0 | 4 | 4 | Partial |
| PostgreSQL 17.0 | 2 | 1 | 2 | 2 | Partial |

The preliminary AI review covers all six entries, splitting two compound entries into smaller
facts for ten reviewed assertion units. Literal assertion/source spans and artifact hashes are
verified. All ten units appear supported within the supplied release-page extract context.
This is a provisional AI assessment, not independent human adjudication or a trusted Judge
score. Schema/link checks alone cannot make that assessment; a regression test deliberately
accepts a well-linked “only” overstatement as structurally valid to preserve this distinction.

The Python candidate no longer adds platform exclusivity. It also keeps optional/default
allocator wording attached to `mimalloc` rather than transferring it to free-threaded build
installation. However, it does not explicitly answer build installation choice and returns
**no unanswered topics**. It therefore remains incomplete. The prompt also fails to make every
entry atomic: experimental-state/GIL/concurrency and the allocator facts remain combined.

For PostgreSQL, the non-official pgEdge extract is excluded in both arms. The Writer sticks to
release date and JSON_TABLE, listing incremental backup and `pg_combinebackup` as unanswered
topics. It does not invent a utility description or claim that official support does not exist.
But the previous saved **official page already contains incremental-backup text**; the earlier
compression selected only the date and JSON_TABLE from that official page. Removing pgEdge now
exposes a selection gap, not a new retrieval failure. `pg_combinebackup` is absent from the actual
bounded fetched records and cannot be recovered by Writer from these inputs.

Both candidates have fewer observed overstatements than the preserved E4.2 reports, but this
stage changes schema/prompt and applies source filtering. PostgreSQL's inputs differ from the
earlier Writer. Only this stage's two arms share identical extracts. Two exposed tasks with one
sample each cannot establish causal or general accuracy gains. The deterministic baseline adds
no paraphrase errors, but also cannot answer omitted details or guarantee source correctness.

## Verification and artifacts

Full regression: **506 passed, 6 skipped**. Eleven new tests cover hostname policy, exact-quote
revalidation, invalid quote/inline citation links, the structural/semantic distinction, hash
preflight before model admission, default offline behavior, answer-key isolation and retention
of parse failures without extra calls. Ruff lint/format and `git diff --check` pass.

The [content-free public record](../../evals/reports/e4-3-writer-fidelity-2026-10-27.json) stores
source/input/output hashes, counts and provisional assessments. Exact inputs, source-extract
baselines, candidates, structured assertions and the checked `AI_REVIEW.md`/`ai_review.json`
remain ignored under the private run directory. No production defaults change. Human accuracy
and Claim-support rates remain null.

## Next bounded step

Address question coverage before another Writer prompt iteration. On the saved actual Evidence,
identify question parts as answered, selected-extract gap or missing-retrieved-evidence gap.
Recover the official incremental-backup passage from the existing saved PostgreSQL record and
keep the absent utility detail separate. Make Python installation choice an explicit unresolved
part when its supporting source passage is unavailable. Reuse these cases as exposed regression
diagnostics, then add a small independent task set before considering production adoption.

A later, separate targeted official-page fetch can test the `pg_combinebackup` retrieval gap.
Do not silently inject evaluator-only reference text into generation, pool these two tasks into
end-to-end accuracy, or expand Hybrid recovery logic as part of this Writer comparison.
