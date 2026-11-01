# Shared application v4 evaluation

Internally authored engineering tasks over official RFC snapshots; not an official benchmark score. Snapshot retrieval excludes live web-search reliability. LLM support grades remain provisional.

| Workflow | Completed | Pass | p50 s | p95 s | Requests | Reserved tokens | Known generator tokens | Missing usage cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bounded | 14/16 | 11/16 | 13.71 | 17.563 | 48 | 345044 | 166052 | 0 |

## bounded (e6-2-dev-repaired)

| Case | Category | Runtime | Coverage | Claim support | Pass | Mechanical issues |
| --- | --- | --- | ---: | ---: | --- | --- |
| dev_local_0 | local_document | completed | 1.0 | 1 | True |  |
| dev_local_1 | local_document | completed | 1.0 | 1 | True |  |
| dev_local_2 | local_document | degraded | 1.0 | 1 | False | runtime_not_completed, unanswerable_task_not_refused |
| dev_local_3 | local_document | completed | 1.0 | 1 | False | unanswerable_task_not_refused |
| dev_mixed_0 | mixed | completed | 1.0 | 1 | True |  |
| dev_mixed_1 | mixed | completed | 0.75 | 0.8 | False |  |
| dev_mixed_2 | mixed | completed | 1.0 | 0.8888888888888888 | False |  |
| dev_mixed_3 | mixed | completed | 1.0 | 1 | True |  |
| dev_sql_0 | sql | completed | 1.0 | 1 | True |  |
| dev_sql_1 | sql | completed | 1.0 | 1 | True |  |
| dev_sql_2 | sql | completed | 1.0 | 1 | True |  |
| dev_sql_3 | sql | completed | 1.0 | 1 | True |  |
| dev_web_0 | web | completed | 1.0 | 1 | True |  |
| dev_web_1 | web | completed | 1.0 | 1 | True |  |
| dev_web_2 | web | degraded | 0.6666666666666666 | 0.8888888888888888 | False | runtime_not_completed, answerable_task_not_answered |
| dev_web_3 | web | completed | 1.0 | 1 | True |  |
