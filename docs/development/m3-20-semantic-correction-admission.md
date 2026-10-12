# M3.20 Grounded-semantic SQL correction admission

## Failure exposed after M3.19

The first post-M3.19 live run used the authorized Tavily 6/6 ceiling and consumed all six queries
and pages. It retained six Web Evidence records, five validated Claims, and the compact three-record
formula bundle. The Supervisor exhausted its phase budget before making any SQL call, however.

The backend then skipped SQL correction because its admission gate required schema or sample
Evidence. This was inconsistent with M3.17: the pinned formula records already contained physical
`resolved_columns` and `relevant_table_columns`, which are sufficient to establish that the database
and required SQL inputs have been discovered. The run therefore ended after about 177 seconds with
zero SQL attempts and zero correction attempts despite retaining more than enough workflow budget.

No decrypted task, gold answer, reference SQL, model output, or local evaluation log is committed.

## Grounded-semantic admission

`ResearchRunTrace.can_attempt_sql_correction` now recognizes a semantic record as database
discovery only when all of the following hold:

- its Evidence kind is `database_semantics`;
- `resolved_columns` is present and non-empty;
- `relevant_table_columns` is present and non-empty.

Schema and sample Evidence retain their previous behavior. A formula description without physical
grounding does not open the correction gate. Existing requirements also remain unchanged: the run
must explicitly require analytical SQL, must not already have `query_result` Evidence, and may
attempt correction only once.

This reuses already collected, discovery-only Evidence. It does not add an LLM call, SQL attempt,
research round, Web query, page fetch, or timeout allowance.

## Post-fix live validation

A second authorized Tavily 6/6 run consumed six queries and five pages. It completed in about 98
seconds, retained five Web Evidence records and three validated Claims, and preserved valid final
citations. Most importantly, the same grounded semantic bundle now admitted SQL correction:

- correction attempts increased from zero to one;
- two distinct correction proposals reached the read-only database;
- the correction phase completed in about seven seconds rather than timing out;
- downstream compression and final writing both completed;
- all search-budget limits remained compliant.

Strict correctness remains false. Both correction proposals were rejected for unknown columns
because the model still represented the named derived metric as a physical field instead of fully
expanding its formula dependencies. That is now the isolated next bottleneck: proposal validation or
deterministic formula compilation, not correction admission, timeout, or evidence handoff.

## Verification

Tests cover all three valid admission paths (schema, sample, and physically grounded semantics) and
verify that ungrounded semantic text cannot enable correction. The full suite continues to cover the
single-attempt correction bound, reserved recovery admission, read-only SQL policy, Evidence gates,
and trace privacy.
