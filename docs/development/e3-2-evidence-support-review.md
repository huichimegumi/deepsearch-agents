# E3.2: evidence-support review packets and fail-closed model suggestions

E3.1b fixed reference formatting, not factual support. This stage adds a separate evaluation
entry point over saved reports. **The production Agent, Claim acceptance rules, retrieval, and
generation budgets are unchanged. Report semantic acceptance remains pending human review.**

## Implemented contract

`evals.reports_acceptance.support_review` loads one executed `local_v1` case, requires a finalized
input-stable execution, checks frozen suite bytes and report/Evidence hashes, and confines resolved
artifact paths to local evaluation results. It verifies the live selected PostgreSQL corpus against
the saved corpus fingerprint before deriving its document inventory. This reads indexed data;
it does not run embedding, reranking, search, or report generation again.

The input package includes body-paragraph segments, their actual inline citation IDs, cited source
records, draft reference keypoints, answerability draft labels, and verified selected-document
names/hashes. Headings are not graded. Lists can contain several claims in one paragraph; these
are **not atomic Claim units**, and no per-claim accuracy rate is computed. Backend rejected-claim
diagnostics are excluded only when the recorded failure and backend partial-result prefix match;
an ordinary model report cannot hide content merely by adding a rejected-drafts heading.

Exact, case-insensitive filename matching checks explicit `《name.ext》` mentions. Unmatched names
are `unverified_filename_pending_review`, not automatic fabrication verdicts. Short titles,
alternative names, and files outside the selected index require manual interpretation. This is
not an exhaustive attachment inventory or proof of corpus-wide absence.

Default operation makes **no model call** and generates a readable `REVIEW.md` with question,
keypoints, report paragraphs, cited IDs, complete cited source passages, metadata, inventory flags,
and unapproved human-review fields. Sources are rendered in inert text fences and deduplicated in
an appendix. Raw source/Claim text stays in ignored private result directories.

## Optional provisional model audit

`--execute-judge` invokes the currently configured model once with a 90-second outer watchdog.
Its existing provider retry policy remains in effect; invocation count is not a billing/request
count. It is the **same configured generator (`qwen-flash` here), not an independent evaluator**.
Reports/passages are explicitly untrusted data; no tools or web access are supplied.

A typed proposal must cover each supplied segment and keypoint exactly once. Report quotes must
be literal contiguous substrings of the relevant body paragraph after whitespace normalization.
Supported/partial/contradicted opinions require a real quote from an actual cited Evidence record
of that paragraph. Unknown, uncited, or invented references/quotes are rejected. Keypoint and
abstention quotes must occur within one supplied body paragraph, not a fabricated concatenation.
Whole-report no-answer review requires an explicit quoted abstention opinion. Input limits are
60 segments / 100,000 serialized characters; oversize input is blocked, never silently truncated.

Quotes being real does **not** establish entailment or correctness of the model's reasoning.
Even quote-valid outputs are only `valid_provisional`; human acceptance is never assigned.
Malformed, incomplete, duplicate-ID, timeout, or grounding failures remain `invalid_review`.
Typed invalid proposals are retained privately as `judge_proposal.json`, not `judge.json` or a
trusted support metric. Static grounding reasons are safe to log; provider error text is omitted.
Input/source drift invalidates the run, and the human worksheet reflects the final invalid state.

`--segment-id` explicitly narrows the scope. It preserves omitted-segment counts, removes reference
keypoint grading, and requires `abstention=not_evaluated`. A selected paragraph cannot receive a
whole-report coverage, refusal-quality, or acceptance score. Duplicate/nonexistent selections fail.
Each v2 run archives its reviewer source and SHA in the private package; earlier pilot source is
also retained locally. Historical execution manifests are separate from new review manifests.

## Commands

```powershell
# Recommended: readable full manual-review packet, no model call.
.venv\Scripts\python.exe -m evals.reports_acceptance.support_review --report-results evals/results/<execution_run_id>/results.json --case-id report_local_006
# Optional selected-paragraph suggestion; not whole-report acceptance.
.venv\Scripts\python.exe -m evals.reports_acceptance.support_review --report-results evals/results/<execution_run_id>/results.json --case-id report_local_006 --segment-id segment_003 --execute-judge
```

Keep `review_input.json`, `judge_proposal.json`, source archives, and `REVIEW.md` private: they
contain the user's document text, filenames, and report content. The opt-in judge sends them to
the configured provider, just as generation does; this is not a new local-only/privacy guarantee.
Only content-free counters, hashes, and limitations are published under `evals/reports/`.

## Real pilot, 2026-10-19: automated acceptance is not ready

Review selected saved reports, not fresh report generations: 002 from E3.1b and 005/006 from
E3.1a. All original reports and generation scores remain unchanged. The first whole-body pilot
failed; its records were preserved before adding an explicitly smaller selected-segment mode.

| Case | Whole-body units | First model review | Selected unit (omitted units) | Selected model review |
| --- | ---: | --- | --- | --- |
| 002 | 15 | timeout | segment_006 (14) | invented/paraphrased report quote |
| 005 | 4 | duplicate segment opinions and missing units | segment_002 (3) | invented/paraphrased report quote |
| 006 | 6 | timeout | segment_003 (5) | invented/paraphrased report quote |

**All six model review invocations were invalid; no suggested verdict, support rate, or abstention
score is accepted.** This is an operational result of this model/protocol/sample, not a claim that
all LLM judges fail. The negative-case proposal even confused a report segment ID with an Evidence
ID and treated report assertions as passage evidence. Literal grounding checks prevented those
opinions from being promoted into acceptance. No extra retries were made after the bounded pilot.

The deterministic inventory check flags 0 / 2 / 5 filenames on full reports 002 / 005 / 006,
respectively. These are reproducible review candidates, not automatically scored hallucinations.
Three new full manual packets were then generated without model calls. Their local directories:

- 002: `evals/results/support_review_20261019T122801Z_294bdc4d98/`
- 005: `evals/results/support_review_20261019T122812Z_7864221582/`
- 006: `evals/results/support_review_20261019T122821Z_7989896c29/`

The final post-pilot code also ensures a drift-invalidated run's worksheet cannot display the
earlier provisional model status; this does not change any preserved pilot verdict. Reviewer
source snapshots/hashes preserve the earlier protocol versions. No reports were regenerated,
no retrieval inference or web queries were made, and human review is still pending for all cases.
See the [content-free operational record](../../evals/reports/e3-2-support-review-2026-10-19.json).

## Verification and next work

Full regression: **307 passed, 6 skipped**; changed-file Ruff lint/format checks pass. The 34 new
tests cover segmentation, ordinary-versus-backend diagnostic sections, filename-candidate scope,
literal report/source grounding, citation binding, missing/duplicate reviews, keypoint/abstention
rules, input bounds, artifact paths/hashes, corpus/suite drift, no-model default, explicit subset
scope, invalid-proposal retention, readable source worksheets, and final drift-invalid status.

This completes the evidence-review **foundation**, not E3 semantic acceptance. Use the full manual
packets for real human judgments and preserve corrections as annotations before reporting factual
accuracy. Do not use the current model judge as a production veto or approval gate. Generation
still needs evidence-grounded source-inventory handling, better cross-document coverage, and less
built-in tool churn. The planned two web/two simple cross-source reports remain outstanding; broad
paid evaluation should not substitute for resolving these local development failures.
