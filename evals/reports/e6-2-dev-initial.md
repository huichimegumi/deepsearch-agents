# Shared application v4 evaluation

Internally authored engineering tasks over official RFC snapshots; not an official benchmark score. Snapshot retrieval excludes live web-search reliability. LLM support grades remain provisional.

| Workflow | Completed | Pass | p50 s | p95 s | Requests | Reserved tokens | Known generator tokens | Missing usage cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bounded | 7/16 | 5/16 | 13.68 | 19.469 | 46 | 324965 | 61498 | 7 |

## bounded (e6-2-dev-bounded)

| Case | Category | Runtime | Coverage | Claim support | Pass | Mechanical issues |
| --- | --- | --- | ---: | ---: | --- | --- |
| dev_local_0 | local_document | completed | 1.0 | 1 | True |  |
| dev_local_1 | local_document | error | 0.0 | 1 | False | runtime_not_completed, answerable_task_not_answered |
| dev_local_2 | local_document | error | 0.0 | 1 | False | runtime_not_completed, unanswerable_task_not_refused |
| dev_local_3 | local_document | error | 0.0 | 1 | False | runtime_not_completed, unanswerable_task_not_refused |
| dev_mixed_0 | mixed | degraded | 0.3333333333333333 | 1 | False | runtime_not_completed, answerable_task_not_answered, missing_required_source_citations, missing_executed_sql_web_dependency |
| dev_mixed_1 | mixed | completed | 1.0 | 1 | False | missing_executed_sql_web_dependency |
| dev_mixed_2 | mixed | degraded | 0.375 | 1 | False | runtime_not_completed, answerable_task_not_answered, missing_required_source_citations, missing_executed_sql_web_dependency |
| dev_mixed_3 | mixed | completed | 1.0 | 1 | False | missing_executed_sql_web_dependency |
| dev_sql_0 | sql | completed | 1.0 | 1 | True |  |
| dev_sql_1 | sql | completed | 1.0 | 1 | True |  |
| dev_sql_2 | sql | completed | 1.0 | 1 | True |  |
| dev_sql_3 | sql | completed | 1.0 | 1 | True |  |
| dev_web_0 | web | error | 0.0 | 1 | False | runtime_not_completed, answerable_task_not_answered |
| dev_web_1 | web | error | 0.0 | 1 | False | runtime_not_completed, answerable_task_not_answered |
| dev_web_2 | web | error | 0.16666666666666666 | 1 | False | runtime_not_completed, answerable_task_not_answered |
| dev_web_3 | web | error | 0.0 | 1 | False | runtime_not_completed, answerable_task_not_answered |
