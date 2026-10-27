# E4.1: one measured source-intent fix

E3.8 found that both Web-only tasks returned local no-evidence notices despite having Web Evidence.
Their natural negative constraint against local KB use supplied a local keyword, while an unrelated
Web-only exclusivity phrase supplied the second condition of the old global keyword check. This
stage targets that one runtime defect and preserves the failed E3.8 baseline.

## Change and regression contract

`app/research/source_scope.py` now associates a source mention with the preceding use/prohibition
directive within the same clause. Negative source lists retain their polarity until another
directive or clause. Exclusivity must apply to an affirmed local source. An affirmed additional
Web/SQL/Fee source keeps the general research route. A negative local constraint cannot itself
request mandatory local retrieval. Network-source labels such as 网络搜索 are not interpreted as
new positive commands inside a prohibited-source list. ASCII token boundaries recognize RAG/SQL
next to Chinese text without treating `fragment` or `storage` as a RAG request.
An affirmed local source plus an explicit no-network request also retains local-only behavior,
even without an adjacent exclusivity word.

The existing main-agent helper delegates to this pure classifier. Its consumers keep the existing
behavior: routing instructions, mandatory local lookup, zero-local-Evidence handoff and the
default-off indexed-local experiment all use the same result. Source/Claim/citation validation and
the genuine local-only no-Evidence boundary are not weakened.

This remains a bounded lexical heuristic, not general language understanding or source/tenant ACL
enforcement. Quoted instructions, conditionals, contradictions, unseen paraphrases and languages
outside the recognized vocabulary can still be misinterpreted. No model-generated intent label,
task ID, reference answer, release number or source URL is used in classification. Other broad
document-first hints in the main agent are unchanged.

Thirty-five new source-scope tests cover negative local requests, affirmative local-only requests,
negative other-source lists, source combinations, clause separation and Chinese/English RAG/SQL
forms. They include the unmodified four frozen extended questions, six original local prompts and
a workflow test proving that actual registered synthetic Web Evidence reaches compression/Writer
without mandatory local lookup. This does not substitute for the real two-task comparison below.
Source association also distinguishes later topic mentions (such as 网络安全 or SQL优化) from
additional source requests, while allowing a KB-name parenthesis before an actual source-list join.

The extended runner adds an explicit `--case-id` subset selector. Unknown, empty and duplicate
selections are rejected; frozen dataset order is retained. Limits do not change. Four added tests
check selection integrity and the two Web tasks' identical three-query/three-page allowances.

## Fixed comparison protocol

Reuse E3.8's original task file and asset lock, including primary-reference snapshots, corpus,
SQLite bytes and independent references. Keep `qwen-flash`, the default researcher, 300-second
profile, configured 12-call allowance, 75-second Writer reserve and 330-second outer watchdog.
Only original Web 001/002 are rerun once each; their questions and reference units are not edited.
Each retains three search queries and three pages, for a new batch ceiling of six. It is a
separate bounded batch from E3.8's nine admitted queries, not unused-capacity recycling.

```powershell
.venv\Scripts\python.exe -m evals.reports_acceptance.extended --lock evals/results/extended_assets_20261027T052916Z_6051bf3cf6/lock.json --case-id report_web_001 --case-id report_web_002
.venv\Scripts\python.exe -m evals.reports_acceptance.extended --lock evals/results/extended_assets_20261027T052916Z_6051bf3cf6/lock.json --case-id report_web_001 --case-id report_web_002 --execute --allow-paid-search
```

The primary measured outcome is whether mandatory local-only routing stops bypassing synthesis of
available Web Evidence. Check `local_retrieval.required`, actual mandatory lookup counts, phase
model-call counts and final delivered content. Separately review answers, references, citation
repair and remaining failures. One run per question, live search variation and provider conditions
do not establish general answer accuracy, stable latency or an isolated performance gain.

## Real before/after execution

Before: E3.8 `extended_reports_20261027T053213Z_967bc25670`, selecting its original two Web rows.
After preflight: `extended_reports_20261027T055917Z_27db725ded`.
After execution: `extended_reports_20261027T055936Z_09f89e8bc9`.
The after run records HEAD `f1911aa8` plus this stage's working changes and exact source fingerprint.
It is not described as a clean prior release. Both original run journals and all artifact hashes
are retained. The task-file hash, asset-lock bytes, configured model name and per-case limits
match; the after run ends with `inputs_unchanged=true`.

| Variant | Case | Local-only flag | Mandatory local requests | Compression / Writer model calls | Seconds | Delivery |
| --- | --- | --- | ---: | --- | ---: | --- |
| E3.8 before | Web 001 | true | 1 | 0 / 0 | 161.219 | local notice inside citation fallback |
| E4.1 after | Web 001 | false | 0 | 1 / 1 | 101.375 | Claim fallback; backend citation validation still false |
| E3.8 before | Web 002 | true | 1 | 0 / 0 | 56.343 | local notice inside citation fallback |
| E4.1 after | Web 002 | false | 0 | 1 / 1 | 50.907 | report body |

