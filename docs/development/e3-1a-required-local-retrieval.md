# E3.1a: require real local lookup before evidence-backed reporting

The six-task E3.1 baseline showed that a task could finish without calling local retrieval and
then assert that known documents were absent. This stage adds a backend retrieval/abstention
boundary. It deliberately leaves Claim ID normalization, model choices, retrieval thresholds,
and the ordinary Agent/compression/writer implementation unchanged.

## Execution contract

When the existing local-only request detector matches a task:

1. Mark local retrieval as required before any model phase starts.
2. Before the Supervisor runs, execute the production `collect_evidence_request` collector using
   the original request, not evaluation answers, reference IDs, or gold anchors. Registry names
   literally present in the request select lookup scopes; otherwise the legacy `all` local scope
   is used. For the fixed suite these are the two explicitly named knowledge bases. Lookup is
   sequential per scope, not a new ranker, query decomposition model, or relevance calibration.
3. The mandatory lookup has at most 60 seconds inside the existing Supervisor allocation.
   Its elapsed time is subtracted from that phase's remaining time; overall budgets do not grow.
   Results are registered only by the awaiting coroutine after completion. Timed-out synchronous
   work can finish in its worker thread, but its late result cannot append Evidence to the run.
4. Supply the actual ledger and mechanical retrieval state to the unchanged research Agent.
   Agent-initiated local retrieval also records outcomes. Further retrieval is still possible;
   backend and Agent collector calls have distinct names in trace counters.
5. After research, if no local Evidence exists, bypass model compression/writing and produce a
   deterministic status report. The exhausted-run final fallback applies the same boundary.

The trace adds `local_retrieval` without changing its existing schema-version field. It records
whether lookup is required, outcome counts/statuses, registered local record count, whether any
attempt failed, and mandatory-lookup wall time. It contains no passage body or provider error text.
The evaluation runner preserves this summary next to its existing independent citation checks.

| State | Meaning with zero registered local records | Output boundary |
| --- | --- | --- |
| `not_executed` | No completed lookup outcome; includes exhausted budgets | Do not claim a search occurred or documents are absent |
| `error` | A lookup or registry operation failed/timed out | Explain execution failure, not corpus absence |
| `no_evidence` | Completed bounded retrieval returned no relevant chunks | Explain bounded non-match, not exhaustive document absence |
| `evidence` | At least one actual local record is registered | Continue existing Claim/citation validation; this is not answer support or correctness |

An error followed by returned Evidence keeps `had_error=true`; recovered records are not erased.
A lookup returning chunks, including a partial/context-limited batch, is not a semantic judgment
that those chunks answer the question. No-answer tasks therefore still require human review.

## Boundaries and limitations

- This is a deterministic lookup requirement, not a proof of statement entailment. A writer with
  some real Evidence can still omit required keypoints or misuse a citation. Existing Claim and
  final-citation validation remain in place; bracket-wrapped Claim IDs are not repaired here.
- Exact registry-name recognition is a convenience for the mandatory lookup, **not an ACL or
  authorization parser**. The pre-existing Agent tools retain their own knowledge-base selection.
  Requests with an unrecognized named scope still use legacy `all`; stricter scope schemas and
  tool authorization are separate work. The feature does not newly assert tenant isolation.
- The original full request is the mandatory query. No evaluation-specific question extraction
  or anchor-driven query rewriting is used. Long/compound requests and cross-document coverage
  can still need better query planning in a separately measured change.
- Worker cancellation is not CPU interruption. A running synchronous retrieval may outlive the
  coroutine deadline, and executor shutdown can wait for it. Late result isolation is tested;
  a strict process-level wall-clock guarantee is not claimed.
- Total run timing includes mandatory lookup. Its wall time is separately exposed because the
  existing Agent-phase timer starts after the mandatory lookup. This experiment shared the
  workstation with regression tests; timing is descriptive, not an isolated service benchmark.
- The frozen E2 corpus labels and references remain pending human review. This is the same known
  development sample, not a new held-out test. No independent expert or answer-accuracy claim.

## Validation protocol

