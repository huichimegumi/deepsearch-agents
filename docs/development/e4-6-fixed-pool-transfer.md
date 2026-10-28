# E4.6 — New questions with automatic source selection

## Frozen task group

This stage freezes three new development questions in
[`transfer_v1.json`](../../evals/reports_acceptance/transfer_v1.json), before the first model call:

1. List the first/second and third/fourth chapter titles in a local digital-human whitepaper.
2. Distinguish the referenced retail survey year from report year, and the overall AI-use
   percentage from the large-retailer percentage in a local ecommerce report.
3. Request measured per-store revenue uplift and study sample size that the supplied excerpts
   do not establish; retain a bounded nonanswer rather than substituting industry estimates.

Each task supplies two hash-pinned records from actual E3.7 saved local Evidence. These are new
questions on a previously exposed corpus, not an independent holdout. The developer chooses the
small source pool; selection **within** it is automatic. No new RAG query, source fetch, manual
post-output source addition or evaluator reference injection occurs.

## Implementation and initial failure

The E4.5 runner now exposes shared bounded execution instead of duplicating its Writer loop.
The new transfer runner verifies all pool hashes/record identities before model admission, runs
selection separately, then uses the unchanged E4.3 Writer instruction/schema. Empty selection
skips Writer and preserves every required part as unresolved. Review-assisted and automatic
fixed-pool selection are explicitly distinguished in output and metadata.

The first selector proposed literal quotes. Both positive cases failed provenance checks:
short chapter headings acquired extra punctuation resembling serialization syntax, and survey
quotes omitted PDF line breaks. The old quote schema's 20-character minimum also made individual
short headings ineligible. The negative case selected no support. All three Writer calls were
skipped. This failed pilot is retained as
`fixed_pool_transfer_20261028T032154Z_ae7d3009de`: **3 model calls, zero candidate parts**.

The corrected interface asks only for existing `evidence_id` values. The backend copies the
entire original selected chunk, preserving line breaks and short text, and binds its quote ID to
the question part. Unknown IDs, duplicate/missing part entries, blank chunks and chunks over
1,200 characters cannot silently become selected support. Whole chunks are rejected when over
the limit, not truncated. No fuzzy text repair is performed. The historical Web quote policy
and production workflow remain unchanged.

This removes model transcription from provenance checking. It does not establish that an ID is
relevant or that a Writer assertion is entailed. Both selection sufficiency and Writer semantics
still require review; same-part links can be wrong.

## Execution and observations

```powershell
# Default: verify frozen inputs and create templates; no model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.transfer

# Explicit opt-in: at most three selector + three Writer calls; no retrieval.
.venv\Scripts\python.exe -m evals.reports_acceptance.transfer --execute
```

The ID-selector run is `fixed_pool_transfer_20261028T032525Z_ec7e9b810f`:

| Task | Selector calls | Writer calls | Linked candidate parts | Unresolved parts | AI initial assessment |
| --- | ---: | ---: | ---: | ---: | --- |
| Chapter titles | 1 | 1 | 2 | 0 | Complete within supplied excerpts |
| Survey year/subgroups | 1 | 1 | 2 | 0 | Complete within supplied excerpts |
| Missing measured outcomes | 1 | 0 | 0 | 2 | Appropriate bounded nonanswer |

Both variants use qwen-flash, one sample per task, provider retries disabled and a 90-second
timeout per call. The three questions, source pools and Writer instruction stay unchanged across
variants. The selector schema/prompt and amount of Writer context change, so this is not an
isolated general accuracy comparison.

Total for this stage: **8 logical model calls, 0 searches, 0 fetched pages**. The failed pilot uses
4,317 input/476 output tokens; the revised run uses 6,124 input/584 output tokens. More stages
actually execute in the revised run; no cost/latency reduction is claimed. Negative-case Writer
reasoning is not evaluated because it is skipped.

AI initial review checks five Writer assertion entries across seven factual units: chapter
titles, survey year and both subgroup percentages. The positive candidates match their source
context, while the negative document makes no corpus-wide absence claim. These provisional
observations are not human acceptance or a trusted Judge score. Human accuracy remains null.

## Verification and provenance

Full regression: **537 passed, 6 skipped**. Six new tests cover backend resolution of short and
multiline chunks, unknown/duplicate selection, frozen-source mutation before model admission,
default offline operation, and separate selection/Writer calls with skipped empty selection.
Existing reviewed-handoff and historical Web-quote tests remain passing. Changed Python files
pass Ruff lint/format; `git diff --check` passes.

The source files used by the failed pilot are archived privately. Substituting their two hashes
into the final source map reconstructs its recorded fingerprint exactly. The ID-based live run
uses the final Python source; frozen dataset/input/output hashes are checked for both variants.
The [content-free record](../../evals/reports/e4-6-fixed-pool-transfer-2026-10-28.json) retains both
manifests, counts, outcomes and AI-review hashes. Source text, complete outputs and checked AI
worksheets remain ignored under `evals/results/`.

The next useful step is an opt-in report evaluation path that feeds **actual RAG retrieval
results** into ID selection and Writer, retaining this small group as exposed diagnostics. That
will test whether support reaches the selector rather than assuming a developer-picked pool.
Keep production defaults unchanged until that boundary is exercised; do not pool these results
with earlier reports into an end-to-end accuracy number.
