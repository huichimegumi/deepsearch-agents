# M3.31 Reserved correction retry time

## Live boundary after M3.30

The post-M3.30 validation reused the fixed `s2sql_041` task with the Tavily 6/6 ceiling. The run
used all six search queries and retained exactly six fetched pages, confirming that the ordinary
4/4 allowance and backend recovery 2/2 allowance now compose correctly. It produced fourteen SQL
Evidence records and six Web Evidence records, accepted eight Claims, rejected two Claims, and
passed citation validation. No upstream timeout occurred.

The run nevertheless stopped before analytical SQL execution. Entity resolution made one attempt,
returned no grounded value match, and requested recovery. Recovery then consumed the SQL correction
phase's complete 60-second allowance, so the phase timed out before the required second resolver
attempt. The trace consequently reported `timeout` and `analytical_sql_evidence_missing`. Total task
time was about 153 seconds out of the 300-second run limit, showing that overall capacity remained
available but was inaccessible behind the correction phase's former 20% share.

## Bounded correction expansion

M3.31 raises the SQL evidence correction allocation from 20% to 30% of the profile's total run time.
For the 300-second deep-report profile, the theoretical phase ceiling therefore increases from 60
to 90 seconds. Quick and standard profiles scale from their own total run limits; no fixed
deep-report timeout is embedded in the runtime.

The larger share does not grant correction unrestricted access to the remaining run. Its dynamic
timeout is still bounded by elapsed wall-clock time, configured phase timeout, and the run-level
writer and verifier reserves. Correction now also deducts the complete 15% evidence-compression
allocation before admission. In simplified form:

```text
correction timeout = min(
    configured timeout,
    30% of total run time,
    remaining run time - writer reserve - verifier reserve - 15% compression reserve,
)
```

This gives a successful recovery search enough room to reach its second structured entity resolver
when the run is healthy, while preserving deterministic capacity for Evidence compression and final
report generation. If the run is already late, the timeout still shrinks or closes rather than
borrowing from those stages.

Search-query, fetched-page, research-round, and LLM-call ceilings are unchanged. The M3.30
per-call page cap, stable Evidence IDs, complete-clue checks, catalog constraints, database-value
grounding, analytical SQL gate, and citation validation also remain unchanged.

## Verification

The runtime tests verify both sides of the new boundary:

- a fresh 100-second test profile receives at most 30 seconds for SQL correction;
- after 50 seconds have elapsed, the same profile receives only about 10 seconds, preserving its
  15-second compression allocation and 25-second writer reserve.

Validation for this stage:

- focused runtime and stability tests: 45 passed;
- Ruff checks for changed Python files: passed;
- full repository suite: 188 passed, 6 skipped.

No post-fix Tavily run is performed in M3.31. The next fixed validation can determine whether the
additional bounded phase time permits recovery to complete the second resolver and proceed to
analytical SQL without changing the 6/6 paid-search ceiling.
