# E4.2 — Claim delivery boundary and extractive compression pilot

## Completed change

E4.1 exposed a concrete delivery bug: a Writer with unapproved citations fell back to raw
compression Markdown. That Markdown included unchecked outlines, rejected drafts, conflicts and
uncertainties. The fallback could itself fail citation validation and still be returned.

The backend now retains structurally accepted typed Claims privately in the run trace. Both the
production Writer handoff and citation fallback are rendered from that registry. Unchecked
compression side fields remain available on the diagnostic model, but are not handed to Writer
or delivered as fallback facts. Accepted Claim limitations remain visible.

If the fallback has no accepted Claims or fails citation validation, the backend returns a
technical delivery-withheld notice. The trace records `report_citation_withheld=true`, the run
remains degraded, and the final artifact status is `citation_withheld` or
`citation_withheld_persisted`. A usable typed fallback is separately marked with
`report_used_claim_fallback=true` and `validated_fallback[_persisted]`. Existing local filename
and absence-scope guards still apply to the typed fallback.

`report_citation_valid=true` on a technical notice means only that the notice has no invalid
citations. It must not be counted as successful answer delivery. Trace schema 12 receives these
two additive top-level flags; historical traces do not contain them. Claim text stays outside
ordinary trace summaries; explicit private evaluation capture retains its existing behavior.

This does **not** verify factual support. A structurally accepted Claim can still misread units,
infer unsupported negatives or cite irrelevant text. The rendered package says this explicitly.

## Fixed-input citation replay

Ten existing delivered documents were replayed through citation enforcement, with their actual
saved Evidence and typed Claim-validation inputs: six local E3.7 tasks, the two E3.8 cross-source
tasks, and the latest two E4.1 Web tasks. There was no retrieval or model call.

All ten replayed deliveries pass citation checks. One document, Python Web 001, is replaced by a
typed Claim fallback: its unchecked outline no longer introduces a registered-but-unapproved
Evidence ID. The other nine remain unchanged; no saved case requires the new withheld notice.
Synthetic regression tests cover missing typed Claims and invalid IDs embedded inside accepted
Claim text, proving those paths withhold the answer.

This replay deliberately tests citation delivery in isolation, without reconstructing local
intent/retrieval state. It is not regeneration, a new end-to-end baseline, or semantic review of
the ten documents. Wrong historical Claims remain wrong after successful citation repair.

## Saved-Web extractive experiment

An evaluation-only CLI tests whether source extraction can reduce unsupported compression:

```powershell
# Default: create a manifest only; no paid/model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.extractive evals/results/extended_reports_20261027T055936Z_09f89e8bc9

# Explicit opt-in: at most four logical model calls; no search or page fetch.
.venv\Scripts\python.exe -m evals.reports_acceptance.extractive evals/results/extended_reports_20261027T055936Z_09f89e8bc9 --execute
```

The two original Web questions use their actual saved fetched-page Evidence, not evaluator-only
reference pages or answer keys. Compression proposes at most twelve `(evidence_id, quote)` pairs.
The backend accepts only exact contiguous substrings from eligible fetched Web records, without
fuzzy matching or paraphrase repair. Duplicate pairs are deduplicated. Only accepted extracts
reach the experimental Writer. Production `ClaimDraft` and the production compression policy
are unchanged; the experimental CLI is not wired into the application workflow.

One qwen-flash sample per task was run, with provider retries disabled and a 90-second timeout
per call. Run: `extractive_compression_20261027T062414Z_925eced641`.

| Task | Accepted quotes | Rejected quotes | Calls | Writer citation check | AI initial assessment |
| --- | ---: | ---: | ---: | --- | --- |
| Python 3.13.0 | 3 | 0 | 2 | valid | Partial; unsupported platform exclusivity |
| PostgreSQL 17.0 | 3 | 1 | 2 | valid | Partial; missing utility detail and source-authority violation |

Total: **4 logical model calls, 0 searches, 0 fetched pages**; recorded usage is 11,420 input and
1,385 output tokens. Source fingerprints and saved-input hashes are unchanged during execution.
The private artifacts retain exact prompts, quotes, reports and hashes.

The PostgreSQL extractor invented a `pg_combinebackup` passage and attributed it to pgEdge. That
passage is absent from the saved page and was rejected before Writer. The Writer then reported
the utility detail as unavailable in the supplied material, instead of claiming it was not an
official PostgreSQL component. However, its incremental-backup paragraph still cites a
third-party page despite the task requiring official sources. The actual missing official
utility passage cannot be recovered by compression alone.

The Python Writer still changes an extract saying the build is available in Windows/macOS
installers “as well” into an exclusive platform restriction. It also draws installation-choice
conclusions beyond what the selected mimalloc passage establishes. Exact quote provenance did
not prevent unsupported interpretation. Neither task receives a complete/correct acceptance.

These are checked, provisional AI observations, not human adjudication or a trusted Judge score.
Human accuracy and Claim-support rates remain null. Report quotations and their source passages
are verified in the private `evals/results/e4-2-replay-20261027/ai_review.json` worksheet.

This pilot jointly changes the compression schema and Writer prompt, uses saved full bounded
records rather than the production ledger's per-record display limit, and has only two exposed
development tasks with one sample each. It cannot isolate a causal accuracy improvement or
establish a speedup. Exact substring matching establishes provenance, not source authority,
relevance, completeness or entailment. Keep it evaluation-only.

## Verification and next stage

Full regression: **495 passed, 6 skipped**. Tests cover typed-only handoff/fallback, fail-closed
delivery, private Claim retention, existing local guards and exact-extract rejection. Changed
Python files pass Ruff lint/format, and `git diff --check` passes. The
[content-free result record](../../evals/reports/e4-2-claim-delivery-2026-10-27.json) includes
manifests, per-case hashes, replay distinctions and failed quality assessments. Raw material
remains ignored under `evals/results/`.

Next, use these same saved extracts to test Writer factual support at individual-assertion
level, especially “also” versus “only” and optional allocator versus optional build. Compare a
source-extract-only delivery with a bounded structured paraphrase, preserving missing details
and official-source requirements. Do not expand negative-assertion keyword gates or add more
Hybrid recovery branches. A separate targeted official-page retrieval experiment is needed for
the missing PostgreSQL backup passage; do not inject evaluator reference text into generation
and call it retrieval success.
