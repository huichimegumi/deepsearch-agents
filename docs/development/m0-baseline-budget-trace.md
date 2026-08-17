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
| Quick | 60 s | 3 | 4 | 1 | 6 | 15 s |
| Standard | 180 s | 8 | 8 | 1 | 10 | 45 s |
| Deep report | 300 s | 12 | 12 | 2 | 12 | 75 s |
| Thorough | 900 s | 30 | 24 | 3 | 20 | 180 s |

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

M0.1 resolves these gaps with `tool_calls_by_name`, `failure_reasons`, and an artifact status for each phase.

## M0.1 execution stabilization

M0.1 was implemented on 2026-08-17. It makes the following changes:

1. Clarification now uses one direct structured-output model call. It returns a typed research brief and has no DeepAgents tools or built-in subagents.
2. Evidence compression also uses one direct structured-output call. The writer receives the compressed package and brief, not the large raw supervisor ledger.
3. The research supervisor rejects any `subagent_type` that is not one of the three configured researchers.
4. Final writing uses one direct model call. The model returns the complete Markdown body, and backend code writes and verifies `report.md`. PDF requests still follow Markdown-first conversion.
5. Trace schema version 2 records `tool_calls_by_name`, every unique failure reason, and an artifact status for each phase.
6. Profile LLM limits were reduced to 6, 10, 12, and 20 calls. The budget reserves one compression call and one writer call after supervisor research.

The code-level stabilization is complete. The same five web samples were rerun after implementation. Unit tests establish the orchestration boundaries; the live rerun below measures latency, token use, and artifact behavior.

M0.1 acceptance targets:

| Metric | M0 baseline | M0.1 target |
| --- | ---: | ---: |
| Markdown artifacts | 0/5 | 5/5 |
| Clarification timeouts | 5/5 | 0/5 |
| Unexpected subagent types | Present | 0 |
| Average LLM calls per task | 19.8 | 12 or fewer |
| Average input tokens per task | 176k | At least 40% lower |
| P95 elapsed time | 208 s | 180 s or lower |

## M0.1 rerun result

The rerun executed the five web-only samples. The five MySQL samples remained blocked because MySQL was not available on `localhost:3307`.

The requested output path, `evals/results/report_eval.json`, still contains the older M0 aggregate with schema version 1. Its modification time predates the M0.1 source changes. The M0.1 process did create five new schema version 2 traces and report files under `app/output/user_evals`, but it did not finish writing the aggregate result. The measurements below were recalculated directly from those traces. This distinction matters because the stale JSON still reports 99 LLM calls and the old 20-call Deep Report limit.

| Metric | M0 baseline | M0.1 rerun | Change |
| --- | ---: | ---: | ---: |
| Normally completed runs | 0/5 | 1/5 | +1 |
| Degraded runs | 5/5 | 4/5 | -1 |
| Non-empty Markdown files | 0/5 | 5/5 | +5 |
| Strict artifact-format matches | 0/5 | 0/5 | No change |
| Clarification timeouts | 5/5 | 0/5 | Fixed |
| Average LLM calls per task | 19.8 | 9.2 | -53.5% |
| Average input tokens per task | 176,110 | 76,843 | -56.4% |
| Total output tokens | 23,166 | 31,414 | +35.6% |
| Total tool calls | 84 | 39 | -53.6% |
| P50 elapsed time | 131.2 s | 199.6 s | +52.1% |
| P95 elapsed time | 208.3 s | 216.6 s | +4.0% |
| Search queries | 52 | 60 | +15.4% |
| Full pages fetched | 6 | 10 | +4 |

Three M0.1 targets passed: clarification no longer times out, average LLM calls are below 12, and average input tokens fell by more than 40%. Backend persistence also wrote Markdown for every task. Latency failed the target, and only one run completed without degradation.

### Per-sample phase outcome

| Sample | Run status | LLM calls | Elapsed | Limiting phase | Markdown |
| --- | --- | ---: | ---: | --- | --- |
| `report_zh_001` | Degraded | 10 | 187.6 s | Supervisor timed out at 150 s | Written |
| `report_zh_003` | Degraded | 9 | 199.6 s | Supervisor timed out at 150 s | Written |
| `report_zh_005` | Degraded | 5 | 205.1 s | Supervisor timed out at 150 s | Written |
| `report_zh_007` | Degraded | 11 | 216.6 s | Compression timed out at 45 s | Written |
| `report_zh_009` | Completed | 11 | 172.7 s | None | Written |

