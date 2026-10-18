# Evidence-level RAG experiments

This runner compares real local retrieval, using the same recall function as application RAG.
It does not generate answers, call an LLM, or use Tavily. The initial dataset contains **five known
development questions**, not an independent test set. Four are answerable; one is an absence probe.

## Run

Start PostgreSQL and Qdrant and index the local corpus first. The pilot refers to hashes of three
existing local source files; their originals are not redistributed. `data/README.md` describes
corpus import. Missing databases, knowledge bases, or evidence anchors are prerequisites to resolve,
not successful zero-result experiments.

```powershell
$env:PYTHONIOENCODING='utf-8'
.venv\Scripts\python.exe -m evals.rag.run_retrieval --knowledge-base 电商行业 --knowledge-base 金融行业
```

Each run creates an independent `evals/results/rag_<timestamp>_<random>/` directory containing
`results.json` and `summary.md`. Raw result JSON includes retrieved passage text and remains local
under the existing ignore rule. Exit code 1 signals at least one blocked or invalid configuration.
The content-free [first pilot record](../reports/e2-rag-pilot-2026-10-18.json) is tracked for review.

## Controls and scoring

| Mode | Recall and ordering |
| --- | --- |
| A_vector | Vector recall, global score ordering, Top-5 |
| B_hybrid | Vector + PostgreSQL lexical recall, RRF, Top-5 |
| C_hybrid_rerank | Exactly B's candidate pool, BGE reranking, Top-5 |

All modes use the same selected knowledge bases, corpus, embedding, and final Top-5. Recall limits
are global across selected knowledge bases: the default is 24 vector and 24 lexical candidates
before deduplication and RRF. Application single/multiple-base retrieval now shares this recall
function. This replaces the old per-base pool concatenation with a global recall limit/order.
Application relevance filtering remains downstream of reranking. Experiments disable it so unlike
vector, RRF, and reranker score scales do not bias the comparison.

B/C candidate IDs are hashed in the same order. C always reuses B's in-memory pool; it does not
perform another recall. A makes its own vector-only recall and never calls the lexical retriever.
Model warmup is recorded separately. C latency includes its paired B recall time plus reranking;
sequential warm measurements are diagnostic, not concurrency or service latency benchmarks.

Each evidence unit has alternative locations containing a document SHA-256 and a whitespace-normalized
literal anchor with its own hash. Different overlapping chunks matching the same unit count once.
Recall@5 is matched units / expected units per question, macro-averaged across valid answerable
questions. MRR@5 uses the first matched evidence unit; all-evidence coverage records whether every
required unit was found. These measure **annotated passage retrieval**, not answer correctness.
Preflight verifies all positive anchors against the selected ready chunks before inference.

The no-answer case records candidate counts without entering Recall/MRR denominators. Its literal
absence check does not prove semantic abstention; refusal must be evaluated in the report phase.
Annotations are marked `source_verified_by_agent_pending_human_review`. Anchors can omit other
legitimate supporting passages, so the labels and alternatives need human review before formal
quality claims. These queries often name the target document and should not represent natural-query
generalization. Do not tune on a frozen test split and subsequently call it independent validation.

When BGE fails, C keeps diagnostic metadata but receives `invalid_reranker` and no metric score.
Each summary discloses scheduled/valid/invalid counts and answerable denominators. Compare groups
only on matching valid case IDs; the first run has all 15 configurations valid. A corpus change
detected between initial and final snapshots invalidates the run.

## Provenance and next steps

Manifests record Git revision/dirty state, application/evaluation source-tree hash, dataset hash,
dependency-lock hash, dependency versions, model names, recall settings, and knowledge-base scope.
The corpus hash covers ordered document SHA/chunk-index/content-hash tuples. Local ONNX and JSON
model artifacts are hashed as well. Legacy indexes do not record their original embedding model;
this provenance gap is disclosed and requires a fresh controlled index for a formal experiment.

E2 pilot is complete. Expand the existing twenty development questions with reviewed evidence units,
then create approximately ten natural-language test questions (including multi-document and
no-answer tasks) and freeze labels/configuration before test execution. E3 adds real report and
evidence-support acceptance; E4 makes one development-driven improvement and validates it with the
fixed configuration. Do not infer a positive reranking effect from implementing the component.