The targeted erroneous flag is removed on **2/2 observed development cases**, and both cases now
actually invoke compression and Writer with collected Web Evidence. This is a measured routing/
handoff correction, not a general routing-accuracy score. Both after runs remain **degraded**:
Web 001 has final citation-validation failure; Web 002 retains
`subagent_retrieval_budget_exhausted`. Neither task receives a semantic acceptance label.

Each after case admits three Tavily queries and three pages: this new batch uses **6 queries,
6 pages**. The before Web subset also used six queries/six pages. E3.8's complete four-case batch
used nine queries; those nine and this new six remain separate records (15 combined across those
two batches). No further query, repeat generation or project Judge request was made for initial
review. Recorded LLM calls change from 2/6 to 9/6 because the previously skipped model stages
now execute; nested/provider usage remains incompletely metered. No billing or general speedup
claim is made from the observed times.

## Content still needs improvement

The independent AI initial review finds both answers **partial**:

- **Python:** release date and experimental state are now answered, but a compressed inference
  claims users cannot explicitly select the free-threaded build. The retrieved release page does
  not establish that negative, and the frozen
  [official installation instructions](https://docs.python.org/3.13/howto/free-threading-python.html)
  explicitly describe optional free-threaded installation. The fallback also speculates about
  absent future official plans and invents a past cutoff date unrelated to the task. Its Writer
  cites unapproved IDs; the returned Claim package's outline still fails backend Claim-scoped
  citation validation. That existing fallback weakness is preserved as a failure, not silently
  repaired in this source-intent experiment.
- **PostgreSQL:** the delivered report answers the date and JSON_TABLE capability, then wrongly
  says `pg_combinebackup` is unconfirmed as an official component. The actual bounded official
  release-note text lacks that name, which cannot prove absence from all official material. The
  frozen [official release announcement](https://www.postgresql.org/about/news/postgresql-17-released-2936/)
  explicitly includes the utility. It also attributes the tool description to a pgEdge article
  whose actual retrieved text does not mention the utility. The complete backup reference unit
  remains unretrieved under the same three-page budget.

Finite reference units retrieved/cited change from 3/3 and 0/3 to 3/3 and 3/3 for Python, and from
2/3 and 0/3 to 2/3 and 2/3 for PostgreSQL. The Python installation conclusion is still wrong despite
complete anchor citation. Both final documents cite registered IDs, but Python's backend citation
check remains false because its fallback includes a registered ID outside the approved Claim ID
set. These measures therefore must not substitute for entailment or answer correctness.

The AI worksheet at `evals/results/e4-1-ai-triage-20261027/AI_REVIEW.md` contains checked report
quotations and clearly distinguishes actually retrieved Evidence from evaluator-only frozen
reference passages. It is selective, provisional AI work; no human attestation is generated.
Human accuracy and Claim-support rates remain null.

## Verification and next work

The old classifier is independently loaded from the reviewed `f1911aa8` function for a pure offline
predicate comparison. Both Web questions change true → false; both mixed-source questions remain
false; all six frozen local prompts remain true. The synthetic end-to-end test additionally proves
the corrected Web path can deliver a cited answer. This classification preservation is not a fresh
six-local-task generation experiment or a new holdout result.

Full regression: **487 passed, 6 skipped**. The 39 added tests comprise 35 source-scope/workflow
cases and four subset-selection cases. Changed-file Ruff lint/format and `git diff --check` pass.
Both selected before/after report/Evidence/Trace hashes, actual Markdown artifacts, matched limits,
source fingerprints, asset references, and AI-review quotations are verified. The
[content-free record](../../evals/reports/e4-1-source-intent-2026-10-27.json) retains the separate
manifests, exact counts, citation distinctions and failed quality outcomes.

During final code review, a topic/source regression was found in the first clause-bound version:
an unrequested later topic word could be treated as another source. The final revision tightens
association to actual use-directive/source-list positions and adds five regression cases. This
revision was made after the live pilot. Its original `source_scope.py` is preserved privately at
`evals/results/source_intent_pilot_20261027/source_scope.py`; substituting its hash reconstructs
the recorded pilot source fingerprint exactly. Pilot and final classifiers return identical
branches on all ten frozen questions. Final full regression and the workflow test use the final
code; no extra model/search rerun is presented as though it used the final source snapshot.

The single targeted E4.1 runtime improvement is complete. Next, use the saved Evidence and typed
Claims to investigate unsupported compression inferences and the invalid citation fallback,
without making more Web retrieval a prerequisite. Keep these failures and the original task
definitions available for subsequent fixed-input regression; do not extend this result to a
general factual-accuracy or product-readiness claim.
