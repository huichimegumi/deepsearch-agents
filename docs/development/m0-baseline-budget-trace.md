# M0 development log: baseline, budget, and trace

Date: 2026-08-17

## Scope

M0 adds run-level controls and structured diagnostics around the existing four-phase research workflow. It does not redesign retrieval or introduce the planned evidence schema. Its purpose is to establish a measurable execution baseline before the Research Core is replaced.

The implementation includes:

- A run-level `ResearchBudget` with wall-clock, search-query, fetched-page, research-round, and LLM-call limits.
- Four budget profiles: quick, standard, interactive deep report, and opt-in thorough research.
- Reserved writer time so earlier phases cannot consume the entire run budget.
- A `research_trace.json` file for every executed task.
- Trace aggregation in the report evaluator.
- Separate `blocked`, `degraded`, `failed`, and `passed` outcomes.
- Initial waste metrics for duplicate queries, duplicate sources, queries with no new sources, and fetched pages that are not cited in the final result.

Relevant files:

- `app/agent/runtime.py`
- `app/agent/main_agent.py`
- `app/config.py`
- `app/tools/tavily_tool.py`
- `evals/runners/run_report_eval.py`

## Budget profiles

| Profile | Run SLO | Search queries | Fetched pages | Research rounds | LLM calls | Writer reserve |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Quick | 60 s | 3 | 4 | 1 | 8 | 15 s |
| Standard | 180 s | 8 | 8 | 1 | 16 | 45 s |
| Deep report | 300 s | 12 | 12 | 2 | 20 | 75 s |
| Thorough | 900 s | 30 | 24 | 3 | 40 | 180 s |

The current four-phase workflow receives 10%, 50%, 15%, and 25% of the selected run SLO. Existing phase limits remain safety caps. The run-level budget is authoritative when the two limits differ.

## Trace output

Each task writes `research_trace.json` in its session output directory. The trace contains:

- Run status, elapsed time, selected profile, and budget usage.
- Per-phase status, elapsed time, LLM calls, tool calls, and budget failures.
- Total LLM, tool, and subagent calls.
- Input and output tokens when the model provider reports usage.
- Search queries, unique candidates, and fetched-page counts.
- Initial waste counters.

Evidence-level waste cannot be measured yet because the current workflow passes evidence as text. That metric remains `null` until the structured Evidence milestone.

## Baseline command

```powershell
$env:UV_CACHE_DIR='.uv-cache'
$env:PYTHONIOENCODING='utf-8'
uv run python evals\runners\run_report_eval.py `
  --execute-ready `
  --output evals\results\report_eval.json
```

When `--timeout-seconds` is omitted, the evaluator uses the task's configured run SLO plus 15 seconds for cancellation and trace cleanup.

## Baseline result

The first M0 run used the 10 samples in `end_to_end_report_zh.jsonl`.

| Metric | Result |
| --- | ---: |
| Total samples | 10 |
| Blocked by unavailable MySQL | 5 |
| Executed web samples | 5 |
| Passed | 0 |
| Degraded | 5 |
| Markdown or PDF artifacts | 0 |
| Trace coverage among executed samples | 100% |
| P50 elapsed time | 131.2 s |
| P95 elapsed time | 208.3 s |
| LLM calls | 99 |
| Input tokens | 880,549 |
| Output tokens | 23,166 |
| Search queries | 52 |
| Unique search candidates | 75 |
| Fetched pages | 6 |

The five blocked samples require MySQL on `localhost:3307`. They were not executed and should not be counted as agent failures. The reported 50% trace coverage across all samples is therefore 100% coverage of the tasks that actually ran.

The evaluator's average score of 42.5 is not a report-quality score. Half the samples were blocked, and none of the executed samples created the required artifact. The useful baseline numbers are the artifact completion rate, degraded-run rate, phase failures, latency, token use, and retrieval behavior.

## Findings

### The clarification phase is not tool-free

All five clarification phases ran for exactly 30 seconds and timed out. Together they made 17 LLM calls and 17 tool calls. Some clarification runs also dispatched subagents.

`create_deep_agent(tools=[], subagents=[])` still exposes DeepAgents built-in capabilities. A prompt that says "do not use tools" is not an execution boundary. Clarification and evidence compression should use direct model calls with structured output rather than a general-purpose DeepAgent.

### The supervisor claimed files that did not exist

Several supervisor outputs said that a Markdown file had been saved in the session directory. The directories were empty. The final writer then searched for those files and reported that delivery could not continue.

File completion must be determined by the backend. The planned correction is:

```text
Writer returns Markdown text
  -> backend validates non-empty content
  -> backend writes the file
  -> backend verifies that the file exists
  -> task is marked complete
```

### Built-in subagents bypass the configured team

The research phase invoked `general-purpose` and `research-analyst` subagents in addition to the configured web researcher. These subagents can bypass the intended capability boundary and may claim work that the backend did not perform.

The research phase needs a backend allowlist for subagent types. Unknown subagent types should fail fast instead of running.

### LLM usage is dominated by repeated context

The five executed samples averaged 19.8 LLM calls and about 176,000 input tokens per task. Average input per LLM call was roughly 8,900 tokens. Input tokens exceeded output tokens by about 38 to 1.

Increasing `max_llm_calls` would postpone the failure without fixing this cost. Clarification and compression should each take one model call. The writer should take one content-generation call, followed by deterministic file handling.

### Retrieval still relies on snippets

Only 6 of 75 unique candidates were fetched, and all 6 came from one task. Four of the five web tasks read no full pages. This baseline confirms the need for the M2 `search -> select -> fetch -> parse -> evidence` pipeline.

Source quality also varied. Some tasks found official sources such as `cac.gov.cn` and `opentelemetry.io`, while the enterprise-agent and RAG-evaluation tasks relied heavily on blogs, aggregators, and video pages despite instructions to prefer primary sources.

### The first trace schema needs a small follow-up

M0 made the failures visible, but the first trace schema has three gaps:

- It counts tool calls without grouping them by tool name.
- It reports only the first phase failure as the run's failure reason.
- A phase can end normally and still return no usable artifact, but the trace does not record those as separate states.

The follow-up should add `tool_calls_by_name`, `all_failure_reasons`, and an artifact status for each phase.

## Next milestone: M0.1 execution stabilization

M0.1 should be completed before citation-quality evaluation begins.

1. Replace the clarification DeepAgent with one direct structured-output model call.
2. Replace the compression DeepAgent with one direct model call or deterministic aggregation.
3. Restrict research subagents to an explicit backend allowlist.
4. Make the writer return Markdown text and let the backend write and verify artifacts.
5. Record tool names, all failure reasons, and phase artifact status in the trace.
6. Rerun the same five web samples before changing retrieval behavior.

M0.1 acceptance targets:

| Metric | M0 baseline | M0.1 target |
| --- | ---: | ---: |
| Markdown artifacts | 0/5 | 5/5 |
| Clarification timeouts | 5/5 | 0/5 |
| Unexpected subagent types | Present | 0 |
| Average LLM calls per task | 19.8 | 12 or fewer |
| Average input tokens per task | 176k | At least 40% lower |
| P95 elapsed time | 208 s | 180 s or lower |

## Verification

The M0 implementation passed 82 automated tests. Ruff passed for every modified Python file. Pytest reported one cache-write warning because `.pytest_cache` was not writable in the local environment; the warning did not affect the test result.
