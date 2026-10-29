# E4.17 — Saved live Evidence through ID selection, Writer and provisional review

## Fixed inputs and execution

E4.16 checked retrieval boundaries but did not test whether a selected passage could support
a written answer. This stage freezes four questions/parts in
[`source_transfer_v1.json`](../../evals/reports_acceptance/source_transfer_v1.json), using only
the final E4.16 live retrieval run. The loader verifies the published retrieval record,
run/dataset hashes, every saved retrieval and diagnostic artifact, query identity, delivered
chunk IDs, rerank status, and zero records on the excluded-source case. Raw passages remain in
ignored `evals/results`; no new recall, embedding, rerank, database query or Web search occurs.

The same frozen selector instruction and Writer contract used in E4.14 are reused. The selector
may choose at most two existing Evidence IDs per part; the backend copies the original chunk
text and gives Writer only these selected excerpts. Empty selections skip Writer. This is a
minimal candidate-answer pipeline, **not full DeepAgent report orchestration**.

Generation run: `source_transfer_20261029T074546Z_cc5156d709`. Source and inputs stayed
unchanged during the run. The configured model was **qwen-flash**, with five logical calls:
two each for the directory and JD-practice cases, one selector call for the PBC case, and zero
calls for the zero-evidence exclusion case. No provider retry or passing-result search occurred.

| Case | ID selection and Writer outcome | Provisional source review |
| --- | --- | --- |
| `toc_new_chapters` | One selected part; two candidate statements for chapters 03 and 04 | Both match the original cited TOC |
| `toc_polite_negative` | One selected part; ten candidate statements about JD practice; no directory listing | Ten statements have matching passages in their cited two chunks; the negative TOC constraint is respected in this candidate |
| `pbc_attested_title` | Six target-document chunks were delivered, but no quote selected for the requested *columns*; Writer skipped | Part remains unresolved; no claim that the full document lacks the answer |
| `excluded_named_source` | Zero evidence; selector and Writer skipped | Part remains unresolved; no forbidden document content is handed to Writer |

The PBC result separates **source resolution** from **answerable selected evidence**. Its
attested title and source scope passed E4.16, but the bounded six delivered chunks did not
yield a selected supporting quote for this new question. This is a concrete follow-up for
retrieval/selection diagnosis, not proof of document absence.

## AI review and provenance

A separate AI assistant reviewed each of the 12 candidate statements against its linked
original passage, and recorded two unresolved parts. The private
`AI_PRELIMINARY_REVIEW.json` includes literal source spans, verdicts and reasons. The
`source_transfer_review` validator requires one review per assertion or unresolved gap,
checks each quote is a contiguous substring of the original cited Evidence, verifies quote
links, run artifacts and case/input hashes, and rejects a human-review label. The final
validated tally is **12 provisional supported, 2 unresolved**. Quote validation is mechanical;
the semantic verdict is an AI preliminary judgment. Human review and human accuracy remain
pending/null, and the tally is **not a measured claim-support rate**.

The first offline review-validation attempt failed because a `Counter` was constructed from
dictionary values instead of expected keys. This harness defect was corrected and covered by
portable tests. No retrieval or generator call was repeated. The original reviewer source is
archived privately and its hash reconstructs the generation manifest. The
[public record](../../evals/reports/e4-17-source-transfer-2026-10-29.json) contains only
case IDs, statuses, counts, hashes and cost; it does not publish passages or model responses.

## Reproduction and limits

```powershell
# Offline plan; requires the ignored E4.16 saved retrieval artifacts.
.venv\Scripts\python.exe -m evals.reports_acceptance.source_transfer

# Explicit bounded selector/Writer execution on those same saved artifacts.
.venv\Scripts\python.exe -m evals.reports_acceptance.source_transfer --execute

# Offline validation of an AI preliminary review file; no model calls.
.venv\Scripts\python.exe -m evals.reports_acceptance.source_transfer_review `
  evals/results/source_transfer_20261029T074546Z_cc5156d709 `
  evals/results/source_transfer_20261029T074546Z_cc5156d709/AI_PRELIMINARY_REVIEW.json
```

Full regression: **664 passed, 6 skipped**. Focused portable fixtures check hash and question
binding, exclusion refusal, full assertion coverage, literal quote membership and rejection of
fabricated human reviewer status. Ruff lint/format and `git diff --check` pass. The four cases
reuse an exposed corpus and an already inspected retrieval run; they are development checks,
not an independent holdout. The experimental retrieval route remains off by default. Next
inspect why the PBC column question had no selected supporting quote, with a small fixed
candidate/retention diagnostic before changing search or promoting this workflow.
