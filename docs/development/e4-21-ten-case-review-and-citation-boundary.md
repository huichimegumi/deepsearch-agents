# E4.21 — Ten-case review packets and versioned citation boundary

E4.20 produced ten real, same-source report executions. This stage adds an
offline `ten_case_review` command that revalidates the frozen batch plan and
both result files, checks every saved report/Evidence/Trace/reference binding,
and writes one private `REVIEW.md` plus `input.json` for each of the ten cases.
The worksheet lists the original question, required keypoints, report
segments, each segment's actual cited passage, unknown IDs, and finite
reference coverage. It does not call a generator, search, or database query.
All source text stays under ignored `evals/results/`.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.ten_case_review `
  --plan evals/results/ten_case_plan_20261030T075526Z_902254a746/plan.json `
  --local-results evals/results/report_acceptance_20261030T075549Z_b11bd7a238/results.json `
  --extended-results evals/results/extended_reports_20261030T080951Z_5008c43ce0/results.json
```

The final private review run is
`ten_case_review_20261030T082841Z_a49f3c51e9`. Its
[content-free record](../../evals/reports/e4-21-ten-case-review-2026-10-30.json)
contains only task IDs, input hashes, signal counts, and pending verdicts.
Seven tasks have degraded execution, five have a finite reference retrieval
gap, six have a finite reference citation gap, two already had citation ID
validation failures, and one required-source gap remains. These categories
overlap; their counts are not an answer error rate or human judgment.

## Observed missed citation

`report_cross_002` was marked `completed` in E4.20, yet its evidence snapshot
contains only SQL records. Its generated report cites two `ev2_doc_...` and
`ev3_doc_...` strings as if they were local document passages. The old
`EVIDENCE_CITATION_PATTERN` scanned only `ev1_...` tokens, so the versioned
fabrications were invisible to `validate_report_citations`; the original
audit's `citation_ids_resolve=true` is preserved as a historical observation.
The same report independently has `required_sources_collected=false` and
neither finite reference unit credited. Thus completed execution was not a
successful SQL-plus-local answer.

The runtime citation scanner now recognizes bracketed `ev` plus a numeric
version and an ID suffix, then requires exact membership in the allowed
Evidence set. The separate known-wrapper normalizer still accepts only
eligible canonical `ev1_...` IDs. An offline replay of the untouched saved
report now returns `valid=false` and both fabricated strings in
`unknown_evidence_ids`. The new review record flags this one historically
missed unknown citation. No new live generation is counted as proof of
post-fix report behavior.

## Next quality decision

The immediate runtime boundary is fixed. The ten private worksheets are ready
for source-based AI triage and human claim/keypoint review; accuracy remains
null. Given five finite retrieval gaps and seven degraded executions, the next
development iteration should inspect the missing-source and timeout cases
before choosing one quality intervention. This stage does not label all
uncited statements false or treat literal anchors as semantic entailment.
