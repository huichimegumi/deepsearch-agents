# E3.4: experimental indexed-local capability and query budgets

This stage targets the local research tool loop, not another semantic judge. The E3.3 two-task
baseline recorded 13 model-requested filesystem/todo calls across tasks 002/006, although the
requests only needed indexed knowledge. The new route removes those model-facing capabilities.
**It remains default-off: the bounded pilot still makes unsupported corpus-absence assertions
on the negative case. Faster execution is not semantic acceptance.**

## Explicitly selected route

The route is used only when `run_deep_agent(indexed_local_research_enabled=True)` is supplied,
the existing local-only detector matches, and the session contains no actual uploaded files.
Otherwise use the previous DeepAgents researcher. The report CLI exposes `--indexed-local`;
no new HTTP API field or automatic production enablement was added.

```powershell
# Preflight only, no model execution.
.venv\Scripts\python.exe -m evals.reports_acceptance.run --indexed-local --case-id report_local_002
# Deliberate experimental execution; zero web-query/page budgets in this runner.
.venv\Scripts\python.exe -m evals.reports_acceptance.run --execute --indexed-local --case-id report_local_002 --case-id report_local_006
```

The implementation uses the already installed `langchain.agents.create_agent`, without DeepAgents
filesystem, todos, memory, or delegation middleware. Its sole declared tool retains the external
name `collect_evidence` for compatibility but exposes only `query` and `knowledge_base`.
The backend always dispatches `source=local_document`; extra model-supplied SQL/Fee routing fields
cannot select a different source. Generic Web/SQL/Fee tooling remains on the legacy route.

The phase prompt and system prompt describe that actual capability set rather than asking the
restricted graph to use DeepAgents subagents. General filesystem/runtime instructions are not
passed into the restricted research phase. It still receives the original request, brief, actual
prefetched Evidence and retrieval status. Backend SQL semantic prefetch/correction/requirements
are also skipped in this route, even if an analytical-SQL environment flag is enabled.

Unknown tool requests stop the phase with `research_tool_not_allowed`. The final bounded policy
admits at most **two supplemental tool requests** after the unchanged mandatory lookup. An
over-budget model batch is rejected as a whole before the next tool step; it is not partially
dispatched. `local_research_query_limit` marks the run degraded while preserving already collected
Evidence for compression/writing. Model calls, run/phase time, writer reserve, retrieval parameters,
Claim/citation validation and source-filename boundaries are not relaxed or enlarged.

Trace/evaluation rows expose `research_tool_mode`, `research_tool_call_limit`, and a blocked-request
counter. Tool counters record model-requested/admitted calls and backend events, not necessarily
completed external executions. Admission tests and the compiled graph test verify the boundary;
zero observed forbidden names alone would not establish it.

## Compatibility and limitations

- Default callers remain on DeepAgents. Actual attachments, Web and mixed requests do not use
  this indexed-only route. Ordinary session copying, checkpoint persistence and backend artifact
  creation still perform their normal I/O; this is not a claim of zero filesystem access.
- A narrow positive source-join check prevents common phrases such as “本地知识库和数据库” or
  “RAG + SQL” from being misclassified as document-only. Negated database/Web/Fee lists retain
  the local route. This is not complete natural-language intent parsing or an authorization policy.
- Knowledge-base selection/tenant authorization is unchanged. The local tool may select `all`
  under the existing resolver; it does not establish a new per-request KB ACL. Existing user-memory
  preloading and non-research phases are not redesigned, although no memory tool is exposed here.
- The two-query supplemental cap can reduce coverage on complex local tasks. Reaching the cap
  is a degraded outcome, not successful research completion or a false runtime pass.
- Coroutine budgets do not forcibly interrupt all synchronous retrieval worker activity. Existing
  backend I/O/deadline limitations persist. No process-level hard real-time guarantee is claimed.
- Citation/source identity and actual retrieval do not establish entailment. In particular, three
  chunks cannot prove that all accessible documents lack a topic.
