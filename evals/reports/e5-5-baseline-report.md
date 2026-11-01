# Public benchmark v3 score: benchmark_v3_20261101T121542Z_a4a07448

- Scheduled: 20; terminal: 20; completed: 20; task passes: 10/20.
- Checklist judged: 20/20 DABStep cases.
- Judge: deepseek; median of 3 model judgements per answer; grades are provisional, not human labels.
- Statuses: {'completed': 20}; mean judged checklist coverage: 0.770.
- Latency p50: 26.6s; observed p95: 34.8s.
- Recorded tokens: generator 258519, judge 804056; timeouts can omit in-flight provider usage.
- DABStep pass rule: completed, at least two judge responses, median checklist coverage ≥0.80, evidence-supported coverage ≥0.75, and all cited IDs resolve to this case's Evidence. ID validity is mechanical; support is a provisional model judgement.
- Hybrid three-case subset is an engineering smoke only; DABStep selected holdout was previously exposed.
- No private PDFs, occupied GPU or paid search were used.

| Case | Runtime | Checklist | Supported | Citation IDs | Pass |
| --- | --- | ---: | ---: | ---: | --- |
| dabstep_research_039 | completed | 0.71 | 0.71 | 1.00 | no |
| dabstep_research_022 | completed | 0.38 | 0.38 | 1.00 | no |
| dabstep_research_037 | completed | 0.50 | 0.44 | 1.00 | no |
| dabstep_research_036 | completed | 0.56 | 0.50 | 1.00 | no |
| dabstep_research_030 | completed | 0.79 | 0.79 | 1.00 | no |
| dabstep_research_044 | completed | 0.70 | 0.70 | 1.00 | no |
| dabstep_research_052 | completed | 0.71 | 0.71 | 1.00 | no |
| dabstep_research_053 | completed | 0.67 | 0.67 | 1.00 | no |
| dabstep_research_055 | completed | 0.75 | 0.75 | 1.00 | no |
| dabstep_research_048 | completed | 0.80 | 0.80 | 1.00 | yes |
| dabstep_research_016 | completed | 0.86 | 0.86 | 1.00 | yes |
| dabstep_research_008 | completed | 0.69 | 0.69 | 1.00 | no |
| dabstep_research_001 | completed | 0.92 | 0.92 | 1.00 | yes |
| dabstep_research_009 | completed | 0.92 | 0.92 | 1.00 | yes |
| dabstep_research_011 | completed | 0.92 | 0.92 | 1.00 | yes |
| dabstep_research_094 | completed | 0.95 | 0.95 | 1.00 | yes |
| dabstep_research_087 | completed | 0.95 | 0.95 | 1.00 | yes |
| dabstep_research_086 | completed | 0.86 | 0.86 | 1.00 | yes |
| dabstep_research_096 | completed | 0.90 | 0.90 | 1.00 | yes |
| dabstep_research_088 | completed | 0.88 | 0.88 | 1.00 | yes |

Timeout, error and degraded cases remain in the denominator. Raw attempts are in the ignored results directory.
