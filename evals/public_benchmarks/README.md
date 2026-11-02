# E7 public-task validation

Selection was frozen before application changes. Run `python -m evals.public_benchmarks.prepare`
for a model-free preflight. There are 12 previously unused DABStep tasks (three per checklist
category), 12 alien Hybrid tasks (four per direction, excluding the three old smoke IDs),
and six DeepResearch Bench tasks (three Chinese/three English). Selection uses a fixed hash
ranking, not observed model success. Only identifiers and hashes are committed.

Reuse the locked DABStep and Hybrid downloads described in their respective directories.
DeepResearch Bench files come from
https://github.com/Ayanami0730/deep_research_bench at
`f2735b5c3636759c22f9e936c0232de8bf545b67`: retain `LICENSE`, `README.md`,
`data/prompt_data/query.jsonl`, and `data/criteria_data/criteria.jsonl` under
`data/benchmarks/deepresearch_bench/<revision>/`. File hashes are in `suite.lock.json`.
A downloader is available with `python -m evals.public_benchmarks.prepare --download-drb`.
Upstream text is not redistributed here. Hybrid canary/decrypted questions, answers, traces
and generated reports remain in ignored local storage. Never include them in public commits.

Both research workflows use DeepSeek non-thinking, CPU, 300 seconds internally/330 seconds
hard deadline, eight model requests/180k estimated reserved tokens, at most five lookups
(and thus at most five free Web queries/ten fetched pages). Each 30-case workflow has a 5.4M
reservation limit. Actual usage and blocked calls are reported separately. Judge runs have
independent 60-request/1.5M-token reservation limits. Final validation runs once per workflow;
interruptions and low scores are retained without research retries. Source code is frozen
before either workflow, with no edits between runs.

Primary results are separated by suite. DABStep checklist coverage is model-judged, not
independent numerical correctness. Hybrid has published result references, permitting
independent value/result checks alongside claim entailment. DRB uses the published criteria
with our custom judge and publishes continuous rubric coverage/citation support. It is NOT
an official RACE/FACT score. Independent-provider judging is optional when credentials are
available; absence of a second judge must be disclosed. Anonymous audit exports permit
later human review without pretending an automated review is human annotation.

Development uses previously exposed DABStep/Hybrid smoke tasks, old RFC development tasks,
and separately authored refusal/partial/tool-error fixtures. The 30 selected public task
outputs must not be used for repair before the final report. Shared data in DABStep/alien
and public questions limit independence. Actual Web failures remain part of end-to-end
results; snapshot or search-result availability must not be substituted for answer quality.

Commands after preflight:

```bash
python -m scripts.evaluate public-prepare --development
python -m scripts.evaluate public-run --inputs evals/results/e7-inputs/development/public.json --output evals/results/my-dev --workflow bounded
python -m scripts.evaluate public-score --run evals/results/my-dev --inputs evals/results/e7-inputs/development --output evals/results/my-dev/score-deepseek
# Only after implementation and scorer are frozen:
python -m scripts.evaluate public-prepare
python -m scripts.evaluate public-run --inputs evals/results/e7-inputs/validation/public.json --output evals/results/my-final --workflow bounded
python -m scripts.evaluate public-score --run evals/results/my-final --inputs evals/results/e7-inputs/validation --output evals/results/my-final/score-deepseek
python -m scripts.evaluate public-score --run evals/results/my-final --inputs evals/results/e7-inputs/validation --output evals/results/my-final/score-qwen --provider qwen --audit-subset
python -m scripts.evaluate public-report --run evals/results/my-final --output evals/reports/my-final.md
```

The Qwen audit deterministically selects two cases per suite, using task IDs before scoring;
it does not override primary grades. Calibration found a false acceptance of a known-but-wrong
citation by Qwen, so provider agreement is diagnostic, not proof. The local anonymous review
export is `python -m evals.public_benchmarks.audit --run <run> --inputs <inputs> --output <new-ignored-directory>`.
Keep its private decoding key separate from reviewer packets; no human review is claimed.
