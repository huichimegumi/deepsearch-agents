# E5.0 — Public benchmark foundation and CPU-only RAG inference

The former report suite depends on private PDFs that are unavailable on this host. The new
`benchmark_v3` development suite uses only pinned public datasets and keeps the old results as
historical diagnostics. It has eleven IDs: the existing eight selected DABStep-Research tasks and
three HybridDeepResearch routing smoke tasks. The old DABStep holdout was already exposed during
earlier development, so the v3 labels correctly describe it as regression material. The three
Hybrid tasks do not estimate performance on the full 380-task release.

## Assets prepared

Downloaded and byte/hash verified the eight DABStep-Research source files at revision
`62ae9e0de555a8fb1fd5ab334e0546dbf27aa10c`, the Adyen public dev file at revision
`8afcb4ee3df0d73da5e0cddfddfb55665b760169`, and five selected Hybrid/LiteSQL files at
revisions `31304784b7aec82f22d59772a8afeb78567fd8b3` and
`0664a2f28555faa0dd2947c8c23288df79bcc06b`. The DABStep importer built a local
34,533,376-byte SQLite database and reproduced the checked-in SQL and fee-engine references.
These files and the database stay in ignored local directories; decrypted Hybrid text is never
written into tracked files.

The new `evals/benchmark_preflight.py` checks upstream bytes, suite lock and selection hashes,
the prepared DABStep database's reference results, Hybrid decryption checks, and the read-only
Alien SQLite schema. It only emits IDs, hashes and status. The output from this host reported
`ready: true`, 8 DABStep cases, 3 Hybrid cases, and no problems. The existing Hybrid runner's
dry-run also confirmed all three modes with zero search or model calls.

## GPU boundary

At inspection time, GPU 1 had another process using about 9.8 GB; GPUs 2–5 each had another
process using about 22.4 GB; GPU 0 returned a device-handle error. FastEmbed's constructors
default to automatic device selection, so both the embedding and cross-encoder constructors
now request `CPUExecutionProvider` with `cuda=False`. This is an explicit shared-host resource
choice, not an inference-speed comparison. No existing GPU process was altered.

## Reproduction

```bash
.venv/bin/python -m evals.dabstep.prepare
.venv/bin/python -m evals.hybrid.download_dataset
.venv/bin/python -m evals.benchmark_preflight --output evals/results/benchmark_v3_preflight.json
.venv/bin/python -m evals.hybrid.run_smoke --json
```

The first command verifies the source lock before import. On later runs the downloader accepts
matching cached files. The preflight does not run an agent or score answers. DABStep-Research
does not declare a dataset license; its raw files are not redistributed. The Hybrid source
requires decrypted questions, SQL, and answers to stay out of public artifacts.

Focused checks exercise selection tampering and CPU provider arguments. The full offline
pytest suite and Ruff checks must pass before this stage is committed. No end-to-end accuracy
or model-quality claim is made from asset preparation.
