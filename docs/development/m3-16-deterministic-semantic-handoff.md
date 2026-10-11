# M3.16 Deterministic semantic prefetch and Claim-safe handoff

## Post-M3.15 live validation

The first post-M3.15 one-task run used the explicitly authorized Tavily 6/6 override. It consumed
six queries and five fetched pages, stayed within the configured limits, and completed in about
110 seconds without an upstream timeout.

M3.15 fixed the previous SQL execution failure: schema discovery exposed 136 semantically described
columns, all five analytical SQL attempts executed successfully, analytical SQL Evidence was
collected, and one actually executed query was attached to the result. The earlier unknown-column
correction failure did not recur.

Two narrower failures remained:

1. the Supervisor did not call `search_semantic_knowledge`, despite the prompt instruction, and
   therefore did not receive the pinned formula for the named derived metric;
2. Compression cited five schema Evidence IDs from the Supervisor summary. Those IDs were correctly
   rejected as discovery-only, leaving zero accepted Claims and causing final citation validation to
   fail.

The run was therefore degraded and strictly incorrect. No decrypted question, gold answer,
reference SQL, model output, or local evaluation log is committed.

## Backend semantic prefetch

When both `EVIDENCE_SQLITE_PATH` and `EVIDENCE_SQLITE_KNOWLEDGE_PATH` are configured, the backend now
performs one bounded `search_semantic_knowledge` call using the original task before Supervisor
research. Matching formula records are rendered into a dedicated SQL semantic context in the
Supervisor prompt.

This removes reliance on model tool-selection behavior. The prefetch:

- uses the existing deterministic ranking and eight-record cap;
- has a ten-second maximum inside the existing run-level time budget;
- increments SQL semantic-discovery telemetry;
- consumes no Web query, fetched-page, or research-round budget;
- remains discovery-only and cannot directly support final Claims.

The SQL-correction prefetch from M3.15 remains in place as a recovery path when no analytical SQL
Evidence was collected during Supervisor research.

## Claim-safe Compression handoff

The raw Supervisor artifact may contain reasoning, stale IDs, or discovery-only citations. M3.16 no
longer replays it into the structured Compression call. Instead, the backend constructs a separate
handoff containing:

- the structured research brief;
- a fresh Evidence Ledger filtered by the runtime's `claim_eligible_evidence_ids`;
- Web Evidence before SQL Evidence, preserving cross-source context within bounded ledger space;
- an explicit instruction that only the listed IDs may support Claims.

Schema, samples, semantic formulas, and the Supervisor's unvalidated prose are excluded. If no
claim-eligible Evidence exists, Compression receives an explicit gap instruction rather than IDs it
cannot legally cite.

`render_evidence_ledger` now supports deterministic filtering by Claim eligibility or Evidence kind.
This keeps the all-record ledger available to SQL correction while allowing the Supervisor semantic
context and Compression handoff to use different trust boundaries. No trace schema change is
required; schema v11 already records semantic discovery, rejected Claims, unknown IDs, and citation
validity.

## Verification boundary

Tests verify that:

- Supervisor prefetch exposes a matching pinned formula without consuming external retrieval budget;
- prefetched semantic Evidence remains outside the Claim gate;
- Claim-only ledgers exclude schema and semantic records;
- kind-filtered ledgers expose only the requested discovery class;
- Compression never receives raw Supervisor prose or discovery-only IDs;
- existing SQL correction, Claim validation, and runtime behavior remain compatible.

The implementation used no additional Tavily request after the diagnostic run. A subsequent
single-task validation should determine whether deterministic formula injection corrects the SQL
calculation and whether the Claim-safe handoff restores accepted Claims and valid report citations.
