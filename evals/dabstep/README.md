# DABStep-Research baseline

This directory makes the first data benchmark reproducible without committing upstream raw data.

## What is fixed

- Dataset: `RUC-DataLab/DABStep-Research`
- Revision: `62ae9e0de555a8fb1fd5ab334e0546dbf27aa10c`
- Eight source files: byte size and SHA-256 are recorded in `dataset.lock.json`.
- Task subset: 2 development tasks and 6 holdout tasks in `selected_tasks.jsonl`.
- Reference facts: six read-only SQL query groups in `reference_results.json`.
- Fee reference: deterministic Decimal calculations, public-dev checks, and independent SQL
  cross-validation in `fee_reference_results.json`.

The upstream repository does not declare a license. Raw files are therefore downloaded into an
ignored directory and must not be redistributed until licensing is clarified. The related source
dataset `adyen/DABstep` declares CC BY 4.0, but that declaration is not assumed to transfer to this
derivative task repository.

## One-command preparation

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m evals.dabstep.prepare
```

This command downloads and verifies the locked files, regenerates the audit artifacts, imports a
local SQLite database, and checks it against the committed reference facts. The raw snapshot is
stored under `data/benchmarks/dabstep_research/<revision>/`; the SQLite database is stored under
`evals/dabstep/work/`. Both are ignored by Git.

Individual steps:

```powershell
.\.venv\Scripts\python.exe -m evals.dabstep.download_dataset
.\.venv\Scripts\python.exe -m evals.dabstep.audit_dataset
.\.venv\Scripts\python.exe -m evals.dabstep.import_sql
.\.venv\Scripts\python.exe -m evals.dabstep.verify_reference
.\.venv\Scripts\python.exe -m evals.dabstep.download_adyen_dev
.\.venv\Scripts\python.exe -m evals.dabstep.validate_fee_engine
```

`import_sql` accepts any SQLAlchemy database URL. For the project's MySQL service:

```powershell
$env:DABSTEP_DATABASE_URL = 'mysql+mysqlconnector://root:root@localhost:3307/deepsearch_db'
.\.venv\Scripts\python.exe -m evals.dabstep.import_sql
.\.venv\Scripts\python.exe -m evals.dabstep.verify_reference
```

The importer replaces only the ten tables listed in `import_sql.TABLE_ORDER`. Use a dedicated
benchmark database if those names already exist.

## Fee Rule Engine

`app/research/fee_engine` is a pure deterministic core with no Pandas, SQL, or LLM dependency. It
uses Decimal arithmetic, derives natural-month merchant volume and fraudulent-volume ratios, and
matches all documented merchant and transaction dimensions. Every fee component includes the fee
rule ID, matched values, wildcard fields, and a `fees.json#ID=<id>` locator.

The engine is checked against six reproducible fee questions in Adyen's public dev split and 500
diverse transactions re-evaluated by an independent SQLite query. Empty lists are treated as
wildcards, consistent with the public answers and Adyen discussion #2. Public task 2697 is retained
as a known upstream inconsistency: its `E:13.57` answer is not reproducible from the documented
per-transaction formula, so it does not count as a hard check.

All 138,236 transactions receive a status. The current snapshot produces 81,772 `MATCHED` and
56,464 `NO_MATCH` results. Reports must disclose unmatched coverage and must not silently turn
`NO_MATCH` into a verified zero fee. Current matched-fee totals are hard evaluator references;
causal claims, conversion effects, and counterfactual savings remain assumption-bound.

## Evaluation boundary

The committed references cover source facts, deterministic rule matching, and currently matched
fees. They do not establish future conversion behavior, causal effects, or the realized savings of
an unobserved routing or fraud intervention.

Never expose `reference_results.json` to the research agent. It belongs to the offline evaluator.
