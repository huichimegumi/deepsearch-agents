# Public benchmark v3 score: benchmark_v3_20261101T050247Z_1a4e024b

- Scheduled: 6; terminal: 6; completed: 6; task passes: 4/6.
- Checklist judged: 6/6 DABStep cases.
- Judge: deepseek; median of 3 model judgements per answer; grades are provisional, not human labels.
- Statuses: {'completed': 6}; mean judged checklist coverage: 0.765.
- Latency p50: 27.6s; observed p95: 34.4s.
- Recorded tokens: generator 75995, judge 236197; timeouts can omit in-flight provider usage.
- DABStep pass rule: completed, at least two judge responses, median checklist coverage ≥0.80, evidence-supported coverage ≥0.75, and all cited IDs resolve to this case's Evidence. ID validity is mechanical; support is a provisional model judgement.
- Hybrid three-case subset is an engineering smoke only; DABStep selected holdout was previously exposed.
- No private PDFs, occupied GPU or paid search were used.

| Case | Runtime | Checklist | Supported | Citation IDs | Pass |
| --- | --- | ---: | ---: | ---: | --- |
| dabstep_research_002 | completed | 0.83 | 0.83 | 1.00 | yes |
| dabstep_research_084 | completed | 1.00 | 1.00 | 1.00 | yes |
| dabstep_research_000 | completed | 1.00 | 1.00 | 1.00 | yes |
| dabstep_research_003 | completed | 0.86 | 0.86 | 1.00 | yes |
| dabstep_research_020 | completed | 0.50 | 0.50 | 1.00 | no |
| dabstep_research_041 | completed | 0.40 | 0.40 | 1.00 | no |

Timeout, error and degraded cases remain in the denominator. Raw attempts are in the ignored results directory.
