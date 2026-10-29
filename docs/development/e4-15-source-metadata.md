# E4.15 — Indexed filename metadata and structural negative controls

E4.14 succeeded on three exposed report tasks but did not establish source-resolution coverage
or general structural precision. This stage addresses the nine unresolved financial questions
and adds separate component challenges. It introduces no generator calls or default promotion.

## Why the nine names failed

The three indexed financial filenames end with `17页` or `63页`; the nine corresponding questions
omit that suffix. The title text otherwise matches under existing Unicode/case/whitespace and
extension normalization. This is not an invitation to infer abbreviations or semantic aliases.

Add an **opt-in indexed-page-suffix key** only when the terminal `N页` matches trusted scoped
`indexed_page_end` metadata. Reject missing/wrong/noninteger metadata, leading-zero suffixes and
`第N页` excerpt naming. Literal full filenames still work independently. Preserve years and all
other title text. If an exact key and a suffix key identify different document hashes, return
ambiguity; do not silently prefer the exact key or choose a document from ranking scores.

The last indexed page is **not proof of the original PDF's total pages**. It only attests the
metadata condition for this narrow filename convention. No semantic PDF title is extracted or
invented. Partially indexed/renamed documents can conservatively remain unresolved.

`resolve_document_sources` and the replay CLI require an explicit suffix opt-in. The existing
experimental live source/structure route enables it using actual database metadata; ordinary
Evidence Tool/API/UI routes remain unchanged. `resolution_methods` distinguishes `exact_filename`
and `indexed_page_suffix` in the plan. Stable Evidence identity and source passages are unchanged.

## Scoped database metadata

The experimental document inventory now reads `MAX(chunk.page_end)` with ready-document and
both document/chunk knowledge-base constraints. A bounded document-ID subquery limits which
documents participate in aggregation before the join (256 plus an overflow sentinel). No body
text is needed for source-name matching, no schema migration/reindex is performed, and the
existing structural-chunk read cap remains unchanged.

An actual PostgreSQL metadata-only run across the authorized ecommerce/finance scope returns
five documents. All filenames, document hashes and indexed last pages match the frozen
five-document/305-chunk snapshot:

| Filename convention | Indexed last page | Newly resolved question IDs |
| --- | ---: | --- |
| BlackRock report + `17页` | 17 | `rag_local_zh_009`–`011` |
| Monetary policy report + `63页` | 63 | `rag_local_zh_012`–`014` |
| CKISS report + `63页` | 63 | `rag_local_zh_015`–`017` |

No global alias table, fuzzy match, author/date deletion or evaluator keypoint enters runtime
resolution. Eight development questions still resolve by exact filename, nine now use the
attested suffix convention, and three have no explicit `《》` source. Thus resolution changes
from **8/20 to 17/20**, or **8/17 to 17/17 among explicitly named-source questions**. This is
component coverage on exposed questions, not semantic answer accuracy.

## Structural negative and ambiguity checks

Fix two demonstrated boundary issues: negatives such as `请先不要生成目录` and `目录不用列` no longer
activate reservation, and decimal spellings `01`/`1` no longer count as distinct numbered TOC
entries. Intent remains a bounded lexical rule, not a general natural-language constraint parser.

The versioned `evals/rag/suites/source_structure_v1.json` contains 21 planner component checks:
positive TOCs, varied negative requests, generic chapter requests, unknown/unquoted names,
wrong years, verified suffix names, duplicate source names, duplicate TOCs, missing structure
and out-of-pool structure. **21/21 final checks match their expected statuses.**

Seventeen checks use the original frozen corpus; four use explicit synthetic perturbations of
copies (duplicate document name, duplicate TOC, excluded candidate TOC, removed corpus TOC).
Original snapshots are never modified. The engine receives only query/corpus/candidate inputs;
expected statuses are checked afterward. Candidate membership starts from the full scoped
corpus, except the deliberate exclusion fixture. These are planner checks, **not live retrieval
precision, independent holdout results or report success rates**. The fixture dataset is authored
for development and is not a general structural benchmark.

