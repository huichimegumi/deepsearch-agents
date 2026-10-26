# E3.6: saved-report annotation, adjudication and result aggregation

E3.2 produced readable report/Evidence worksheets, but there was no structured path from a
person's notes to an explicit final result. E3.6 adds that offline path. It does not supply human
labels, rerun a judge, change production generation, or promote the indexed-local experiment.

## Commands

```powershell
# Use one or more finalized support-review packets. No live corpus connection is needed.
.venv\Scripts\python.exe -m evals.reports_acceptance.adjudication init --review-results evals/results/support_review_20261019T122801Z_294bdc4d98/results.json --review-results evals/results/support_review_20261019T122812Z_7864221582/results.json --review-results evals/results/support_review_20261024T144244Z_1963e7f860/results.json
```

The command creates a unique ignored `evals/results/human_review_.../` directory containing:

- `batch.json`: source packet paths/hashes and report identities/scopes.
- `annotation.template.json`: intentionally invalid pending fields, with every expected segment
  and reference keypoint listed once. No verdicts are guessed or copied from model proposals.
- `annotation.schema.json`: allowed values and required fields, generated from the strict models.
- `INSTRUCTIONS.md`: how to read each source packet's adjacent `REVIEW.md` and fill the template.

Copy the template to a new annotation file. A person must provide their identifier, a timestamp
with timezone, the exact personal-review attestation shown in the instructions, and all judgments.
The attestation is self-reported: this CLI cannot authenticate authorship or prove independence.
Do not present agent-generated judgments as human work.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.adjudication validate --batch <batch.json> --annotation <filled-annotation.json>
# Pending summary: succeeds, with zero adjudications and an unavailable acceptance rate.
.venv\Scripts\python.exe -m evals.reports_acceptance.adjudication summarize --batch <batch.json>
```

For a final decision, preserve the initial annotation file. Make a separate file with
`stage=adjudication` and `prior_annotations` entries containing the repository-relative path and
SHA256 of each initial annotation. The adjudicator personally resolves differences in the final
item/segment reasons and corrections; the software does not vote or infer the correct judgment.
The same person may adjudicate, but the summary reports overlap with initial reviewers and does
not call that an independent review.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.adjudication validate --batch <batch.json> --annotation <final-adjudication.json>
.venv\Scripts\python.exe -m evals.reports_acceptance.adjudication summarize --batch <batch.json> --adjudication <final-adjudication.json>
```

Each summary writes new `results.json` and readable `SUMMARY.md` under an ignored unique directory.
Initial annotations alone cannot generate a final acceptance score. Unfilled templates exit 1 with
structured validation errors; error output omits Pydantic input values. Successful validation only
means schema, quote and consistency checks passed, not that the human's semantic judgment is true.

## Judgment and integrity rules

The existing quote-grounding validator is reused: every included paragraph and keypoint must be
reviewed exactly once, report quotations must occur in the corresponding paragraph, and evidence
quotations must come from that paragraph's actual cited records. Supported/partial/contradicted
verdicts need passage quotations. Negative cases need a quoted abstention judgment. Selected-segment
review cannot assess whole-report abstention or count as accepted whole-report work.

Problem paragraphs (`partial`, `unsupported`, `contradicted`) additionally require at least one
unique error tag and an actionable correction. Tags are `scope_overclaim`, `unsupported_assertion`,
`irrelevant_evidence`, `missing_citation`, `source_identity`, `numeric_error`, and `other`.
These are explicit reviewer labels; filename warnings and lexical gates do not assign them.
Supported paragraphs cannot simultaneously carry error tags. Reasons cannot be blank.

Each item includes a separate assessment of the draft reference labels (`confirmed`, `uncertain`,
`incorrect`), an overall decision (`accepted`, `rejected`, `uncertain`), and a decision reason.
Acceptance requires nonempty whole-report coverage, supported paragraphs, covered keypoints,
applicable acceptable abstention and reviewer-confirmed reference labels. A rejection needs an
explicit recorded failure; uncertainty can remain unresolved without inventing a pass or failure.

The batch pins source packet bytes. Loading rechecks packet/input/report/Evidence hashes, the
original frozen local_v1 dataset and execution manifest, known case identity, and safe paths under
`evals/results`. Inputs are reconstructed from the original report/Evidence and frozen case labels,
including rejected-diagnostic exclusions and selected-segment semantics. The saved packet's indexed
inventory is reused; it is not a fresh exhaustive-corpus audit. Duplicate instances of the same
executed report are rejected, including overlapping whole/selected scopes. Final adjudications
revalidate every initial annotation and its hash; duplicates, chains and cycles are rejected.
Hashes establish consistency, not signatures or protection against someone rewriting an entire
artifact lineage. Earlier reviewer-source manifests are preserved, not re-executed.

## Aggregation boundaries

The summary distinguishes expected, pending and adjudicated report scopes, distinct cases and
original executions. It reports final decision counts, paragraph verdict counts, error-tag counts,
the number of report-level decision disagreements between initial annotations, and how many initial
annotations share the adjudicator's identifier. It does not claim inter-rater agreement for all
paragraphs or independent human consensus.

The acceptance denominator includes only whole-report, reference-confirmed, resolved final items.
Uncertain decisions, selected scopes and unconfirmed references are excluded, with an explicit
excluded count. No eligible items means `acceptance_rate=null`, never 0% or 100%. Paragraphs are not
atomic claims, multiple tags may describe one paragraph, and these selected saved reports do not
estimate population accuracy. Mixed executions are visible; do not treat them as a controlled
before/after experiment. Production `completed`/`degraded` status remains independent of these
human decisions. Full-corpus absence is still not established by retrieving a few passages.

## Real preparation and validation, 2026-10-26

A final three-report batch was prepared at
`evals/results/human_review_20261026T072426Z_36b41f3c43/batch.json`. It uses existing full-report
worksheets for local 002 (single-document), 005 (cross-document), and the bounded E3.4 negative 006,
from three saved executions. The generated template remains pending; validation correctly rejects
it with exit 1. The pending summary is
`evals/results/human_summary_20261026T072444Z_9d46113aa9/results.json` with adjacent `SUMMARY.md`.
It records three pending scopes, zero adjudications and no acceptance rate. Original packets were
not edited. Raw text, annotations and reviewer identifiers remain private/ignored.

The [content-free preparation record](../../evals/reports/e3-6-human-adjudication-2026-10-26.json)
contains hashes and counts. Earlier pending-only development smoke directories are not acceptance
results and are not pooled into the final batch. No real human annotation or adjudication has been
submitted; all completed examples in automated tests are synthetic fixtures, not benchmark labels.

Full regression: **418 passed, 6 skipped**. Changed-file Ruff lint/format passes. The 38 added tests
cover pending templates, actual CLI error handling, identity/hash/path drift, reconstructed input
tampering, quote validation, omissions/duplicates, error-tag/correction requirements, negative and
selected-scope rules, uncertain denominators, initial-versus-final separation, changed/cyclic prior
inputs, and explicitly adjudicated disagreement reporting. Real preparation and pending-summary
commands made zero model, judge, retrieval, database, Tavily or fetched-page calls.

Next: collect the first personal review/correction on this small batch, retain disputed or uncertain
labels, and use adjudicated development error counts to select one measured improvement. The tool
workflow is implemented; semantic report acceptance and the remaining Web/cross-source tasks are
still incomplete. No additional lexical-rule expansion or judge retries are required for this stage.
