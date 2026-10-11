# M3.14 Upstream model-timeout recovery

## Expanded-budget validation finding

The first M3.13 diagnostic run raised the one-task Tavily limits from the frozen 2/2 defaults to
6/6. It actually used five search queries and fetched three pages, producing three Web Evidence
records plus the previously discovered SQL schema. The run remained within both the configured
override and the hard cap of ten.

The Supervisor did not reach analytical SQL. An upstream model request raised
`APITimeoutError("Request timed out")` after about 145 seconds. Although roughly 155 seconds of the
run budget remained and collected Evidence was still usable, `_run_agent_phase` treated the
provider-specific timeout as an unknown exception. The exception escaped the phase boundary and
terminated the complete workflow before SQL correction, compression, or final writing.

## Recoverable phase boundary

M3.14 recognizes timeout exceptions across provider wrappers without importing a particular model
SDK. Recognition checks the exception and its cause/context chain for the built-in timeout types or
a timeout-bearing exception class name.

When a tool-capable phase encounters such an exception, the runtime now:

1. marks the phase `budget_exceeded` with reason `upstream_timeout`;
2. records the recovery in the trace;
3. preserves all Evidence already registered through backend tools;
4. returns control to the workflow instead of terminating the run;
5. allows the existing SQL-only correction gate, deterministic Evidence ledger, compression, and
   writer stages to use the remaining run budget.

Unknown non-timeout exceptions still propagate as errors. Cancellation semantics, recursion
limits, local phase deadlines, LLM-call reserves, SQL safeguards, and retrieval caps are unchanged.

## Trace schema v10

Trace schema v10 adds `upstream_timeout_recoveries`. Hybrid smoke output exposes the counter per
task and as `total_upstream_timeout_recoveries`. The affected phase also retains its
`budget_exceeded` status and `upstream_timeout` reason, so recovery is visible rather than reported
as a normal phase completion.

## Verification boundary

Deterministic tests verify that a provider-shaped `APITimeoutError`:

- does not escape `_run_agent_phase`;
- increments the recovery counter exactly once;
- produces a degraded, budget-exceeded phase with the expected reason;
- emits an operator-visible recovery event;
- leaves unrelated exception behavior unchanged through the existing suite.

No additional Tavily call is needed to implement this boundary. A later single-task diagnostic can
reuse the 6/6 override to confirm that a real upstream timeout now reaches SQL correction and final
reporting instead of ending the workflow.
