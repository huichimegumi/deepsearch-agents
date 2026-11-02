# Shared research evaluation v4

Run commands from the repository root with the project Python environment. The checks,
snapshot retrieval, SQLite and source adapters use CPU. These are internally authored
engineering tasks over public RFC sources, with source-disjoint development and validation
documents; they are not an official benchmark leaderboard. Live Web availability is measured
separately. The original DABStep v3 reports retain their original scoring version.

```bash
uv sync --frozen --group dev
uv run python -m scripts.evaluate check
uv run python -m scripts.evaluate prepare
uv run python -m scripts.evaluate run --split dev --workflow bounded --output evals/results/my-dev --score
```

`prepare` verifies the source lock before use. It preserves unmodified RFC texts and metadata
in ignored `data/benchmarks/standards_v4/` and reconstructs the SQLite files. It does not need
a model key. A changed upstream file is rejected against the lock instead of silently
refreshing the corpus. To reproduce a historical run, use that run's recorded Git revision,
source fingerprint and lock; a later implementation intentionally cannot resume its workers.

`run` and `score` call DeepSeek and require `DEEPSEEK_API_KEY` in the environment or local
`.env`. They disable automatic transport retries. `simple` performs planning/collection and
one Writer; `bounded` also performs one gap check and optional lookup. Both call the same
application implementation used by `/api/task` when bounded research is enabled. Only
public task projections reach workers. Hidden reference values and checklists reach only
the scorer.

Each case has an isolated worker and hard deadline of 210 seconds; internal execution
uses 180 seconds. Its request budget admits at most 8 requests and 180k estimated reserved
tokens, retaining one final request and 32k reserved tokens for delivery. A batch reserves at
most 2M tokens across workers. The judge has a separate ledger with at most 100 requests
and 1M estimated reserved tokens. These reservations are estimates, not provider invoices.
Missing actual usage is reported as unknown. Failed and interrupted cases remain scheduled.

Rerunning `run` with the same output directory resumes missing cases, preserving terminal
results and refusing changed input/code. Interrupted attempts are retained instead of
silently repeating possibly paid calls. Scoring checkpoints save every judge reply and
every finished case, so scoring can continue without rerunning research:

```bash
uv run python -m scripts.evaluate score --run evals/results/my-dev
uv run python -m scripts.evaluate audit --run evals/results/my-dev
uv run python -m scripts.evaluate report --run evals/results/my-dev --output evals/reports/my-dev.md
```

`audit` makes no model calls and reports only mechanical checks, not task passes. Semantic
claim support and checklist grades remain provisional model judgements. A known source ID
does not establish entailment. The renderer checks structured numeric fields against source
paths; the independent scorer additionally checks task reference values. Arbitrary numeric
prose is still subject to semantic review.

An independent comparison uses the already-frozen holdout once, with the same code and
budgets for both workflows:

```bash
uv run python -m scripts.evaluate run --split holdout --workflow bounded --output evals/results/my-final --score
uv run python -m scripts.evaluate run --split holdout --workflow simple --output evals/results/my-baseline --score
uv run python -m scripts.evaluate report --run evals/results/my-baseline --run evals/results/my-final --output evals/reports/my-comparison.md
```

The holdout in this repository has already been used for the E6 report. It is now regression
material; a future tuned implementation needs new validation sources/questions. Both flows
share the complete source catalog; no per-case good evidence is injected. The report tool
rejects differing source, question, database, model or budget configuration. Publication
includes per-case failures and does not exclude missing grades from task denominators.

For the actual API, `RESEARCH_WORKFLOW=bounded` opts in globally; a task can also specify a
configured source list such as `sources:["sql"]`. Legacy remains the compatibility default
until the application release decision. API smoke exercises the HTTP handler, shared model
executor and real SQLite, replacing identity/conversation storage for isolation:

```bash
uv run python -m evals.api_smoke_v4 --output evals/results/my-api-smoke
uv run python -m scripts.probe_live_web --output evals/reports/my-live-web.json
```

The Web probe makes four free DuckDuckGo queries and no model calls; it publishes fetched
page availability, never folds these outcomes into snapshot task quality. CI runs portable
offline fault/contract tests on Linux and Windows. Real API calls require an explicit manual
workflow input and repository secret. Raw provider responses, source excerpts and rejected candidates
remain local artifacts; the RFC task questions themselves are original authored fixtures.

The E7 public-task extension is documented in
[public benchmark protocol](../evals/public_benchmarks/README.md). Use the `public-*`
subcommands in the same CLI for the separate DABStep, Hybrid and DRB results. E7 replaces
neither historical RFC scores nor official upstream scoring. The frozen E7 30-task validation
is consumed after its first report; subsequent tuning requires a new validation selection.
`python -m evals.api_smoke_v4 --web --output <directory>` additionally exercises actual free
Web retrieval and HTTP report delivery, with the same isolated identity/storage limitations
as the SQL smoke. It is a connectivity/delivery check, not a semantic quality score.
