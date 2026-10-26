# E3.7: one frozen six-task local report baseline

This stage delivers the first-phase result table and source-grounded AI initial findings. All six
development cases ran once under one clean code version, including the failures. Application,
dataset and corpus inputs were held stable through execution. No production fix, judge retry,
prompt tuning or experimental-route promotion was made during this baseline.

## Frozen execution

- Execution commit: `33e91f08439318376a16756a8806036a49ef5773`, clean checkout.
- Model: configured `qwen-flash`; default DeepAgents research route, indexed-local flag false.
- Suite: unchanged `evals/reports_acceptance/local_v1.json`, all six cases.
- Corpus: the same five documents/305 indexed chunks in 电商行业 and 金融行业.
- Corpus fingerprint: `4bd56a51490ea32fe830fd39efa4dd8a97f14a9d4a8457dd8ce6221305f9eedc`.
- Budgets: deep_report 300 seconds, configured LLM allowance 12, Writer reserve 75 seconds,
  outer per-case watchdog 330 seconds, search queries/pages both zero.
- Preflight: Docker services were running; the real runner's corpus and reference checks passed.
  Initial sandbox access to the Docker pipe required the normal authorized escalation.
- Preflight-only run: `report_acceptance_20261026T080753Z_4561a0772c`.
- Actual execution: `report_acceptance_20261026T080816Z_d82eaa1862`; final `inputs_unchanged=true`.

```powershell
# Actual baseline command, run on the execution commit above.
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute
```

The command exited **1** because degraded rows are retained and reported, not because the
experiment disappeared or its inputs drifted. All six had nonempty Markdown, a requested
Markdown artifact, Evidence snapshot and Trace. The negative snapshot correctly contains no records.

## Unified results

The reference columns count finite, literal-anchor evidence units; they do not measure semantic
correctness. AI judgments cover the reference keypoints and salient errors, not every claim.

| Task | Topic | Execution | Delivered content | Seconds | LLM calls | Records | Reference retrieved / cited | AI initial assessment |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |
| 001 | Digital-human scenarios | completed | report | 68.422 | 6 | 6 | 1/1 · 1/1 | Core answered; unsupported financial-marketing digression |
| 002 | Digital-human advantages | degraded | report | 123.000 | 13 | 10 | 1/1 · 1/1 | Core answered; response-time unit error and omitted case-data period |
| 003 | AI customer service | degraded | Claim fallback | 181.547 | 12 | 12 | 1/1 · 1/1 | Core reference covered; cross-document capability attribution error |
| 004 | Monetary-policy stance | degraded | Claim fallback | 84.891 | 13 | 9 | 1/2 · 0/2 | Retrospective answered; outlook omitted and chunk/page range confused |
| 005 | Two-report macro comparison | degraded | Claim fallback | 106.812 | 8 | 7 | 1/2 · 1/2 | Partial facts, wrong supporting chunk, missing China outlook/comparison |
| 006 | No-answer topic | degraded | insufficient-Evidence notice | 41.485 | 5 | 0 | n/a | Bounded no-evidence explanation; no exhaustive absence assertion |

Execution counts: **1 completed, 5 degraded**. Delivery counts: **2 reports, 3 Claim fallbacks,
1 no-evidence notice**. Median elapsed time: **95.852 seconds**, range **41.485–181.547**.
These are one-shot development measurements, not a service latency benchmark or answer accuracy.

Machine failure codes: 002/004 hit `llm_call_limit`, 003 hit research `timeout`, and 003/004/005
failed original Writer citation validation. 006 has a degraded status with no failure-code entry;
its research artifact was a fallback before the deterministic zero-Evidence handoff. Preserve
that distinction rather than inventing a timeout/error code or calling the negative an accepted answer.

The run records 57 LLM calls, 698,119 input tokens and 16,497 output tokens in existing trace
instrumentation. Observed 13 calls on 002/004 exceed the configured allowance of 12: the existing
research-stage admission and downstream compression/Writer accounting must not be described as
a strict total provider-call cap. These counters are not complete provider billing.

## Initial error attribution with actual passages

The private `AI_REVIEW.md` includes report quotations, Evidence IDs/source quotations and, where
available, the original typed compressed Claim. Every quoted span is checked against the saved
artifact; that mechanical check does not validate the AI's semantic judgment.

- **002 — source interpretation in compression.** A customer-interaction passage specifies
  second-level replies. The saved compressed Claim and delivered report describe millisecond
  replies, while a separate passage uses milliseconds for rendering. The incorrect unit exists
  before Writer. The Lenovo figures can be verified, but their event-period qualifier is omitted.