Clarification took one LLM call and no tool calls in every sample. Compression and final writing also used one direct call when admitted by the phase budget. The remaining latency is concentrated in supervisor research. Three supervisors used the full 150-second allowance, and a fourth ran for 138.5 seconds before compression consumed its full 45-second allowance.

### Artifact-format false positive

All five Markdown-only samples also generated `report.pdf`. The evaluator therefore treats them as artifact-format mismatches even though `report.md` exists and is non-empty.

The constrained eval prompt names both `generate_markdown` and `convert_md_to_pdf` when it describes the report-generation route. `_requested_artifact_formats()` currently scans the whole task for the substring `pdf`, so the tool name overrides the later instruction to generate Markdown only. Artifact intent needs a structured field or an explicit precedence rule for the final-output instruction.

### Supervisor fan-out still dominates runtime

The five supervisors dispatched 6, 5, 1, 2, and 1 researcher tasks. A researcher task can run several queries and search backends, so the first two samples expanded far beyond one focused web-research pass. The rerun used the full 12-query allowance in every sample, up from 52 total queries in M0.

Waste counters also worsened:

- Duplicate queries increased from 0 to 12.
- Queries with no new sources increased from 14 to 19.
- Duplicate sources increased from 3 to 9.
- Ten pages were fetched, all by `report_zh_009`, and all ten were counted as unused in the final report.

The other four samples fetched no full pages. They still relied on snippets.

### The research tool boundary is incomplete

No unconfigured subagent type appears in the new run, and no `subagent_not_allowed` failure was recorded. The subagent allowlist is working for the observed calls.

The research DeepAgent still called built-in tools that were not part of the configured evidence-gathering surface: `write_todos`, `write_file`, and `read_file`. Supervisors also claimed that report files had already been written. Backend persistence prevented this claim from breaking final delivery, but it remains misleading and consumes calls inside the research budget.

### Final citations are not grounded in the logged search set

An audit compared each final report URL with the URLs recorded in `search_result.top_results`. Exact overlap was zero for all five reports: 0 of 6, 0 of 7, 0 of 22, 0 of 11, and 0 of 14 report URLs matched the logged search URLs.

This check covers only the top results stored in the audit log, so it cannot prove that every unmatched URL was invented. The result is still a strong warning. Several report links contain obvious placeholder patterns such as `docId=123456` and `sn=abc123def456ghi789`, while other citations point to pages that never appeared in the recorded search set. The writer can currently add URLs from model memory instead of staying inside retrieved evidence.

Artifact completion must therefore remain separate from report quality. M0.1 fixed delivery, not evidence grounding.

## Recommended M0.2 follow-up

M0.2 should remain small and focus on the failures exposed by this rerun:

1. Parse artifact intent from a structured request field. For text prompts, make the explicit final-output instruction take precedence over tool names.
2. Limit web-only supervisor fan-out to one primary researcher task and, when needed, one targeted follow-up.
3. Reduce the supervisor phase allowance to about 90 seconds so one phase cannot consume most of the SLO.
4. Reject research-stage calls to file-writing built-ins and remove `write_todos` unless it is required for execution.
5. Carry an allowlist of observed evidence URLs into compression and writing. Reject or label citations outside that set.
6. When supervisor research falls back, force compression to return an explicit insufficient-evidence package instead of filling gaps with new facts.
7. Write the eval aggregate incrementally or from a `finally` path so an interrupted shutdown cannot leave a stale result file.

M1 retrieval work should begin after these controls are in place. Otherwise a stronger fetch pipeline can still feed an unbounded supervisor and an ungrounded writer.

## Verification

The M0.1 implementation passed 87 automated tests. The new regression coverage checks single-call structured phases, rejection of unconfigured built-in subagents, deterministic Markdown persistence, complete failure-reason collection, tool-name counters, and the compressed writer handoff. Ruff passed for every modified Python file. Pytest reported one cache-write warning because `.pytest_cache` was not writable in the local environment; the warning did not affect the test result.
