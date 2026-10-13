# M3.30 Per-call fetched-page cap

## Live boundary after M3.29

The post-M3.29 validation reused the fixed `s2sql_041` task and Tavily 6/6 ceiling. The Supervisor
performed no Web search, so backend entity recovery used the two reserved queries directly. The
candidate-backfill path retained three successful Web Evidence pages from six candidates, performed
two entity-resolution attempts, and completed in about 43 seconds. Fourteen SQL Evidence records,
three Web Evidence records, three validated Claims, cross-source validation, and citation validation
all succeeded. The second resolver still failed closed at `sql_entity_resolution_clues_unsupported`.

The three retained pages exposed a local-budget bug. M3.27 intended entity recovery to own two
reserved page slots. Once those slots were released, however, `research_search` saw the entire
global remaining capacity. Because the Supervisor had used zero pages, the tool passed a six-page
success cap into M3.29 backfill. The run remained compliant with the global 6/6 ceiling, but recovery
exceeded its local two-page allowance.

## Hierarchical page admission

M3.30 adds an optional `max_fetched_pages` argument to `research_search`. The tool resolves the
effective limit as follows:

- with a run budget: `min(requested call cap, currently available run pages)`;
- without a requested call cap: the currently available run pages;
- without a run budget: the non-negative requested call cap, when present.

A caller can therefore tighten page use but cannot expand the run-level budget. A resolved limit of
zero disables full-page fetching. Monitoring records both the requested and effective page caps.

Entity recovery now passes its released page allowance explicitly. Its candidate pool may still
contain up to six ranked URLs for M3.29 backfill, but no more than two may retain successful full-page
content in that call. Query admission, run-level page accounting, stable Evidence IDs, and all
entity/SQL gates remain unchanged.

## Verification

Tests prove that a one-page call cap tightens a two-page run allowance and that an oversized call cap
is reduced to the available run capacity. The entity-recovery integration assertion verifies that
the exact released allowance is forwarded with its bounded candidate pool. Existing backfill tests
continue to prove that failures can be replaced without exceeding the effective success cap.

Validation for this stage:

- focused search, runtime, and entity-recovery tests: 55 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 187 passed, 6 skipped.

No post-fix Tavily run is performed in M3.30. The next fixed validation should retain at most two
recovery pages even when ordinary research used none, then use the resulting content-free entity
category to guide the next stage.
