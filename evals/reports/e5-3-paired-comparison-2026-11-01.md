# Six-case paired model and workflow comparison

All six simple-flow cases received byte-identical SQL Evidence across models.
The cases are public SQL tasks already exposed during development, not a new holdout.

| Profile | Workflow | Terminal | Completed | Pass | Median seconds | Reserved tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| deepseek | agent | 6 | 0 | 0 | 33.1 | 899548 |
| deepseek | simple_sql | 6 | 6 | 4 | 27.6 | 102753 |
| qwen | agent | 6 | 0 | 0 | 54.1 | 968193 |
| qwen | simple_sql | 6 | 6 | 3 | 42.7 | 102753 |

| Case | DeepSeek simple | Qwen simple | DeepSeek agent | Qwen agent |
| --- | ---: | ---: | ---: | ---: |
| dabstep_research_002 | completed / 0.83 | completed / 0.83 | budget_exhausted | budget_exhausted |
| dabstep_research_084 | completed / 1.00 | completed / 0.89 | budget_exhausted | budget_exhausted |
| dabstep_research_000 | completed / 1.00 | completed / 1.00 | budget_exhausted | budget_exhausted |
| dabstep_research_003 | completed / 0.86 | completed / 0.79 | budget_exhausted | budget_exhausted |
| dabstep_research_020 | completed / 0.50 | completed / 0.50 | budget_exhausted | budget_exhausted |
| dabstep_research_041 | completed / 0.40 | completed / 0.60 | budget_exhausted | budget_exhausted |

Pass requires completed execution as well as checklist and citation thresholds. A missing checklist score means no scorable answer; it is never removed from the denominator.
The same DeepSeek model judged both generators, so judge preference and variance remain limitations.
