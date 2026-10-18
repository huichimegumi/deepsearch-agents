# M3.35 Retrieval-aware subagent admission

## Live boundary after M3.34

The fixed post-M3.34 `s2sql_041` validation confirmed that the explicit route contract removed the
previous failure: every Supervisor dispatch used the registered `network_search` route, and no
`subagent_not_allowed` event occurred. The run stayed within the Tavily 6/6 ceiling, producing
fourteen SQL Evidence records, five Web Evidence records, and four validated Claims with valid
cross-source citations.

The next bottleneck was repeated legal dispatch after useful retrieval capacity was gone. The
Supervisor requested `network_search` five times. Only the initial researcher performed the
ordinary Web retrieval; later dispatches did not add sources, while the Supervisor continued its
agent loop until the 150-second research-phase allocation expired. That phase accumulated ten LLM
calls and ten tool calls and ended with `timeout`. The complete workflow took about 192 seconds.
SQL correction then used the reserved retrieval capacity, made two entity-resolution attempts, and
failed closed at `sql_entity_resolution_clues_unsupported` without analytical SQL.

The query and fetched-page ledgers already enforced hard limits inside `research_search`, so the run
never exceeded 6/6. The missing control was earlier admission: the Supervisor could still launch a
network subagent after either dimension available to ordinary research had reached zero, causing
model latency without any possibility of new full-page Evidence.

## Admit only useful network researchers

M3.35 adds a pre-dispatch admission gate for the configured `network_search` subagent. After the
route allowlist check and before recording or launching the task, the backend requires both:

```text
ResearchBudget.available_search_queries > 0
ResearchBudget.available_fetched_pages > 0
```

These properties are reserve-aware. The final two queries and two pages held for backend entity
correction remain invisible to ordinary Supervisor dispatch, so a repeated researcher cannot consume
them. When either ordinary dimension is exhausted, the phase stops immediately with
`subagent_retrieval_budget_exhausted`. The denied request is not counted as a tool call or subagent
call and cannot begin execution.

The phase prompt now tells the Supervisor that one `network_search` dispatch can batch multiple
complementary queries. Once query or page capacity is exhausted, it must stop dispatching and return
the Evidence Ledger plus remaining gaps. The existing route allowlist, per-profile subagent-call
limit, search-tool hard limits, phase timeout, and run timeout remain independent defense layers.

## Verification

Parameterized tests exhaust query capacity and fetched-page capacity separately, then present a
valid `network_search` task request. Both cases prove that the stream is stopped before the agent
continues, the trace records `subagent_retrieval_budget_exhausted`, and neither the task tool count
nor subagent count increases. Existing tests continue to cover legal dispatch and invalid-route
rejection. Prompt assertions cover batching and the required stop behavior.

Validation for this stage:

- focused stability, workflow, routing, and runtime tests: 66 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 191 passed, 6 skipped.

No post-fix Tavily run is performed in M3.35. The next fixed validation should show one useful
Supervisor researcher followed by an immediate ledger handoff or bounded admission stop, rather
than repeated zero-capacity dispatches and a 150-second timeout.
