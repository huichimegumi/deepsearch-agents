# E7 public-task validation

CPU; live free Web; all scheduled failures retained. Custom provisional judges.

| Workflow | Suite | Completed | Task passes | Coverage¹ | Citation support² | Judged |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| simple | dabstep | 11/12 | 0/12 | 0.382 | 0.941 | 12/12 |
| simple | drb | 5/6 | continuous score | 0.162 | 1.000 | 6/6 |
| simple | hybrid | 10/12 | 0/12 | 0.104 | 0.875 | 12/12 |
| bounded | dabstep | 11/12 | 0/12 | 0.398 | 0.935 | 12/12 |
| bounded | drb | 5/6 | continuous score | 0.370 | 0.967 | 6/6 |
| bounded | hybrid | 11/12 | 0/12 | 0.167 | 0.681 | 12/12 |

¹ Uniform checklist mean across all scheduled cases, missing grades count zero; published weighted DRB rubric scores are separately recorded in JSON.
² Mean across valid graded claim sets; scoped empty refusals have no claim support score. Read with coverage, runtime and pass gates.

| Workflow | Requests | Reserved tokens | Known generator tokens | Missing usage cases | p50 / p95 seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| simple | 65 | 974626 | 733707 | 1 | 23.387 / 42.285 |
| bounded | 97 | 1743309 | 1410074 | 0 | 28.213 / 57.005 |

Latency percentiles exclude unknown/interrupted durations; all scheduled tasks remain in pass denominators.

## Limits

- DABStep shares source data with prior work; checklist judgements are not independently verified numeric correctness
- Hybrid is alien-only and public task selection is not an external blind evaluation
- Live Web responses can differ across sequential workflow runs
- DRB six-task subset uses custom judges and limited retrieval budget; not official RACE/FACT
- Independent Qwen judge is a small audit; failed judge calls are not valid agreement
- Human review packets exported locally; human review not performed

## simple per-case results

| Case ID | Suite | Runtime | Pass | Coverage | Support | Issues |
| --- | --- | --- | --- | ---: | ---: | --- |
| dabstep:31 | dabstep | completed | False | 0.429 | 0.818 | answerable_task_not_answered, duplicate_metric |
| dabstep:25 | dabstep | completed | False | 0.500 | 1.000 | answerable_task_not_answered, duplicate_metric |
| dabstep:21 | dabstep | completed | False | 0.300 | 1.000 | answerable_task_not_answered |
| dabstep:45 | dabstep | completed | False | 0.500 | 0.917 | answerable_task_not_answered, duplicate_metric |
| dabstep:40 | dabstep | completed | False | 0.500 | 1.000 | answerable_task_not_answered, duplicate_metric |
| dabstep:50 | dabstep | completed | False | 0.500 | 0.909 | answerable_task_not_answered, duplicate_metric |
| dabstep:12 | dabstep | delivery_invalid | False | 0.000 | 1.000 | answerable_task_not_answered, runtime_not_completed |
| dabstep:19 | dabstep | completed | False | 0.583 | 1.000 | answerable_task_not_answered |
| dabstep:14 | dabstep | completed | False | 0.429 | 0.857 | answerable_task_not_answered |
| dabstep:93 | dabstep | completed | False | 0.375 | 0.889 | answerable_task_not_answered |
| dabstep:97 | dabstep | completed | False | 0.389 | 1.000 | answerable_task_not_answered |
| dabstep:81 | dabstep | completed | False | 0.077 | 0.900 | answerable_task_not_answered |
| hybrid:s2sql_046 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:s2sql_050 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:s2sql_048 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:s2sql_017 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:sql2s_088 | hybrid | completed | False | 0.250 | 1.000 | answerable_task_not_answered, independent_sql_or_direction_check_failed |
| hybrid:sql2s_128 | hybrid | delivery_invalid | False | 0.250 | 1.000 | answerable_task_not_answered, independent_sql_or_direction_check_failed, missing_required_source_citations, runtime_not_completed |
| hybrid:sql2s_191 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:sql2s_022 | hybrid | interrupted | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations, runtime_not_completed |
| hybrid:parallel_040 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:parallel_085 | hybrid | completed | False | 0.250 | 1.000 | answerable_task_not_answered, independent_sql_or_direction_check_failed |
| hybrid:parallel_032 | hybrid | completed | False | 0.250 | 0.500 | answerable_task_not_answered, duplicate_metric, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:parallel_006 | hybrid | completed | False | 0.250 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| drb:16 | drb | completed | None | 0.096 | N/A | answerable_task_not_answered, empty_answer |
| drb:23 | drb | completed | None | 0.254 | 1.000 | answerable_task_not_answered |
| drb:3 | drb | delivery_invalid | None | 0.040 | 1.000 | answerable_task_not_answered, runtime_not_completed |
| drb:81 | drb | completed | None | 0.000 | 1.000 | answerable_task_not_answered |
| drb:87 | drb | completed | None | 0.200 | 1.000 | answerable_task_not_answered |
| drb:54 | drb | completed | None | 0.385 | 1.000 | answerable_task_not_answered |

