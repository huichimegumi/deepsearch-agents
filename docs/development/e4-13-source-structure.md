# E4.13 — Exact document resolution and explicit TOC delivery prototype

E4.12 rejected blanket title replacement. This stage adds a pure planning module,
`app/rag/source_structure.py`, and an offline replay runner. Production search, Evidence Tool,
API and UI call sites do **not** invoke it. There is no new runtime feature flag or deployment.

## Implemented behavior

- Resolve explicit `《document name》` references against actual snapshot filenames using Unicode
  NFKC, case folding, whitespace removal and recognized document-extension removal only. Do not
  infer aliases, expand abbreviations, remove date prefixes or choose a similarly named report.
- Resolve all named sources or return an explicit unresolved/ambiguous status. Identical names
  attached to different document hashes are ambiguous. Negated source constraints conservatively
  return an unsupported status. Fallback preserves the old result; it does not claim to satisfy
  an unresolved or unsupported source constraint.
- Recognize affirmative TOC requests independently of source matching. Require a standalone
  raw-text `目录`, `CONTENTS` or `table of contents` marker and at least two distinct numbered
  entries. A thematic paragraph or a generic request about a chapter is insufficient.
- For each resolved source, select a TOC only when exactly one structural chunk exists in the
  scoped snapshot and that same chunk already belongs to the frozen candidate pool. Multiple
  possible TOCs, missing structure, out-of-pool structure or more than two named sources produce
  explicit structure statuses and no structural reservation. No chunk is injected from a label.
- Scope the saved ranking to resolved document hashes, retain the existing score threshold/top
  eight, then reserve up to two selected structural chunks ahead of those thematic hits. Reapply
  the same final six-hit/10,000-character limiter. Unresolved names preserve the saved policy
  byte-for-byte rather than rebuilding already truncated passages.

**Structural reservation intentionally bypasses the semantic score gate.** This is a separate,
explicit source/structure selection method, not reranker acceptance or a new calibrated score.
The original score remains historical. This differs from E4.9's unconditional vector protection:
it requires an affirmative structural request, exact document identity, a unique actual TOC and
membership in the existing candidate pool. These guards are still heuristics, not semantic proof.

Returned passages stay raw; no heading or summary is invented. The existing Evidence adapter
computes IDs from document/chunk/content identity. Changing the retrieval method or ordering does
not change an ID when that identity is unchanged; actual text truncation can change an ID. The
replay supplies no invented knowledge-base IDs because the corpus snapshot omits them.

## Reproduction

```powershell
# Verify private hash-bound inputs, write plan only; no replay/model/services.
.venv\Scripts\python.exe -m evals.rag.run_source_structure

# Reuse saved E4.10 scores and candidate membership, without inference.
.venv\Scripts\python.exe -m evals.rag.run_source_structure --diagnostic --execute
.venv\Scripts\python.exe -m evals.rag.run_source_structure --execute
```

Inputs remain the earlier E4.8/E4.9 corpus/pools and E4.10 paired outputs. The runner verifies
saved result hashes, candidate/control membership and historical development metrics, checks
delivery configuration, and rechecks source/input hashes after execution. Failures invalidate a
row without retry. Default execution creates a plan only. No holdout questions are loaded.

Final runs:

- Diagnostic: `source_structure_diagnostic_20261029T030916Z_102d05813f`.
- Development: `source_structure_dev_20261029T030921Z_b3ae1cccf4`.

Two preliminary offline replays preceded addition of explicit negated-source handling and stable
Evidence IDs. The public record binds only the final implementation/runs above. Neither the
preliminary nor final replays performed inference or new retrieval.

## Results and limits

| Diagnostic reference | Saved raw/context delivery | Scoped raw/context delivery |
| --- | --- | --- |
| TOC | Absent / absent | 1 / 1 |
| Survey paragraph | 3 / 1 | 3 / 1 |

The TOC's **delivery** is recovered in the saved-pool replay by explicit structural selection.
Its original semantic rerank positions remain 29/28. Its unchanged raw text produces the same
`ev1_local_document_4072a8b1a934c6f323e8aed5` as the earlier source record. The survey's ID remains
`ev1_local_document_33124c6985a61183e34ca2b0`. Earlier saved hit controls omitted an `evidence_id`
field; null baseline ID fields in the public record indicate that missing field, not absent
survey evidence. Current scoped hits use the normal adapter.

| Development condition | Finite-unit Recall@6 | MRR@6 | Complete finite units |
| --- | ---: | ---: | ---: |
| Raw baseline / scoped | 0.702 / 0.702 | 0.480 / 0.480 | 12/19 / 12/19 |
| Context baseline / scoped | 0.754 / 0.754 | 0.592 / 0.592 | 12/19 / 12/19 |

All 20 development rows and both diagnostics are valid. All development delivery IDs and actual
texts remain identical to their own baselines. The no-answer case returns zero hits in every
condition; no generator abstention or answer correctness is measured.

Only **8/20** development questions resolve explicit document names. **9/20** financial questions
have titles that do not exactly match indexed filenames and therefore retain original results;
**3/20** use no explicit `《》` source reference. None of these development questions exercises the
positive TOC branch. Unchanged aggregate scores are therefore a limited regression control, not
proof of broad document-resolution or structural precision. In particular, the customer-service
and cross-document coverage gaps from E4.10 remain unresolved.

Total: **zero new retrieval queries, rerank/embedding calls, generator calls or Web searches**.
This is a post-hoc replay on exposed development data, not a fresh end-to-end retrieval run,
holdout result, production fix or repaired report. Finite labels remain provisional/nonexhaustive;
human accuracy is null. Raw passages/full outputs stay ignored under `evals/results/`; the
[public record](../../evals/reports/e4-13-source-structure-2026-10-29.json) contains only hashes,
source plans, metrics, IDs, budgets and counts.

## Verification and next stage

Twenty-four focused tests cover strict normalization, unknown/ambiguous/negated source references,
all-or-nothing multi-source resolution, negative structural requests, standalone markers and
distinct entries, ambiguous/missing/out-of-pool structure, source reservation bounds, explicit
score bypass, source isolation, stable raw Evidence IDs, context limits, immutable fallback,
invalid pool/control rejection and offline plans. Full regression: **620 passed, 6 skipped**.
Ruff lint/format and `git diff --check` pass.

Next connect this planner behind an explicit experimental switch to real scoped indexed
retrieval, preserve source/method diagnostics, and run the frozen TOC/survey/insufficient-evidence
report tasks. Confirm the live corpus and Evidence IDs, then inspect whether the Writer uses
the actual TOC instead of inferring chapters from thematic body headings. Unknown/ambiguous
source handling and broader structural negatives remain required before any default switch.
