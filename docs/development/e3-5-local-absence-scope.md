# E3.5: a bounded local-absence delivery check

The E3.4 bounded negative retrieved three unrelated snippets and still asserted that all
accessible documents lacked the requested subject. Valid IDs and registered filenames did not
prevent that unsupported scope expansion. This stage adds a small delivery defense and an offline
regression experiment, not another generation/judge retry or a claim of semantic acceptance.

## Delivery behavior

For requests matched by the existing local-only detector, `local_absence_wording_v1` checks the
Writer candidate after filename provenance and before citation validation. It recognizes explicit
Chinese/English corpus or whole-document scope directly followed by selected absence predicates.
Basic Markdown emphasis is ignored. A later caveat does not excuse a matched assertion; narrow
immediate epistemic prefixes such as “无法确认” are exempt. Ordinary retrieved-excerpt gaps,
positive findings and the covered question forms remain deliverable under this check.

A match withholds the entire generated body, marks the run degraded with
`unverified_local_absence_scope`, and returns a deterministic explanation that the retrieved
excerpts cannot establish whether the requested content exists. No rejected conclusion, Claim,
filename inventory or fallback body is copied into that notice. Citation-failure fallbacks and
terminal fallback delivery use the same boundary. Artifact states distinguish
`scope_withheld` / `scope_withheld_persisted`. A notice can have valid citation syntax while the
run remains degraded: it is not an accepted factual answer or a verified appropriate refusal.

Both the default researcher and opt-in indexed-local researcher pass through this local delivery
check. Mixed-source requests keep existing behavior. The indexed-local experiment remains off by
default. No retrieval, model, phase or query budget has been increased. Compression and Writer
instructions now explicitly prohibit inferring full-corpus absence from retrieved snippets.

Ordinary traces retain only policy, candidate kind, match counts and withheld flags in
`local_scope_checks`. The original candidate and matched strings are saved only in the private
Evidence snapshot under the existing explicit evaluation-export flag. Earlier audit previews are
not redesigned by this change.

## Offline experiment, 2026-10-26

The saved-report replay CLI now supports a separate `--policy absence_scope` mode. Its default
remains filename-only; the two policies are not silently combined for historical comparisons.
Both modes require finalized, input-stable local_v1 results, known/unique executed case IDs,
the pinned dataset hash, safe artifact paths and exact report/Evidence hashes. Each replay writes
new private outputs, preserves originals, and checks source/input fingerprints for drift. It does
not reconnect to PostgreSQL/Qdrant, regenerate reports, or invoke a judge/search provider.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.replay_sources --policy absence_scope --report-results evals/results/report_acceptance_20261024T142538Z_6a32b9cb59/results.json
```

| Saved execution | Reports | Matched bodies | Explicit matches before → delivered | Unchanged bodies |
| --- | ---: | ---: | ---: | ---: |
| E3.4 bounded indexed-local pilot, 002/006 | 2 | 1 (006) | 2 → 0 | 1 (002) |
| E3.1a six-task execution | 6 | 0 | 0 → 0 | 6 |

These are eight saved reports, including repeated task IDs, not eight independent questions.
The E3.4 negative is withheld rather than rewritten into a claimed supported answer. The old
six-task negative is a **known miss**: its assertion of systematic checking and “not found” wording
is outside this narrow grammar. It also contains invented filenames covered by the independent
E3.3 policy; absence-only replay deliberately does not claim that filename detection as its gain.

Replay IDs are `scope_replay_20261026T071035Z_a8ee4dda5c` and
`scope_replay_20261026T071043Z_d32dde8f71`. The
[content-free record](../../evals/reports/e3-5-local-absence-scope-2026-10-26.json) preserves input,
output and source hashes plus counters. Full candidates and private check snapshots remain in
ignored `evals/results/`. Model/judge/retrieval/Tavily calls for this experiment: **zero**.

## Limits and verification

This is a conservative lexical heuristic. Paraphrases, short titles, cross-sentence reasoning,
inventories without selected absence predicates, and other languages can escape it. Quoted
assertions, hypotheticals or unfamiliar uncertainty wording can be withheld conservatively.
Recognized wording can be withheld even when a document explicitly supports a negative fact:
there is currently no backend full-text/corpus-coverage certificate to establish that exception.
The local-only routing heuristic itself is incomplete. Non-matches are **unreviewed**, not supported.
This check does not validate evidence entailment, execute a full-text audit, establish recall, or
make any promise that all unsupported corpus conclusions are blocked.

Full regression: **380 passed, 6 skipped**; changed-file Ruff lint/format passes. Added coverage
checks absence wording with valid citation IDs, later caveats, uncertainty/question forms,
positive-report preservation, no fallback leakage, trace privacy, offline replay preservation,
and actual workflow artifact persistence. The prior filename-only replay tests remain passing.

No fresh model generation or paid evaluation was run. The prompt changes have no measured
generation-quality effect in this stage. Human support annotations are still pending. Next work
should consolidate the existing saved-report review material into an explicit adjudication/result
workflow, then use reviewed development errors to choose one measured improvement. Do not expand
these expressions indefinitely or promote the indexed-local route based on timing or this replay.
The remaining Web/cross-source acceptance tasks are still incomplete.