- Local-only describes the research tool source, not on-device LLM inference. The configured
  provider is unchanged and may receive passages through an API; no new privacy guarantee is made.

## Two preserved development pilots

Both pilots used the same frozen tasks 002/006, selected corpus and configured `qwen-flash` name
as E3.3, with unchanged 300-second run limits and zero web queries/pages. Generation is stochastic;
timings include local model/cache and provider conditions and are not an isolated service benchmark.

| Variant | Task | Seconds | Supplemental local requests | Unwanted tool requests | Execution |
| --- | --- | ---: | ---: | ---: | --- |
| E3.3 legacy baseline | 002 | 184.781 | 3 | 4 | degraded: timeout |
| E3.3 legacy baseline | 006 | 60.844 | 0 | 9 | degraded: call limit |
| First indexed pilot, uncapped | 002 | 190.062 | 9 | 0 | degraded: timeout/citation validation |
| First indexed pilot, uncapped | 006 | 68.219 | 3 | 0 | completed, zero local records |
| Second indexed pilot, cap=2 | 002 | 56.422 | 2 | 0 | degraded: query limit |
| Second indexed pilot, cap=2 | 006 | 52.641 | 2 | 0 | degraded: query limit |

Every row also has two mandatory backend lookup attempts. Backend Markdown creation is legitimate
and is not an unwanted researcher file tool. The first pilot demonstrates why capability removal
alone was insufficient: the model replaced tool churn with nine local searches and still timed out.
The second pilot reduced admitted supplementary retrieval but both tasks explicitly hit the cap.
Its instrumented LLM counts are 6/5 versus the legacy 10/11; these are not complete provider billing.

002 cites its finite reference unit in the bounded pilot, while the baseline did not. That is
mechanical anchor coverage, not answer accuracy. More importantly, 006 collected three unrelated
local snippets and asserted an exhaustive corpus-level absence anyway, despite valid IDs and known
filenames. Agent source inspection flags this unsupported inference; human labels remain pending.
**The quality gate therefore did not pass, and the route was not promoted to the default.**

A full manual-review packet for that bounded negative is available locally at
`evals/results/support_review_20261024T144244Z_1963e7f860/REVIEW.md`; creating it made no model call.
It displays the actual paragraphs and cited passages without pre-approving any human judgment.

Pilot IDs: `report_acceptance_20261024T141507Z_cdbe69712c` (uncapped) and
`report_acceptance_20261024T142538Z_6a32b9cb59` (bounded). Both source/dataset/corpus drift checks
passed. Private source archives preserve the pre-opt-in pilot code; restoring the original CRLF
for archived `main_agent.py` reconstructs both recorded source-tree fingerprints exactly. The final
default-off routing wrapper was added after reviewing those results, verified by unit tests and
a no-model CLI preflight, not by silently rewriting the pilot manifests.

The [content-free record](../../evals/reports/e3-4-indexed-local-agent-2026-10-24.json) keeps the
legacy comparison, failed uncapped pilot, bounded pilot, artifact hashes, source-archive hashes,
and final no-execution preflight separate. Only 002/006 were rerun; no six-task accuracy/acceptance
score or general latency improvement is claimed. The original reports and negative-case evidence
remain private under ignored evaluation results.

## Verification and next work

Full regression: **355 passed, 6 skipped**. Changed-file Ruff lint/format checks pass. The 26 added
tests cover factory capabilities, fixed-source dispatch with adversarial extra fields, a real
compiled model/tool/model graph using a synthetic model, prompt replacement, unavailable-tool
rejection, atomic query-budget admission, default-off opt-in forwarding, attachment/default route
compatibility, SQL environment isolation, and positive/negated source-combination routing.

Next, constrain the scope of conclusions supported by retrieved excerpts, especially exhaustive
absence/inventory claims, and obtain real human support annotations before promoting this route.
Do not substitute more failed model judging or a broad crawl for that acceptance gate. Cross-document
coverage and the remaining Web/cross-source E3 tasks remain incomplete.