The initial 20 checks passed, but replaying the old diagnostic caught a real regression: the
bare negative character `别` matched inside the affirmative word `分别`, suppressing TOC
reservation. That failed diagnostic is preserved as
`source_structure_diagnostic_20261029T033448Z_19a4b32667`. The corrected rule constrains standalone
`别` with a Chinese word boundary and optional courtesy prefixes; `分别列出目录` is now an added
positive challenge while `请先别生成目录` remains negative. The original planner source and initial
challenge dataset are archived, hash-checked, and the pilot's source fingerprint is reconstructed
in the public record. The initial failed diagnostic is not counted as a passing replay.

## Frozen-score replay results

Rerun the 20-case development comparison with exact-only resolution, then with suffix keys,
reusing the same E4.10 raw/context scores. Both runs are valid with unchanged source/input hashes.
The alias-enabled diagnostic replay also keeps the actual TOC delivered first and the survey
reference at its previous position. No new recall, embedding, rerank or generator is performed.

| Format | Exact-only Recall@6 / MRR@6 | Suffix-enabled Recall@6 / MRR@6 | Complete finite units |
| --- | --- | --- | --- |
| Raw | 0.702 / 0.480 | 0.702 / 0.480 | 12/19 in both |
| Source context | 0.754 / 0.592 | 0.754 / 0.592 | 12/19 in both |

Unchanged metrics do not imply unchanged deliveries. Raw-format `009` drops one other-document
chunk and adds one target-document chunk; raw-format `017` drops two other-document chunks,
returning four rather than six hits. Their finite-unit metrics do not change. Context-format
deliveries remain identical. The no-answer case still returns zero hits. Do not report this as
an improvement in recall, Writer fidelity or the earlier customer-service coverage gap.

Actual records:

- Component checks: `structure_challenges_20261029T034253Z_909d0089ae`.
- Exact-only replay: `source_structure_dev_20261029T034254Z_ba8829a2ed`.
- Suffix replay: `source_structure_dev_20261029T034300Z_93ae7ad113`.
- Diagnostic replay: `source_structure_diagnostic_20261029T034305Z_97b91c353a`.
- Live metadata: `source_metadata_20261029T034357Z_a6a61669f6`.

The [public record](../../evals/reports/e4-15-source-metadata-2026-10-29.json) binds manifests,
input/output hashes, method/status counts, per-case metrics, metadata attestation and delivery
changes. Source passages stay private. Human accuracy is null; the prior report success examples
are not rerun or counted as new accepted reports.

## Reproduction and verification

```powershell
# Planner-only challenges; private frozen corpus snapshots required, no services/models.
.venv\Scripts\python.exe -m evals.rag.source_structure_challenges

# Exact-only versus indexed-suffix frozen-score replay.
.venv\Scripts\python.exe -m evals.rag.run_source_structure --execute
.venv\Scripts\python.exe -m evals.rag.run_source_structure --execute --indexed-page-suffix
.venv\Scripts\python.exe -m evals.rag.run_source_structure --diagnostic --execute --indexed-page-suffix
```

Full regression: **651 passed, 6 skipped**, including 53 related cases. New tests cover suffix
attestation/types, exact/alias collision, date preservation, negative request forms, decimal
number deduplication, fixture isolation, scoped SQL last-page aggregation, the live suffix path
and the absence of structural body scans for negated TOC requests. Ruff lint/format and
`git diff --check` pass.

Totals: metadata-only PostgreSQL access plus offline checks/replays, **zero new local RAG
queries, embeddings, reranks, generator calls or Web searches**. Metadata SQL is an actual database
read and is not counted as a RAG query. Next validate the remaining semantic and structure gaps
on a small new task set before exposing a public experimental request option; no default change
is justified by these component checks and the earlier three exposed examples alone.
