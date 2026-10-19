# E3.1b: canonical Claim references and exact-input offline replay

E3.1/E3.1a exposed a concrete formatting failure: structured `evidence_ids` arrays sometimes
contained `[ev1_...]` rather than the bare ID. All claims in cases 001/002 could then be rejected
even though their source records existed. This stage repairs the syntax boundary, not entailment.

## Narrow normalization policy

`validate_claims` now defaults to `known_single_bracket_v1`. After the existing whitespace trim,
a reference is unwrapped only if all of the following hold:

- The whole value is one pair of square brackets around one complete production stable ID.
- The source prefix is `local_document`, `sql`, `web`, or `fee_engine`, followed by 24 lowercase
  hexadecimal characters. No case folding, fuzzy matching, substring extraction, or typo repair.
- The enclosed bare ID is already in the exact eligible-ID allowlist for this validation batch.

Unknown wrappers remain unchanged and rejected. Markdown links, backticks, nested brackets,
extra words, multiple references in one entry, uppercase variants, internal padding, and
malformed hashes are not repaired. Bare allowlisted references keep their existing behavior.
Missing references and inference-without-limitations remain rejected. The source allowlist is
never normalized or expanded. Rejected drafts retain their original reference strings.

Accepted references are deduplicated in input order before computing the Claim ID. Equivalent
bare/wrapped drafts therefore produce the same stable Claim identity and downstream canonical
citations, without mutating input drafts or changing Claim text, kind, or limitations.
`normalized_evidence_references` counts repaired entries, including entries in claims rejected
for another issue; it is not a rescued-claim or correctness counter.

`normalize_known_wrappers=False` reproduces the former exact-string policy for offline comparison.
It is an internal stricter validator option, not a user-facing relaxation or Agent-controlled switch.
Ordinary report citation parsing is unchanged.

## Capturing and replaying real inputs

Only runs already opting into `export_evaluation_evidence=True` retain `claim_validation_batches`
inside their private Evidence snapshot. Each batch stores original typed Claim drafts, the eligible
ID list used at that moment, the policy name, and recorded accepted/rejected/normalization counts.
The ordinary trace adds only a normalization counter, not these structured input bodies. Default
application runs do not retain these extra batches. Existing audit previews are unchanged;
this does not assert that historical audit logs contain no Claim text. Keep snapshots private.

```powershell
# Two targeted development tasks; uses configured LLM but zero web queries/pages.
.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute --case-id report_local_001 --case-id report_local_002
# Same saved drafts and eligible IDs, two reference policies; no LLM or retrieval.
.venv\Scripts\python.exe -m evals.reports_acceptance.replay_claims --report-results evals/results/<run_id>/results.json
```

Replay checks snapshot hashes, confines review directories to local evaluation results, verifies
that every declared eligible ID appears in the saved records, and reconciles current replay counts
with the recorded live counts. It preserves the execution manifest and adds a separate replay
manifest and input hash. Missing compression batches are explicit `no_validation_batches`, not
successful zero-error validation. Snapshots lacking original structured inputs are rejected:
old rejected-claim Markdown loses information such as kind/limitations and cannot be promoted
into a trustworthy full-Claim replay. Historical report artifacts remain untouched.

## Interpretation and remaining work

The application still calls these structurally linked objects “Validated claims”; neither the
old nor new ID rule proves that a statement follows from its passage. A wrong inventory claim
with an eligible ID can pass this mechanical validation. Tests make that limitation explicit.
Appropriate abstention, claim entailment, and report acceptance remain pending semantic review.
This stage does not fix E3.1a's negative-case hallucination, cross-document coverage, built-in tool
churn, or phase/call budgets, and does not modify retrieval settings or the frozen E2 query tests.

The two targeted fresh reports are a development check, not a rerun of the entire six-case suite.
Their generation can vary stochastically from older reports; any exact-policy comparison applies
only to identical saved structured inputs in the offline replay, not to report answer accuracy.

## Verification and real targeted results, 2026-10-19

Full regression: **273 passed, 6 skipped**; all changed Python files pass Ruff lint and format
checks. The 28 added tests cover all four production source prefixes, exact eligibility, malformed
wrappers, unchanged input drafts, stable identity/deduplication, unknown/missing/inference gates,
default-off private input capture, no Claim/source bodies in ordinary trace fields, replay hash/
path/eligibility/live-count validation, and explicitly skipped missing-compression batches.
A deliberately unsupported inventory sentence also passes structural validation when its ID is
eligible: that test documents the absence of semantic approval rather than claiming it is safe.

The two real tasks ran under `report_acceptance_20261019T120234Z_bf87f1e46f` with the same
`local_v1.json` questions and `qwen-flash` configuration, selecting only 001/002. Source, dataset,
and corpus checks passed. Zero Tavily queries and fetched pages were used. Private snapshots
contain complete original structured inputs for one validation batch per task.

| Task | Execution | Seconds | Normalized references | Structurally accepted/rejected | Final citation validation |
| --- | --- | ---: | ---: | --- | --- |
| 001 scenarios | degraded | 110.391 | 5 | 4 / 0 | valid |
| 002 advantages | completed | 83.844 | 9 | 5 / 0 | valid |

001 still reached `llm_call_limit`; removal of the formatting rejection did not erase that failure.
Both tasks cite the finite reference unit, but this remains mechanical coverage, not entailment.
The report runner exited 1 because a task degraded. No full six-task pass-rate update is asserted.

Offline run `claim_replay_20261019T120630Z_c53c467ed6` compared the **same saved drafts and eligible
IDs**, making no model or retrieval calls:

| Task | Former exact rule accepted/rejected | Canonical rule accepted/rejected | Former unknown-reference issues |
| --- | --- | --- | ---: |
| 001 | 0 / 4 | 4 / 0 | 5 |
| 002 | 0 / 5 | 5 / 0 | 9 |

Thus all nine fresh drafts would have been rejected under the former format rule solely because
of fourteen wrapped eligible references. The canonical replay matches recorded live counts.
This isolates the formatting effect on these drafts; it does **not** regrade old reports, measure
answer accuracy, or establish that all nine statements are supported by their passages.
Historical runs lacked typed inputs and are not silently reconstructed or rescored.

Content-free [execution/replay record](../../evals/reports/e3-1b-claim-reference-replay-2026-10-19.json)
retains execution and replay manifests, file hashes, counters, and the explicit unexecuted 003–006
subset. Claim/source bodies remain only in ignored local artifacts. Human semantic review remains
pending, including the E3.1a negative-case hallucination. The next work is evidence-support and
appropriate-abstention acceptance on saved passages, not relaxed ID checks or a fresh broad crawl.
