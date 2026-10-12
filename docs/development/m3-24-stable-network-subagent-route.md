# M3.24 Stable network-researcher route identity

## Motivation

M3.23 added content-free entity rejection categories so the next live run could identify the exact
cross-source grounding boundary. The first authorized one-task Tavily 6/6 attempt did not reach
research because the clarification model timed out; it issued zero searches and fetched zero pages.
A single retry completed clarification but the Supervisor phase stopped with
`subagent_not_allowed:network_search`, again before any search request.

The network researcher was configured and passed to DeepAgents, so this was a local admission
contract bug rather than a missing capability. Its dictionary used the localized YAML display name
as the machine `name`, while the task call used the stable route token `network_search`. The backend
allowlist was built from the localized dictionary name and rejected the otherwise valid dispatch.

## Stable machine identity

The network subagent now has an explicit code-owned route name:

```text
network_search
```

The localized YAML name remains part of the description shown to the model and operator. It no
longer participates in security-sensitive identity comparison. Consequently:

- DeepAgents registration and `task.subagent_type` use the same ASCII token;
- the backend allowlist is derived from that exact registered token;
- changing translations or display copy cannot silently revoke the route;
- the built-in `general-purpose` subagent remains outside the allowlist.

This is intentionally not an alias-based bypass. Unknown names are still rejected before dispatch,
and the existing per-profile subagent-call limit is unchanged.

## Verification

The positive phase test emits a `task` call with `subagent_type=network_search`, verifies that the
stream continues to its normal result, and confirms exactly one subagent/tool call in telemetry. The
negative test still rejects `general-purpose` without continuing the stream. A routing contract test
asserts that the configured allowlist contains only `network_search`.

The complete suite passes with **178 passed and 6 skipped**, and Ruff checks pass. Neither diagnostic
attempt consumed Tavily credits: both recorded zero search queries and zero fetched pages. No
post-fix paid run was started in this stage, and generated evaluation content remains ignored.

## Remaining boundary

The next one-task validation should confirm that the stable route reaches fetched Web Evidence and
then read the M3.23 entity rejection category. If entity grounding succeeds, the workflow can proceed
to unique database value matching and executable SQL semantics. If it fails, the bounded category
must guide the next fix; the entity gate should not be weakened speculatively.
