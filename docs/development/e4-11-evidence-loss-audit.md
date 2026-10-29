# E4.11 — Attribute finite evidence loss before changing retrieval

E4.10 improved mean retrieval metrics but lost two previously covered development units.
This stage adds a reproducible offline audit rather than another ranking heuristic. Production
defaults, questions, finite labels, candidate membership, model scores and budgets stay unchanged.

## Reproduction and controls

```powershell
.venv\Scripts\python.exe -m evals.rag.audit_evidence_loss
# Optional content-free public record:
.venv\Scripts\python.exe -m evals.rag.audit_evidence_loss --output evals/reports/e4-11-evidence-loss-audit-2026-10-29.json
```

Requires the private E4.8/E4.9 candidate/corpus snapshots and E4.10 paired results. Hashes are
checked against committed records, and frozen development labels are validated by the existing
loader. The tool rejects changed case membership, candidate sets, malformed/nonfinite rankings,
foreign document bindings, invalid delivery order and nonreproducible saved development metrics.
It checks inputs again before writing and refuses to overwrite an input. Missing private files
fail explicitly; tests use synthetic fixtures and require no archived source text.

For each finite evidence unit, **all alternative locations** are considered. The first gate at
which none survives is reported: corpus reference match, candidate pool, threshold (1), retained
top eight, delivered hit budget (six), or delivered text (possible truncation). Threshold precedes
top-eight attribution; multiple later gates can also fail. This is loss accounting, not a claim
that bypassing the first failed gate alone would recover the evidence.

Public output contains IDs, ranks, scores, counts, input hashes and the audit source manifest;
it excludes passages, questions and anchor text. Original source/reranker provenance remains in
E4.10 and is distinct from this new audit's manifest. No retrieval, reranking, embedding, generator
or Web calls occur. Test questions are not loaded.

## Results

All 20 development cases and both earlier diagnostic pools were audited; the 19 answerable
development cases contain 30 finite evidence units. These **unit counts** are not the macro
Recall@6 from E4.10 and are not answer accuracy.

| First loss / successful delivery | Raw | Source context |
| --- | ---: | ---: |
| Candidate pool | 3 | 3 |
| Score threshold | 4 | 1 |
| Retained top eight | 1 | 2 |
| Delivery budget | 3 | 3 |
| Delivered with finite anchor | 19 | 21 |

No unit loses all corpus reference matches or all anchors through delivered-text truncation.
The negative case has no positive evidence units and still delivers zero hits in both variants;
it contributes no positive-unit denominator.

| Regression / diagnostic | Raw reference rank | Source-context rank | Source-context first loss |
| --- | ---: | ---: | --- |
| `rag_local_zh_007`, service | 4 (alternative 18) | 11 (alternative 12) | Retained top eight |
| `rag_local_zh_019`, applications | 6 | 8 | Delivery budget |
| TOC diagnostic | 29 | 28 | Retained top eight |
| Survey diagnostic | 3 | 1 | Delivered |

The customer-service reference score rises from 6.011 to 7.608 while its rank worsens. All six
delivered hits are from the reference document but none matches the finite service anchors.
For cross-document applications, the matching score rises from 4.174 to 5.121, yet rank eight
loses to the six-hit cap. Saved budget telemetry confirms hit truncation and **no character
truncation** for both regression cases (3,792 / 4,278 characters, below 10,000).

The TOC's raw score is below threshold; its contextual score clears threshold but rank 28 still
fails retention. Six delivered chunks come from the correct document in both variants. The survey
control remains delivered. Source identification alone therefore does not establish that the
requested structural or factual relation is present in delivered evidence. Lowering the threshold
cannot repair any of these three source-context losses.

Finite anchors are provisional, nonexhaustive annotations. A delivered chunk without an anchor
may contain valid alternative support; this audit neither relabels it irrelevant nor establishes
full-document absence. Human accuracy remains null. No report is regenerated or marked repaired.

## Verification and next experiment

Sixteen focused tests cover every gate, alternative-location survival, source-only counts,
malformed rankings, document identity, paired pool/metric binding and corrupt saved-result hashes.
Full regression: **584 passed, 6 skipped**. Ruff lint/format and `git diff --check` pass.

The next bounded experiment should separate the requested relation from source identity in the
reranker **query**, using the same frozen pools and unchanged delivery budget. Preserve structural
terms such as chapter/TOC, derive query text only from the user question, and keep reference anchors
strictly evaluator-only. Compare raw/context controls across all 20 development cases plus the
two diagnostics; preserve no-answer and regression cases. No production switch should follow
from the mean alone. Do not expand the hit budget merely to recover known labels, inject target
chunks, or infer headings missing from indexed metadata. If this query ablation still fails,
record the failure before choosing a more substantial structure-aware retrieval design.

See the [content-free audit record](../../evals/reports/e4-11-evidence-loss-audit-2026-10-29.json).
