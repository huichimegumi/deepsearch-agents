# M3.13 Explicit evaluation retrieval overrides

## Post-M3.12 validation finding

The first post-M3.12 `s2sql_041` run used exactly two Tavily queries and two fetched pages. It
completed normally in about 101 seconds, collected both Web and analytical SQL Evidence, passed
citation validation, and attached an executed SQL query. The strict SQLite result comparison still
failed.

The audit localized the failure to entity resolution rather than SQL execution infrastructure. The
two fetched pages did not resolve the clue chain to a unique entity. The Supervisor consequently
ran several valid but generic analytical queries, and the final output attached one of those
executed queries. This is the first result in the sequence where a larger diagnostic retrieval
budget is justified.

## Explicit bounded overrides

M3.13 keeps the frozen smoke-subset defaults at two search queries and two fetched pages per task.
It adds two optional runner arguments for deliberate evaluation runs:

```text
--max-search-queries N
--max-fetched-pages N
```

Each value must be between 1 and 10. Omitting both arguments preserves the frozen defaults. The
resolved report records whether an override was used, the hard per-task cap, the effective
per-task limits, and the aggregate maximum for the selected task count.

Paid or mixed search backends remain fail-closed. Selecting Tavily, Perplexity, `auto`, or
`advanced` still requires `--allow-paid-search`; a budget override does not imply paid-search
authorization.

## Safety and interpretation

- Overrides affect only the evaluation runner's run-local `ResearchBudgetLimits`.
- The frozen task-selection file is not modified.
- The hard cap is enforced before task execution, including for direct Python callers.
- Actual query and fetched-page usage remains available in per-task and aggregate output.
- A larger run remains an engineering diagnostic and does not become a statistically meaningful
  benchmark result.
- Decrypted questions, reference SQL, model outputs, and audit logs remain ignored local data.

The next validation should use one task with a moderate override, not the full three-task subset.
Its purpose is to determine whether entity resolution improves before changing SQL selection or
Claim-to-Evidence behavior.