- **003 — document attribution in compression.** The Claim assigns personalized-content/learning
  capabilities to the requested 2025 report while citing a 2026 whitepaper. Its limitation admits
  the source discrepancy, but the principal attribution remains unsupported. The finite customer-
  service reference anchor was retrieved and cited; this is not a missing-reference case.
- **004 — missing outlook and locator interpretation.** The report answers the 2025 stance, not
  the later growth/price policy objective. It describes coverage through page 70, although the
  corresponding locator is chunk 70, metadata PDF page 58, printed page 51. A chunk index is not
  a page audit. No full-document coverage is established.
- **005 — support linked to the wrong available chunk.** The AI-capex/growth passage is present,
  but the matching Claim cites an asset-allocation chunk from the same document instead. The
  Chinese policy outlook unit is missing, and the delivered list does not complete the requested
  comparison. It also introduces an unrequested 2026 China-report requirement.
- **001 — unnecessary unsupported extension.** The requested scenarios are present, but the
  report adds a speculative financial-marketing connection. This does not negate the core answer.
- **006 — transparent limited result.** The backend says that bounded retrieval returned no
  usable passage and explicitly avoids concluding document/topic absence. This is an AI-observed
  boundary outcome, not a human-approved refusal-quality label.

Report-level AI finding counts are: retrieval gap 2; evidence misread 2; unsupported writing 2;
cross-document attribution 1; citation/support mismatch 1; answer omission 1. Categories overlap
and findings are selective; do not sum them into an error rate or claim-unsupported percentage.

There were 25 requested todo/filesystem calls (11 `write_todos`, 5 `ls`, 4 `read_file`, 5 `glob`),
in addition to mandatory/supplemental local retrieval and backend artifact writes. Those are
candidate efficiency costs; this run does not establish how much wall time removing them saves.

## Scoring limitations exposed by this baseline

All five answerable tasks retrieved some Evidence; only three retrieved/cited **all** finite
reference units. 004's retrospective statement is supported by a cited introductory passage,
but that passage lacks the exact configured anchor. Its mechanical cited count is therefore 0/2
while the AI marks the retrospective keypoint covered. The reference annotations are unchanged;
this is an annotation-review candidate, not proof that the retrospective statement lacks support.

All final delivered IDs resolve, including the zero-citation technical notice. Three original
Writer outputs nevertheless failed citation validation and were replaced. Thus final ID resolution
does not establish Writer reliability, original answer quality or fallback Claim entailment.

The AI initial review labels four reference units covered, one partial and two missing. These seven
unit judgments are provisional finite-rubric assessments, not independent ground truth or an answer
accuracy denominator. Human review and accuracy remain pending/null. The existing human-attestation
workflow is untouched, and these AI notes are not submitted as personal human annotations.

## Artifacts and reproducible summary

The full execution stays under its original ignored run directory. The final private AI initial
review is `evals/results/e3-7-ai-triage-20261026/ai_review_v2.json`, with readable `AI_REVIEW.md`.
Its final summary is `evals/results/local_baseline_summary_20261026T082324Z_e7872e3bb2/`.
Earlier initial-review drafts remain separate; only the final version is used in this table.

The small offline summary CLI is added **after** generation. Its source manifest is distinct from
the clean execution manifest. It requires every frozen case exactly once, binds AI notes and
report/Evidence/Trace hashes, rechecks the mechanical audit, validates literal report/source/Claim
quotes and preserves degraded/error rows. Evidence quotations can be review context; they do not
automatically mean that the report cited that record or that its statement is entailed.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.baseline_summary --report-results evals/results/report_acceptance_20261026T080816Z_d82eaa1862/results.json --ai-review evals/results/e3-7-ai-triage-20261026/ai_review_v2.json
```

The [content-free public record](../../evals/reports/e3-7-six-task-local-baseline-2026-10-26.json)
retains separate execution/summary fingerprints, table rows, counters and hashes. Private source
passages and Claim/report quotations are not committed. No extra judge or generative call was
made for initial review. Tavily queries/fetched pages: **zero**.

Full regression after adding the offline summary: **430 passed, 6 skipped**; changed-file Ruff
lint/format passes. Twelve new tests reject omitted/duplicate cases, false human provenance,
changed report/Trace inputs, invented report/source/Claim quotations and unquoted negative labels,
and verify that failures remain visible without an accuracy score.

## Next planned phase

The first-phase baseline is complete even though report quality is weak. Next, add the planned
two Web tasks and two simple cross-source tasks with frozen prewritten requirements and at most
ten cumulative Tavily queries for that batch. Use this baseline's error evidence to choose one
later measured improvement; retain complex Hybrid as diagnostic. Human review may proceed in
parallel. Do not make more lexical rules or a fully adjudicated corpus prerequisites for the next
experiment, and do not present this development batch as independent test performance.
