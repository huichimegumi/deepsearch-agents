# M3.6 Analytical SQL Evidence gate

The post-M3.5 one-task validation reached the intended tools under the `deep_report` timing profile:

| Metric | Result |
| --- | ---: |
| Selected task | `s2sql_041` |
| Schema discovery calls | 1 |
| Sample-table calls | 3 |
| Analytical SQL query attempts | 0 |
| SQL Evidence records | 20 |
| Web Evidence records | 2 |
| DuckDuckGo queries/pages | 2 / 2 |
| Cross-source Evidence | Yes |
| Citation validation | Passed |
| Strict answer | Incorrect |
| Tavily authorized or used | No |

This result exposed a semantic problem rather than a retrieval problem. The model treated schema and
three-row samples as sufficient SQL evidence and never executed the analytical query required to
answer the task. The large SQL Evidence count therefore overstated actual database support.

M3.6 assigns an `evidence_kind` to SQL records:

- `database_schema` for table listings and schema descriptions;
- `database_sample` for bounded sample rows;
- `query_result` for rows returned by an explicit analytical query.

All records remain in the backend Evidence Ledger so the model can use schema and samples for query
construction. Only `query_result` records are claim-eligible. Claim compression deterministically
rejects schema or sample IDs used as support for final facts or inferences.

The Hybrid runner also sets an analytical-SQL requirement. If supervisor research completes without
`query_result` Evidence, the run is marked degraded with `analytical_sql_evidence_missing`, and the
handoff tells compression to report the gap. Smoke results expose an `analytical_sql_evidence`
boolean alongside schema, attempt, failure, and block counters.

No additional live run was issued after implementing the gate. The deterministic suite verifies the
classification and rejection behavior without consuming another DuckDuckGo request; Tavily remains
unused.