Run the same six-case `local_v1.json` suite and user-facing prompt, same `qwen-flash` configuration,
same production retrieval parameters and 300-second run budget, with zero web-query/page limits.
Preserve the original run `report_acceptance_20261018T110328Z_58d089e350` and compare per-case
execution, actual lookup, evidence/reference coverage, and mechanical citation outcomes. Do not
collapse those dimensions into an automatic report pass rate. Source/dataset/corpus drift checks
remain required. Paid web and cross-source tasks are still outstanding E3 scope.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute
```

## Automated verification

Full regression: **245 passed, 6 skipped**. All changed Python files pass Ruff lint and format
checks. Sixteen new gate tests cover distinct empty/error/unexecuted states, deadline expiry,
no late Evidence registration, original-query/explicit-name scope selection, mandatory lookup
ordering, phase-time charging, provider-text sanitization, recovered Evidence diagnostics,
nonlocal-task compatibility, nonlocal Evidence not satisfying the gate, deterministic report
persistence, and the exhausted-run fallback. No Claim-ID acceptance rules were loosened.

This is one small paired development run, not a repeated-seed experiment or a causal estimate of
LLM quality changes. The gate necessarily introduces an original-query lookup per recognized
scope; later model queries can differ stochastically. Do not present evidence-count/timing deltas
as an isolated ranking improvement or compare them with E2's rank-only Recall@5 experiment.

## Actual paired run, 2026-10-19

Run `report_acceptance_20261019T113653Z_fc86f635c0` completed all six scheduled executions with
the same suite bytes, selected corpus, configuration, and dependency lock as the original baseline.
Before/after source/dataset/corpus drift checks passed. It made **12 mandatory collector attempts**
(two named scopes per task), zero web queries, and zero fetched pages. All six reports and private
Evidence/review packages were retained. The CLI correctly exited 1 because three runs degraded.

| Measurement | Original E3.1 | E3.1a |
| --- | ---: | ---: |
| Scheduled/executed tasks | 6/6 | 6/6 |
| Tasks with registered local records | 3/6 | 6/6 |
| Answerable tasks with zero local records | 2/5 | 0/5 |
| Execution completed / degraded | 1 / 5 | 3 / 3 |
| Answerable tasks with all reference units retrieved | 2/5 | 3/5 |
| Answerable tasks with all reference units cited somewhere in returned text | 2/5 | 3/5 |
| Human-reviewed semantic acceptance | pending | pending |

Reference-ID presence includes rejected-claim appendices. Cases 001/002 still failed the
application's final citation check despite matching reference IDs in returned fallback text.
Neither the last two coverage rows nor execution completion are report-answer pass rates.

| Case | Before → after execution | Before → after seconds | Before → after local records | Remaining issue |
| --- | --- | ---: | ---: | --- |
| 001 scenarios | degraded → degraded | 140.828 → 105.047 | 11 → 8 | call limit; final citation validation |
| 002 advantages | degraded → degraded | 156.406 → 98.234 | 0 → 10 | final citation validation; recovered tool error retained in diagnostics |
| 003 customer service | degraded → completed | 178.688 → 70.891 | 3 → 6 | semantic review still pending |
| 004 policy | degraded → completed | 54.672 → 83.640 | 6 → 10 | reference outlook unit absent; retrieved retrospective unit not cited |
| 005 two-document comparison | completed → degraded | 20.453 → 180.047 | 0 → 2 | timeout; final citation validation; both reference anchors absent |
| 006 no-answer | degraded → completed | 37.516 → 155.484 | 0 → 2 | unrelated broader-query hits and unsupported document inventory |

Content-free [paired record](../../evals/reports/e3-1a-local-retrieval-2026-10-19.json) pins the
original summary hash and preserves current manifests, per-case file hashes, counters, and outcomes.
Some tasks are slower, especially the previously fast but unsupported cross-document answer.
This change enforces real work; it is not a demonstrated latency optimization.

### Negative-case finding: returned chunks are not evidence of absence

Both initial mandatory lookups for 006 returned `NO_EVIDENCE`. Later broad Agent queries retrieved
two real but unrelated chunks, changing its mechanical state to `evidence`. The writer then claimed
a systematic document inventory check and named documents absent from the selected five-document
corpus. Agent source inspection flagged those statements as unsupported. This is **not** appropriate
abstention acceptance, even though citation IDs exist and the runtime completed. Human review
remains pending; the source-audit flags are not an independent human approval or accuracy metric.

Consequently no final row of this real run exercised the zero-record terminal override: its
not-executed/error/no-evidence output behavior is demonstrated by the deterministic integration
tests, while the real run demonstrates mandatory lookup execution and the unresolved relevance/
entailment gap. Do not claim this stage solves no-answer hallucination or false corpus inventories
when some unrelated Evidence has been collected.

## Next bounded work

Keep this paired record unchanged. Fix exact bracket-wrapped Claim IDs without accepting unknown
or fuzzy-matched IDs, then evaluate evidence support and appropriate abstention using the saved
passages and reference tasks. Cross-document coverage and built-in tool churn remain unresolved.
Do not expand paid web evaluation or tune the exposed E2 query test set to conceal these failures.
The two web and two simple cross-source E3 tasks and human report review remain outstanding.
