# M3.2 Hybrid smoke baseline

Date: 2026-10-05

This baseline runs the three-task M3.1 subset as an engineering diagnostic. Decrypted questions,
gold answers, reference SQL, and model outputs remain in ignored local files and are not reproduced
here.

## What the first run exposed

The initial DuckDuckGo configuration used `SEARCH_BACKEND=duckduckgo`, but that setting applied only
when the model requested `auto`. On the Parallel task the model explicitly requested `advanced`, so
the service resolved `duckduckgo+tavily`. At most two Tavily queries may have been issued before the
run exposed the problem.

M3.2 replaces that soft preference with `SEARCH_BACKEND_LOCK`. When set by the evaluator, it
overrides every model-provided backend argument. Paid or mixed runner modes still require
`--allow-paid-search`, so the CLI gate and tool-level enforcement now agree.

The same run also showed that a missing Supervisor summary discarded usable tool evidence before
compression. `ResearchRunTrace` now maintains an in-memory, bounded backend Evidence Ledger and
attaches it to the research handoff independently of the model summary. Evidence content remains
absent from serialized telemetry.

Finally, the eval instruction used the literal words Markdown and PDF inside a negative sentence.
The existing deterministic artifact detector interpreted those words as a file request. The prompt
now asks for a direct chat answer without naming file formats, and the runner removes stale session
outputs before every execution.

## Post-fix execution

The second execution used a hard DuckDuckGo lock and no paid-search authorization.

| Metric | Result |
| --- | ---: |
| Selected tasks | 3 |
| Strictly correct | 0 |
| Normal completion | 1 |
| Degraded completion | 2 |
| Valid final citations | 3 |
| Tasks with both SQL and Web Evidence | 2 |
| Validated Claims | 11 |
| Rejected Claims | 0 |
| Search queries used | 4 / 6 |
| Fetched pages used | 4 / 6 |
| Tavily authorized | No |

The strict score is deliberately reported as zero rather than hidden behind report-quality prose.
One task completed normally but produced the wrong answer. Two tasks degraded because of the LLM
call limit or an earlier planning timeout. The Parallel task did not reach Web search. Repeated SQL
errors also show that table listing alone is not enough schema support for reliable SQLite planning.

## Interpretation and next action

M3.2 verifies that the evidence and citation architecture can survive a missing Supervisor summary:
the post-fix run moved from zero validated Claims and three invalid citation results to valid
citations on all tasks. It does not yet demonstrate correct hybrid reasoning.

The next improvement should be generic SQLite schema discovery and bounded SQL repair telemetry.
It should be evaluated on the same frozen tasks without changing task-specific prompts, gold data,
or the search budget. Expanding the task count or spending Tavily credits would not address the
current database-planning bottleneck.
