# E3.3: local source filenames in the generation and delivery boundary

E3.2 showed that a structurally valid citation could accompany an invented document inventory.
The configured model judge was not reliable enough for automatic approval. This stage therefore
adds a narrow deterministic production boundary rather than another judging prompt.

## Production changes

- Local Evidence ledger entries now include their actual `metadata.filename` and explicitly state
  that the content is a retrieved excerpt, not a full-document inventory audit.
- The Writer receives a dedicated catalog of filenames and Evidence IDs from registered local
  records. General runtime/tool instructions remain excluded from Writer prompts. A workflow test
  verifies that the dedicated catalog really reaches the Writer, not an unused instruction field.
- For local-only requests, inspect explicit `《name.ext》` mentions before final citation validation
  and also inspect any compressed-package fallback after a citation failure. Accepted extensions
  are pdf/doc/docx/xls/xlsx/txt/md, with bounded names up to 240 characters.
- Names must match a filename on an actually registered local Evidence record. Normalization is
  outer whitespace trim, Unicode NFC, and case folding only. Internal whitespace, dates, page counts,
  paths and aliases are not erased or guessed. Web/SQL records cannot expand the local-name catalog.
- An unverified name marks the run degraded with `unverified_local_source_filename`. Withhold the
  whole candidate and return a deterministic source-verification notice. Do not copy Claims,
  uncertainties, rejected drafts, or the compressed fallback into that notice: they can contain the
  same invented names. Display only the real registered-source labels in an escaped JSON block.
- Check both ordinary and run-budget fallback finalization. The final result and persisted report
  use the guarded body; source-withheld artifacts have an explicit artifact status. Existing phase
  and audit previews remain unverified diagnostic output, not final deliverables.

Trace records only candidate kind, filename counts and withholding status. Opted-in evaluation
snapshots additionally retain original candidates and private source checks so a blocked output can
be inspected without republishing it. Ordinary runs do not retain these new extra candidate bodies.
The report evaluator preserves the independent source-check state alongside citation outcomes.

## Important interpretation boundaries

This validates **filename identity**, not entailment. A known filename may still be paired with an
unsupported statement, the wrong citation, an incorrect date, or an exaggerated claim of having
read the entire document. A registered record is not proof that all its content supports a Claim.
The Writer instructions discourage exhaustive-audit statements; this stage does not semantically
prove that it obeyed them.

Only actual retrieved local records establish this catalog; it is not the whole indexed corpus,
not a filesystem/attachment inventory, and not an authorization policy. Missing metadata fails
closed for named-file references. A real but not retrieved document, shortened title with a file
extension, quoted question/example, or output filename can be withheld conservatively. Short
titles without extensions, bare/backtick filenames, other file types and longer names are outside
this narrow matcher. There is no fuzzy repair and no assertion that an unverified file is fictional
or absent. A blocked answer is an unresolved report, not automatically an appropriate refusal.

The backend notice contains no factual-answer citations. Its technical citation check can be valid
with `citations_required=False`, but source checks record withholding and execution is degraded.
The separate answerable-case evaluator can still flag missing answer citations. Neither result is
a semantic pass rate. Preserve those dimensions separately instead of interpreting an empty notice
as a citation-supported answer.

## Offline policy replay

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.replay_sources --report-results evals/results/<saved_run>/results.json --case-id report_local_006
```

Replay requires a finalized, unchanged frozen `local_v1` execution, validates case IDs and resolved
artifact paths/hashes, and applies the same source-filename guard to saved text and record metadata.
It makes no model, database, vector, rerank, or web calls. It writes a new private delivered body and
source check without changing old reports. Results are `withheld` or `not_flagged`, never semantic
`passed`. The replay isolates this policy, not the complete new generation workflow.

## Verification

Focused source/provenance contracts: 22 passed. Full regression: **329 passed, 6 skipped**.
Changed-file Ruff lint/format checks pass. Tests cover production filename extensions, actual local
metadata, NFC/case identity without fuzzy matching, nonlocal compatibility, private/default-off
candidate capture, contaminated citation fallbacks, unchanged known-source text, real Writer
handoff, guarded artifact persistence, and offline replay path/hash/case validation.

The fixed historical negative report from E3.1a is withheld in offline replay: five unverified
filename spellings become zero in the delivered boundary notice. The E3.1b 002 control has no
unverified matches and remains byte-for-byte unchanged. This is a bounded filename-policy check,
not a measured reduction in all hallucinations or an improvement in answer accuracy. Historical
execution records are not overwritten or rescored as complete current-workflow runs.

## Real two-task check, 2026-10-24

Run `report_acceptance_20261024T135024Z_ec2a7ef2f7` selected only 002/006 from the same frozen
development suite. Both used actual local retrieval and the configured `qwen-flash` generator;
no judge, web queries, or fetched pages were used. Source, dataset and corpus drift checks passed.

| Task | Execution | Seconds | Local records | Source checks on final candidate | Remaining outcome |
| --- | --- | ---: | ---: | --- | --- |
| 002 advantages | degraded | 184.781 | 10 | no explicit filename matches; not withheld | timeout; finite reference unit not cited |
| 006 no-answer | degraded | 60.844 | 0 | no explicit filename matches; not withheld | call limit; earlier no-evidence boundary returned a bounded non-match notice |

No newly generated final candidate exercised filename withholding in this run. That branch is
demonstrated by the preserved historical negative replay and integration tests, not claimed as
an observed fresh interception. The negative task did exercise the earlier deterministic
zero-record boundary with real retrieval: its result explains `no_evidence`, does not claim corpus
absence, and does not list invented documents. This is not proof of improved semantic refusal
accuracy. Both executions remain degraded; CLI exit status is 1 and human acceptance is pending.
The positive task still has a coverage gap despite valid citation IDs. No full six-task score,
latency gain, or reduction in all hallucinations is asserted.

The [content-free record](../../evals/reports/e3-3-source-provenance-2026-10-24.json) preserves the
separate offline policy replays, generation manifests, per-case checks and file hashes. Raw rejected
candidates, real document labels and report bodies remain only in ignored local artifacts.

## Next bounded work

Stop broad model judging until its output contract is reliable or human labels are available.
Use the saved support-review packets for actual semantic annotations. Next generation work should
target one frequent local research failure, such as unnecessary built-in tool churn, with a fixed
development comparison. Keep source identity, evidence coverage, execution completion and human
correctness separate. Cross-document coverage and the planned web/cross-source E3 cases remain
unfinished; this stage does not close semantic acceptance.
