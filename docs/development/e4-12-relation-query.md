# E4.12 — Cross query/title separation with passage context

## Fixed experiment

E4.11 identified rank and delivery losses rather than missing candidate retrieval. This stage
tests one deterministic query ablation on the same archived candidate pools. Replace each
explicit `《source title》` in the question with a stable `文档1`, `文档2`, etc. Repeated titles
share a placeholder. All other question text stays byte-for-byte unchanged: structural requests,
dates outside titles, negation and insufficient-evidence constraints are preserved. No reference
anchor, answer keypoint, task-part label, inferred alias or new structural cue is inserted.

This is a narrow ablation of explicit source names, not semantic query parsing. Titles may also
carry domain meaning, and this experiment deliberately does not disentangle that confound.
Unquoted shorthand names in the two cross-document questions remain unchanged. No new source
filter is introduced: pool membership, source scope and order remain frozen. Removing title
information can therefore affect source relevance as well as requested-relation matching.

Cross the original/relation query with the existing raw/source-context passage formats, producing
four conditions per case. Original-query controls are freshly inferred in both formats, with
delivery IDs checked against the hash-bound E4.10 results. A control mismatch invalidates a case.
For the three development questions without `《》`, relation conditions reuse their identical
fresh controls and are explicitly marked as reused; no redundant model calls are made.

All conditions use the frozen local reranker/model artifacts, threshold 1, retained top eight,
delivered maximum six and 10,000 characters. Evidence and scoring use raw source content, never
the prefixed model input. The model sees only question text and candidate text; evaluation labels
are used after ranking. No production default, dataset label, candidate or budget changes.

## Reproduction

```powershell
# Verify private frozen inputs and write query plan; no inference or services.
.venv\Scripts\python.exe -m evals.rag.run_relation_query

# Two diagnostics, eight local rerank calls.
.venv\Scripts\python.exe -m evals.rag.run_relation_query --diagnostic --execute

# Twenty development cases, 74 local rerank calls.
.venv\Scripts\python.exe -m evals.rag.run_relation_query --execute
```

Private archived pools, corpus and E4.10 controls are required. Query plans, raw candidate text,
full rankings and delivered passages stay ignored under `evals/results/`. The public record
contains hashes, metrics, counts and finite-reference ranks, not source passages. Source/input
and reranker-artifact hashes are verified before/after runs. Availability fallback or unexpected
exceptions remain invalid without retry; an exception with unknown progress reports a null call
count rather than inventing an exact count. Test-split questions are not loaded.

## Diagnostic outcome

| Reference / condition | Rank | Score | Delivered |
| --- | ---: | ---: | --- |
| TOC, original + raw | 29 | 0.473 | No |
| TOC, original + context | 28 | 4.334 | No |
| TOC, relation + raw | 3 | -8.795 | No |
| TOC, relation + context | 4 | -5.622 | No |
| Survey, original + raw | 3 | 5.984 | Yes |
| Survey, original + context | 1 | 8.400 | Yes |
| Survey, relation + raw | 1 | 1.658 | Yes |
| Survey, relation + context | 1 | 1.811 | Yes |

The TOC's relative rank improves but both relation-query variants return zero hits under the
unchanged threshold. It is not recovered. The survey stays delivered, with only one hit in each
relation-query condition. Scores are not calibrated probabilities across query/input formats;
better relative rank does not establish usable retrieval. No report is regenerated or repaired.

## Development outcome

| Query + passage format | Finite-unit Recall@6 | MRR@6 | All finite units found |
| --- | ---: | ---: | ---: |
| Original + raw | 0.702 | 0.480 | 12/19 |
| Original + source context | 0.754 | 0.592 | 12/19 |
| Relation + raw | 0.421 | 0.326 | 7/19 |
| Relation + source context | 0.474 | 0.390 | 7/19 |

The 19 answerable cases form the denominators. The relation ablation loses mean coverage and
complete-unit coverage in both passage formats. The customer-service reference is not recovered;
the original raw condition had covered it, but neither relation condition does. Cross-document
applications remain unchanged because that question has no explicit `《》` title and the relation
conditions are deliberately identical to the fresh controls. Thus no cross-document repair is
claimed. The TOC diagnostic also remains undelivered despite improved relative rank.

Compared with each format's original-query control, raw passages improve on `006` but regress
on `007`, `009`, `011`, `012`, `015`, `016` and `017`. Contextual passages have no finite-coverage
improvement and regress on `011`, `012`, `013`, `015`, `016` and `017`. All IDs share the
`rag_local_zh_` prefix. Missing units first lost at the score threshold rise from 4 to 16 for raw
passages and from 1 to 14 for contextual passages. This identifies a score/threshold distribution
shift under the fixed configuration; it does not prove every possible title-separation design
would fail. No threshold search is performed on this exposed split.

The no-answer question returns zero hits in all four conditions. This checks the saved negative
control; no generator abstention or semantic precision is measured. All 22 pairs of historical
delivery controls reproduce (44 policy-level comparisons), and every case is valid. Source,
inputs and frozen model artifacts remain unchanged throughout both runs.

Diagnostic run: `relation_query_diagnostic_20261029T024156Z_beb94f0605`.
Development run: `relation_query_dev_20261029T024436Z_c83d67c7d2`.
Total: **82 local rerank calls, zero retrieval/embedding/generator/Web calls**. The three no-op
development cases save six redundant calls. See the
[content-free paired record](../../evals/reports/e4-12-relation-query-2026-10-29.json).

## Verification

Twelve focused tests cover deterministic title placeholders, repeated titles, preserved dates,
structural and negative constraints, no alias guessing, shared inputs, no-op reuse, historical
control mismatch, fallback accounting, offline planning, corrupt input hashes and budget checks.
Full regression: **596 passed, 6 skipped**. Ruff lint/format and `git diff --check` pass.

The questions are exposed development cases on previously exposed sources. Finite evidence
labels are provisional and nonexhaustive; anchor absence does not prove semantic irrelevance.
No generator, human answer adjudication or holdout accuracy is measured. Human accuracy stays null.

## Decision and next implementation boundary

Keep this as an evaluation-only ablation. Blanket title replacement loses supported development
cases and does not recover the diagnostic TOC. Do not retune the global threshold to rescue this
particular query format, and do not promote improved relative ranks as successful delivery.

The next implementation should represent source identity explicitly, before evaluating passage
support: resolve exact user-specified document names against real indexed metadata, preserve
ambiguous/unresolved names rather than guessing aliases, and retain the original question for
fallback. For structural requests, inspect genuinely indexed structural passages instead of
assuming a thematic body chunk answers chapter/TOC questions. Keep all returned Evidence as raw
source material with unchanged IDs, and measure any document/structure selection on the broader
development and insufficient-evidence cases before connecting it to production. This is a new
implementation boundary, not a claim that source filtering or structural retrieval has already
been tested or solved here.
