# M2.1 Claim-to-Evidence Validation

M2.1 turns the compression-to-writer handoff from parallel text lists into a backend-validated
Claim-to-Evidence relationship.

## Protocol

The model proposes `ClaimDraft` objects with four fields:

```text
text
evidence_ids[]
kind: fact | inference
limitations[]
```

The backend compares every proposed `evidence_id` with the IDs actually collected in the current
run. It then produces one of two outcomes:

- `ValidatedClaim`: all evidence IDs exist; an inference also states at least one limitation;
- `RejectedClaim`: evidence is missing, an ID is unknown, or an inference has no limitation.

Accepted claims receive a deterministic `clm1_<digest>` identifier derived from normalized claim
content, claim kind, evidence IDs, and limitations. Reordering evidence IDs does not change the
claim ID. Rejected drafts remain visible as gaps but are not passed to the writer as report facts.

## Workflow boundary

The compression model still performs semantic synthesis, but the backend renders its structured
output into a `Validated Claim Package`. The final writer receives that package instead of separate
`core_findings` and `citations` lists.

The writer must cite exact bracketed IDs such as `[ev1_sql_...]`. After writing, the backend checks
that:

1. every cited evidence ID belongs to an accepted claim;
2. a report backed by collected evidence does not omit all evidence citations.

If either check fails, the generated report is not used as the deliverable. The backend returns the
validated claim package as a partial result, marks the run degraded, records
`final_report_citation_validation_failed`, and persists only the validated fallback when the user
requested a file.

## Trace schema v3

The research trace now records counts only; it does not duplicate claim or evidence content:

- accepted and rejected claim counts;
- accepted claims by kind;
- evidence IDs used by accepted claims;
- unknown evidence IDs proposed by rejected claims;
- final-report citation validity and cited-evidence count;
- collected evidence never used by an accepted claim.

This makes evidence waste measurable without putting private source text into telemetry.

## Current boundary

M2.1 validates the internal sources registered in M1.2: Fee Engine, SQL, and local documents. Web
search is still a discovery-oriented sub-agent and does not yet create `EvidenceRecord` objects.
Web material must therefore remain an uncertainty or gap in M2.1; promoting fetched web passages to
stable Web Evidence is the next milestone.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_claim_validation.py `
  tests/test_research_runtime.py tests/test_research_workflow.py -q
```

The tests cover deterministic claim IDs, accepted and rejected claims, unknown evidence, inference
limitations, writer citation checks, validated fallback behavior, and trace metrics.

With the local stack running, the opt-in infrastructure suite also binds a live MySQL
`EvidenceRecord` to a validated claim and passes it through the final citation gate:

```powershell
$env:RUN_EVIDENCE_INFRASTRUCTURE_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest `
  tests/integration/test_evidence_infrastructure.py::test_live_sql_evidence_can_back_a_validated_claim_and_report -v
```