## bounded per-case results

| Case ID | Suite | Runtime | Pass | Coverage | Support | Issues |
| --- | --- | --- | --- | ---: | ---: | --- |
| dabstep:31 | dabstep | completed | False | 0.500 | 1.000 | answerable_task_not_answered, duplicate_metric |
| dabstep:25 | dabstep | completed | False | 0.500 | 0.917 | answerable_task_not_answered |
| dabstep:21 | dabstep | completed | False | 0.300 | 0.800 | answerable_task_not_answered, duplicate_metric |
| dabstep:45 | dabstep | delivery_invalid | False | 0.000 | 1.000 | answerable_task_not_answered, runtime_not_completed |
| dabstep:40 | dabstep | completed | False | 0.500 | 1.000 | answerable_task_not_answered, duplicate_metric |
| dabstep:50 | dabstep | completed | False | 0.458 | 0.909 | answerable_task_not_answered, duplicate_metric |
| dabstep:12 | dabstep | completed | False | 0.800 | 1.000 | answerable_task_not_answered |
| dabstep:19 | dabstep | completed | False | 0.750 | 1.000 | answerable_task_not_answered |
| dabstep:14 | dabstep | completed | False | 0.429 | 0.600 | answerable_task_not_answered |
| dabstep:93 | dabstep | completed | False | 0.000 | 1.000 | answerable_task_not_answered |
| dabstep:97 | dabstep | completed | False | 0.500 | 1.000 | answerable_task_not_answered, duplicate_metric |
| dabstep:81 | dabstep | completed | False | 0.038 | 1.000 | answerable_task_not_answered |
| hybrid:s2sql_046 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:s2sql_050 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:s2sql_048 | hybrid | delivery_invalid | False | 0.000 | 1.000 | answerable_task_not_answered, independent_sql_or_direction_check_failed, missing_required_source_citations, runtime_not_completed |
| hybrid:s2sql_017 | hybrid | completed | False | 0.250 | 0.167 | answerable_task_not_answered, independent_sql_or_direction_check_failed |
| hybrid:sql2s_088 | hybrid | completed | False | 0.250 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:sql2s_128 | hybrid | completed | False | 0.250 | 0.750 | answerable_task_not_answered, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:sql2s_191 | hybrid | completed | False | 0.000 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:sql2s_022 | hybrid | completed | False | 0.250 | 0.500 | answerable_task_not_answered, duplicate_metric, independent_sql_or_direction_check_failed |
| hybrid:parallel_040 | hybrid | completed | False | 0.250 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:parallel_085 | hybrid | completed | False | 0.250 | 0.667 | answerable_task_not_answered, independent_sql_or_direction_check_failed |
| hybrid:parallel_032 | hybrid | completed | False | 0.250 | N/A | answerable_task_not_answered, empty_answer, independent_sql_or_direction_check_failed, missing_required_source_citations |
| hybrid:parallel_006 | hybrid | completed | False | 0.250 | 1.000 | answerable_task_not_answered, independent_sql_or_direction_check_failed |
| drb:16 | drb | completed | None | 0.481 | 1.000 | answerable_task_not_answered |
| drb:23 | drb | delivery_invalid | None | 0.000 | 1.000 | answerable_task_not_answered, runtime_not_completed |
| drb:3 | drb | completed | None | 0.120 | N/A | answerable_task_not_answered, empty_answer |
| drb:81 | drb | completed | None | 0.640 | 1.000 | answerable_task_not_answered |
| drb:87 | drb | completed | None | 0.500 | 1.000 | answerable_task_not_answered |
| drb:54 | drb | completed | None | 0.481 | 0.833 | answerable_task_not_answered |
