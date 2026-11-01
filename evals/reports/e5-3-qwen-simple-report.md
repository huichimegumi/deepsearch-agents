# Public benchmark v3 score: benchmark_v3_20261101T050602Z_51b95ca9

- Scheduled: 6; terminal: 6; completed: 6; task passes: 3/6.
- Checklist judged: 6/6 DABStep cases.
- Judge: deepseek; median of 3 model judgements per answer; grades are provisional, not human labels.
- Statuses: {'completed': 6}; mean judged checklist coverage: 0.768.
- Latency p50: 42.7s; observed p95: 47.8s.
- Recorded tokens: generator 78406, judge 227494; timeouts can omit in-flight provider usage.
- DABStep pass rule: completed, at least two judge responses, median checklist coverage ≥0.80, evidence-supported coverage ≥0.75, and all cited IDs resolve to this case's Evidence. ID validity is mechanical; support is a provisional model judgement.
- Hybrid three-case subset is an engineering smoke only; DABStep selected holdout was previously exposed.
- No private PDFs, occupied GPU or paid search were used.

| Case | Runtime | Checklist | Supported | Citation IDs | Pass |
| --- | --- | ---: | ---: | ---: | --- |
| dabstep_research_002 | completed | 0.83 | 0.83 | 1.00 | yes |
| dabstep_research_084 | completed | 0.89 | 0.89 | 1.00 | yes |
| dabstep_research_000 | completed | 1.00 | 1.00 | 1.00 | yes |
| dabstep_research_003 | completed | 0.79 | 0.71 | 1.00 | no |
| dabstep_research_020 | completed | 0.50 | 0.50 | 1.00 | no |
| dabstep_research_041 | completed | 0.60 | 0.60 | 1.00 | no |

Timeout, error and degraded cases remain in the denominator. Raw attempts are in the ignored results directory.
