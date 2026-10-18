# E2 RAG suite v2: annotations, freezing, and comparable results

## Why the labels changed

Reviewing the first pilot's actual Top-5 passages found label false negatives. For `001`, BGE put the
whitepaper's dedicated typical-scenarios page first, but v1 accepted only the earlier definition
page. For `012`, the policy report repeated its monetary stance with slightly different wording.
Those passages answered the question but missed a single literal anchor. The first pilot remains
unchanged as a historical development result; its low C anchor score must not be presented as proof
that BGE harms relevance.

Suite v2 expands evidence alternatives and makes keypoints explicit. Regrading the **same stored
Top-5 passages** gives the following comparison; no retrieval or model execution was repeated:

| Mode | Original v1 Recall@5 | v2 Recall@5 on identical passages | Original MRR@5 | v2 MRR@5 |
| --- | ---: | ---: | ---: | ---: |
| A vector | 0.25 | 0.25 | 0.0625 | 0.0833 |
| B hybrid | 1.00 | 1.00 | 0.7083 | 0.7083 |
| C hybrid + BGE | 0.25 | 1.00 | 0.2500 | 0.8125 |

The denominator is four answerable questions; the no-answer question is separate. This is an
annotation correction, not an algorithm improvement. Original rankings, timing, model status, and
candidate pools are retained in the offline rescoring record.

## Dataset and execution contract

- All twenty existing development questions now have evidence-level v2 labels: nineteen answerable
  and one no-answer question, including two multi-document questions.
- Ten new questions form a frozen query test split: eight answerable and two no-answer cases,
  including two multi-document tasks. They use natural questions instead of exact document titles.
- Evidence units contain reference keypoints, document hashes, normalized-anchor hashes, alternative
  passages, and parser-derived page hints. Every alternative is checked against indexed source text,
  not only the first matching alternative.
- No-answer literal checks are sanity checks, not semantic refusal evaluation. The second test
  negative asks for unavailable merchant/day-level future transaction data rather than another
  invented topic alone.
- The lock pins canonical development/test JSON content, selected knowledge bases, indexed-corpus
  fingerprint, retrieval configuration, experiment modes, and local model artifact hashes. Canonical
  JSON hashes avoid Windows/Linux newline differences. Test execution requires a lock and validates
  both dataset files before inference.
- A manifest is captured before model execution. Application/evaluation source or dataset changes
  during the run invalidate results. A per-question journal preserves partial work on interruption.
- Paired summaries use the same valid case IDs for A/B/C and explicitly list exclusions, so a
  failed C case cannot silently produce a different comparison denominator.
- `rescore.py` grades saved passage text under revised annotations and rejects changed questions or
  missing original cases. It preserves the execution provenance and adds a separate rescoring
  manifest.

The lock was created before executing either new split. Retrieval parameters and application
ranking logic were not tuned after inspecting new development or test results. The application
retriever and model configuration are unchanged from the first pilot.

## Human review and scope

All labels remain `source_verified_by_agent_pending_human_review`; the review worksheet has no
prechecked approvals. A frozen file does not imply human validation. The test split contains new
questions over the same known five-document corpus, not held-out documents or independently
authored expert labels. Reference keypoints are a finite rubric for passage retrieval, not an
exhaustive summary of each source. Alternative passages may still be incomplete.

The legacy index does not record its original embedding provenance. This limitation persists and
needs a separately controlled reindex before formal model comparisons. No independent answer
accuracy or claim-entailment result is asserted here. E3 report acceptance and E4 one measured
development-driven change remain subsequent milestones.

## Commands

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m evals.rag.run_retrieval --dataset evals/rag/suites/v2/development.jsonl --suite-lock evals/rag/suites/v2/suite.lock.json --knowledge-base 电商行业 --knowledge-base 金融行业
.venv\Scripts\python.exe -m evals.rag.run_retrieval --dataset evals/rag/suites/v2/test.jsonl --split test --suite-lock evals/rag/suites/v2/suite.lock.json --knowledge-base 电商行业 --knowledge-base 金融行业
.venv\Scripts\python.exe -m evals.rag.rescore --results evals/results/<original_run_id>/results.json --dataset evals/rag/suites/v2/development.jsonl
```

Raw passages and partial journals remain under ignored `evals/results/<run_id>/`. Content-free
records and real split metrics are included below. No Tavily or generative LLM calls
are required by these experiments.

## Real frozen-suite results, 2026-10-18

The development run is `rag_20261018T104648Z_c989caa149`; the first test execution is
`rag_20261018T105142Z_482e811875`. All 60 development and 30 test configurations completed with
`ok` status. Every C row ran BGE inference; paired comparisons excluded no cases. Both runs share
the same source fingerprint, frozen lock, five-document/305-chunk corpus, and model artifacts.

| Split | Mode | Valid/scheduled | Answerable denominator | Recall@5 | MRR@5 | All evidence | Median ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | A vector | 20/20 | 19 | 0.1579 | 0.0588 | 0.1053 | 121.232 |
| Development | B hybrid | 20/20 | 19 | 0.5000 | 0.2561 | 0.4737 | 874.986 |
| Development | C reranked | 20/20 | 19 | 0.6754 | 0.4798 | 0.5789 | 13723.347 |
| Test | A vector | 10/10 | 8 | 0.6250 | 0.5417 | 0.6250 | 129.166 |
| Test | B hybrid | 10/10 | 8 | 0.5000 | 0.5000 | 0.5000 | 906.259 |
| Test | C reranked | 10/10 | 8 | 0.8750 | 0.7438 | 0.7500 | 12324.265 |

No-answer cases (one development, two test) are reported separately and do not enter the Recall/MRR
denominators. All modes use the full selected five-document corpus for each question. These are
local retrieval measurements; part of the development run shared the workstation with regression
tests. Latencies are descriptive and are not isolated service benchmarks.

The broader development set contains eight C cases without complete evidence. Two are multi-source
tasks (`018` and `019`); others miss marketing, deployment integration, AI capital expenditure,
credit/funding, price, or investor-survey evidence units. On the test split, C completely covers
six answerable questions; the two multi-document cases each retrieve only one of two required
units. B trails A on this small natural-query split, despite beating A on the title-heavy development
split. Hybrid recall is therefore not uniformly beneficial; reranking improves this v2 retrieval
comparison while adding substantial local inference time.

Records: [development](../../evals/reports/e2-v2-dev-2026-10-18.json),
[test](../../evals/reports/e2-v2-test-2026-10-18.json), and
[original-pilot annotation regrade](../../evals/reports/e2-v2-pilot-rescore-2026-10-18.json).
The old pilot, revised-label regrade, and new split runs remain distinct artifacts. The test split
is now exposed; subsequent tuning should use development cases. A materially revised test rubric
must be versioned, and fresh unseen questions are needed for a new independent validation claim.

## Verification and next milestone

Final full regression: **218 passed, 6 skipped**. The focused contract suite passed 12 tests, and
changed-file Ruff lint/format checks passed. Contract coverage includes frozen data/configuration/corpus/model rejection,
split overlap, CRLF-independent hashes, all-alternative validation, matched comparison denominators,
and preservation of original execution details when regrading labels.

The E2 executable data/evaluation layer is complete at the provisional-label level. Human review
remains pending in `evals/rag/suites/v2/REVIEW.md`. E3 should next run a small set of real reports with
reference keypoints and saved Evidence bodies, especially multi-document and no-answer tasks,
before changing retrieval parameters. E4 can then target one frequent development failure with a
clear before/after comparison.
