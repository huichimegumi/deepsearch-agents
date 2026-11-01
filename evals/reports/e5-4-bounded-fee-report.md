# Public benchmark v3 score: benchmark_v3_20261101T115306Z_3a9669ef

- Scheduled: 8; terminal: 8; completed: 8; task passes: 7/8.
- Checklist judged: 8/8 DABStep cases.
- Judge: deepseek; median of 3 model judgements per answer; grades are provisional, not human labels.
- Statuses: {'completed': 8}; mean judged checklist coverage: 0.922.
- Latency p50: 27.0s; observed p95: 30.3s.
- Recorded tokens: generator 134802, judge 414189; timeouts can omit in-flight provider usage.
- DABStep pass rule: completed, at least two judge responses, median checklist coverage ≥0.80, evidence-supported coverage ≥0.75, and all cited IDs resolve to this case's Evidence. ID validity is mechanical; support is a provisional model judgement.
- Hybrid three-case subset is an engineering smoke only; DABStep selected holdout was previously exposed.
- No private PDFs, occupied GPU or paid search were used.

| Case | Runtime | Checklist | Supported | Citation IDs | Pass |
| --- | --- | ---: | ---: | ---: | --- |
| dabstep_research_002 | completed | 0.92 | 0.92 | 1.00 | yes |
| dabstep_research_084 | completed | 1.00 | 1.00 | 1.00 | yes |
| dabstep_research_000 | completed | 1.00 | 1.00 | 1.00 | yes |
| dabstep_research_003 | completed | 0.93 | 0.93 | 1.00 | yes |
| dabstep_research_020 | completed | 0.71 | 0.71 | 1.00 | no |
| dabstep_research_041 | completed | 0.90 | 0.90 | 1.00 | yes |
| dabstep_research_047 | completed | 0.92 | 0.92 | 1.00 | yes |
| dabstep_research_085 | completed | 1.00 | 1.00 | 1.00 | yes |

Timeout, error and degraded cases remain in the denominator. Raw attempts are in the ignored results directory.
