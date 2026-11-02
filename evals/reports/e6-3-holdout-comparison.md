# Shared application v4 evaluation

Internally authored engineering tasks over official RFC snapshots; not an official benchmark score. Snapshot retrieval excludes live web-search reliability. LLM support grades remain provisional.

| Workflow | Completed | Pass | p50 s | p95 s | Requests | Reserved tokens | Known generator tokens | Missing usage cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| simple | 22/24 | 20/24 | 13.13 | 15.166 | 48 | 301929 | 133944 | 0 |
| bounded | 22/24 | 22/24 | 14.56 | 17.223 | 72 | 488560 | 225552 | 0 |

Original simple passes: 19; judge-error-only retries: 1; unresolved: 0. Research was not rerun; original score artifacts are retained.


## simple (e6-3-holdout-simple)

| Case | Category | Runtime | Coverage | Claim support | Pass | Mechanical issues |
| --- | --- | --- | ---: | ---: | --- | --- |
| holdout_local_0 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_1 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_2 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_3 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_4 | local_document | delivery_invalid | 0.0 | 1 | False | runtime_not_completed, unanswerable_task_not_refused |
| holdout_local_5 | local_document | delivery_invalid | 0.0 | 1 | False | runtime_not_completed, unanswerable_task_not_refused |
| holdout_mixed_0 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_1 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_2 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_3 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_4 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_5 | mixed | completed | 1.0 | 1 | True |  |
| holdout_sql_0 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_1 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_2 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_3 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_4 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_5 | sql | completed | 1.0 | 1 | True |  |
| holdout_web_0 | web | completed | 1.0 | 0.8888888888888888 | False |  |
| holdout_web_1 | web | completed | 1.0 | 1 | True |  |
| holdout_web_2 | web | completed | 1.0 | 1 | True |  |
| holdout_web_3 | web | completed | 1.0 | 1 | False | answerable_task_not_answered |
| holdout_web_4 | web | completed | 1.0 | 1 | True |  |
| holdout_web_5 | web | completed | 1.0 | 1 | True |  |

## bounded (e6-3-holdout-bounded)

| Case | Category | Runtime | Coverage | Claim support | Pass | Mechanical issues |
| --- | --- | --- | ---: | ---: | --- | --- |
| holdout_local_0 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_1 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_2 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_3 | local_document | completed | 1.0 | 1 | True |  |
| holdout_local_4 | local_document | degraded | 1.0 | 1 | False | runtime_not_completed |
| holdout_local_5 | local_document | degraded | 1.0 | 1 | False | runtime_not_completed |
| holdout_mixed_0 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_1 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_2 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_3 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_4 | mixed | completed | 1.0 | 1 | True |  |
| holdout_mixed_5 | mixed | completed | 1.0 | 1 | True |  |
| holdout_sql_0 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_1 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_2 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_3 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_4 | sql | completed | 1.0 | 1 | True |  |
| holdout_sql_5 | sql | completed | 1.0 | 1 | True |  |
| holdout_web_0 | web | completed | 1.0 | 1 | True |  |
| holdout_web_1 | web | completed | 1.0 | 1 | True |  |
| holdout_web_2 | web | completed | 1.0 | 1 | True |  |
| holdout_web_3 | web | completed | 1.0 | 1 | True |  |
| holdout_web_4 | web | completed | 1.0 | 1 | True |  |
| holdout_web_5 | web | completed | 1.0 | 1 | True |  |
