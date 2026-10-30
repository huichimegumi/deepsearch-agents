# E4.23 — Source-grounded initial review of the two delivery-ready reports

E4.22 found two reports that satisfy the mechanical delivery protocol:
`report_local_001` and `report_local_004`. This stage reviews their frozen
answer keypoints against the actual delivered report and its cited Evidence.
The full review, including report and source quotations and reasons, remains
private under `evals/results/e423-two-case-review.json`. It is an **AI
preliminary assessment**, not a personal human annotation or a whole-report
accuracy score.

The new `two_case_triage` validator binds that review to the private E4.22
packet hash, requires both eligible cases and every frozen keypoint exactly
once, checks each positive report quote in its source segment, and checks the
Evidence quote against an ID actually cited by that same segment. Invented
quotes, unknown IDs, mismatched segment citations and omitted cases fail.
Passing these structural checks does not prove semantic entailment.

| Task | Frozen keypoint | Preliminary finding | Source-grounded limit |
| --- | --- | --- | --- |
| local 001 | Concrete digital-human livestream scenarios | Covered candidate | The cited whitepaper page lists the scene categories; individual claimed business effects and the completeness of the 11-item list were not adjudicated. |
| local 004 | 2025 moderately accommodative monetary policy | Covered candidate | The cited report states that policy was implemented in 2025. |
| local 004 | Continued accommodative policy with growth and reasonable price recovery | Missing | The delivered answer does not state the complete later-policy point; its finite reference unit was not retrieved. |

The [content-free validation result](../../evals/reports/e4-23-two-case-triage-2026-10-30.json)
has per-keypoint candidate labels and hashes but no report or source passages.
It leaves `human_accuracy` and report-level semantic acceptance null. Local
004 illustrates why a technically completed report with valid Evidence IDs
may still fail to answer the full question.

Reproduction, using the locally retained source packet and private review:

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.two_case_triage `
  --packet evals/results/ten_case_review_20261030T083833Z_74cfa7db25/results.json `
  --review evals/results/e423-two-case-review.json
```

This uses zero new retrieval, Web, or model calls. Next, inspect the five
finite reference retrieval gaps and the seven degraded executions in E4.22,
then select one repeatable failure class for a fixed-input improvement test.
