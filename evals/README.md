# Project Evals

This directory contains the first-phase internal Chinese evaluation set for DeepSearch Agents.
It intentionally excludes local knowledge-base QA samples.

## Datasets

- `datasets/web_research_zh.jsonl`: 20 web-search QA tasks.
- `datasets/db_query_zh.jsonl`: 20 MySQL business-data query tasks.
- `datasets/routing_boundary_zh.jsonl`: 20 routing, refusal, and boundary tasks.
- `datasets/end_to_end_report_zh.jsonl`: 10 end-to-end report-generation tasks.
- `datasets/rag_local_zh.jsonl`: 20 local knowledge-base retrieval QA tasks.

## Shared Schema

Each JSONL row uses these core fields:

- `id`: Stable sample id.
- `category`: One of `web_research`, `db_query`, `routing_boundary`, `end_to_end_report`.
- `task`: User-facing Chinese prompt.
- `expected_route`: Expected high-level agent/tool route.
- `disallowed_routes`: Routes that should not be used.
- `success_criteria` or `answer_checks`: Human-readable checks for pass/fail.

Some datasets add extra fields:

- Web samples include `expected_source_types`, `freshness`, and `answer_checks`.
- DB samples include `gold_sql` and `answer_checks`.
- Routing/boundary samples include `boundary_type`.
- Report samples include `required_sections` and `artifact_expectation`.

## Route Names

Use these canonical route labels in eval runners:

- `network_search`
- `database_query`
- `knowledge_base`
- `file_read`
- `memory`
- `report_generation`
- `direct_answer`
- `refusal`

## First Metrics To Implement

- Route accuracy.
- Disallowed-route violation rate.
- Web source coverage and freshness.
- DB SQL intent match and result correctness.
- Report section coverage and citation/source preservation.
