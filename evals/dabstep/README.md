# DABStep-Research baseline

This directory makes the first data benchmark reproducible without committing upstream raw data.

## What is fixed

- Dataset: `RUC-DataLab/DABStep-Research`
- Revision: `62ae9e0de555a8fb1fd5ab334e0546dbf27aa10c`
- Eight source files: byte size and SHA-256 are recorded in `dataset.lock.json`.
- Task subset: 2 development tasks and 6 holdout tasks in `selected_tasks.jsonl`.
- Reference facts: six read-only SQL query groups in `reference_results.json`.

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
```

`import_sql` accepts any SQLAlchemy database URL. For the project's MySQL service:

```powershell
$env:DABSTEP_DATABASE_URL = 'mysql+mysqlconnector://root:root@localhost:3307/deepsearch_db'
.\.venv\Scripts\python.exe -m evals.dabstep.import_sql
.\.venv\Scripts\python.exe -m evals.dabstep.verify_reference
```

The importer replaces only the ten tables listed in `import_sql.TABLE_ORDER`. Use a dedicated
benchmark database if those names already exist.

## Evaluation boundary

The committed reference results cover source facts such as row counts, amounts, fraud/refusal
rates, merchant joins, card schemes, and domestic/cross-border routing. Exact fee totals are not a
hard reference yet: the snapshot has no authoritative worked example and the manual explains
`null` wildcards but not the empty-list wildcards present in `fees.json`. Reports must disclose
those assumptions instead of presenting an unverified fee total as fact.

Never expose `reference_results.json` to the research agent. It belongs to the offline evaluator.
