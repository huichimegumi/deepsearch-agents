# M3.34 Explicit subagent route contract

## Live boundary after M3.33

The fixed post-M3.33 `s2sql_041` validation used the full Tavily 6/6 ceiling and remained budget
compliant. It produced fourteen SQL Evidence records, six Web Evidence records, and five validated
Claims, and passed cross-source and citation validation. The complete workflow finished in about 88
seconds without an upstream or correction timeout.

The primary failure moved outside entity-recovery iteration. The Supervisor successfully dispatched
the registered `network_search` researcher, then later emitted a task request for the unregistered
`general-purpose` subagent. The deterministic allowlist correctly rejected that request as
`subagent_not_allowed:general-purpose`. Supervisor research therefore ended as `budget_exceeded`
after about 41 seconds, six LLM calls, five tool calls, and one accepted subagent dispatch. SQL
correction continued with the available Evidence, made two resolver attempts, and failed closed at
`sql_entity_resolution_clues_unsupported` without executing analytical SQL.

The run proves that the backend security boundary works, but it also exposes an avoidable mismatch:
the research prompt described a generic choice of suitable subagents while the runtime registered
exactly one machine route. The model could therefore select a DeepAgents built-in route that the
application intentionally forbids.

## Exact machine route in the phase contract

M3.34 makes the route contract explicit in both the Supervisor instruction and the generated phase
boundary:

- the only registered task route is `subagent_type=network_search`;
- `general-purpose` and every other subagent type are prohibited;
- the network researcher is used only for public-Web retrieval;
- the Supervisor performs planning, evidence analysis, Reflection, and Evidence Ledger assembly
  itself after the researcher returns.

The runtime allowlist remains unchanged and is still the final authority. M3.34 does not alias,
rewrite, execute, or silently ignore an invalid subagent request. If the model violates the explicit
contract, the existing `subagent_not_allowed:<route>` failure still stops the phase before an
unconfigured agent can run.

The SQL-correction instruction is also synchronized with M3.33: it now describes at most three
backend recovery rounds, each limited to two queries and two fetched pages, instead of the obsolete
single-recovery wording. Correction models remain forbidden from invoking search or subagents
themselves.

## Verification

Prompt tests assert that the generated research boundary includes the exact `network_search` route,
explicitly rejects `general-purpose`, and retains planning and ledger assembly in the Supervisor.
Workflow tests also assert the updated three-round SQL-correction description. Existing runtime
tests continue to prove that an unconfigured route is rejected before dispatch and that
`network_search` is accepted and counted.

Validation for this stage:

- focused workflow, route, and stability tests: 39 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 189 passed, 6 skipped.

No post-fix Tavily run is performed in M3.34. The next fixed validation should verify that the
Supervisor returns its Evidence Ledger after `network_search` rather than requesting a generic
subagent, allowing entity correction to receive the complete research artifact.
