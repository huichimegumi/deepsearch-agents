"""Run local knowledge-base retrieval evals."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.rag.database import session_scope
from app.rag.models import Document, KnowledgeBase
from app.rag.retrieval import hybrid_search
from evals.runners.common import DATASET_DIR, RESULTS_DIR, load_jsonl, now_utc, status_counts, write_json


DEFAULT_DATASET = DATASET_DIR / "rag_local_zh.jsonl"


def _norm(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _knowledge_bases(hint: str) -> list[KnowledgeBase]:
    with session_scope() as session:
        rows = session.query(KnowledgeBase).order_by(KnowledgeBase.name).all()
        if hint in {"", "全部知识库", "all", "local"}:
            return rows
        normalized_hint = _norm(hint)
        matched = [kb for kb in rows if normalized_hint and normalized_hint in _norm(kb.name)]
        if matched:
            return matched

        # Terminal output may look garbled on Windows, but filenames are still useful
        # for resolving the intended sample domain.
        doc_rows = session.query(Document).filter(Document.status == "ready").all()
        wanted = "电商" if "电商" in hint else "金融" if "金融" in hint else ""
        if wanted:
            kb_ids = {
                doc.knowledge_base_id
                for doc in doc_rows
                if any(token in doc.filename for token in _domain_tokens(wanted))
            }
            return [kb for kb in rows if kb.id in kb_ids]
        return rows


def _domain_tokens(domain: str) -> list[str]:
    if domain == "电商":
        return ["电商", "数字人", "直播"]
    if domain == "金融":
        return ["BlackRock", "贝莱德", "中国人民银行", "货币政策", "CKISS", "投资者情绪"]
    return []


def _filename_hit(filename: str, expected: str) -> bool:
    if not expected:
        return False
    return _norm(expected) in _norm(filename)


def _score_sample(sample: dict[str, Any]) -> dict[str, Any]:
    kbs = _knowledge_bases(sample.get("knowledge_base_hint", ""))
    hits = []
    for kb in kbs:
        for hit in hybrid_search(sample["task"], kb.id):
            hits.append(hit)
    hits.sort(key=lambda item: item.score, reverse=True)
    hits = hits[:8]

    expected = sample.get("expected_filename_contains", "")
    secondary = sample.get("secondary_expected_filename_contains", "")
    filenames = [hit.filename for hit in hits]
    primary_hit_rank = next(
        (index for index, name in enumerate(filenames, start=1) if _filename_hit(name, expected)),
        None,
    )
    secondary_hit_rank = next(
        (index for index, name in enumerate(filenames, start=1) if _filename_hit(name, secondary)),
        None,
    )
    expects_empty = bool(sample.get("expect_empty_or_low_confidence"))

    if expects_empty:
        status = "passed" if not hits or not any(hit.score > 0 for hit in hits[:3]) else "review"
    elif primary_hit_rank is not None and (not secondary or secondary_hit_rank is not None):
        status = "passed"
    elif primary_hit_rank is not None:
        status = "partial"
    else:
        status = "failed"

    return {
        "id": sample["id"],
        "status": status,
        "knowledge_base_ids": [kb.id for kb in kbs],
        "hit_count": len(hits),
        "primary_hit_rank": primary_hit_rank,
        "secondary_hit_rank": secondary_hit_rank,
        "top_hits": [
            {
                "filename": hit.filename,
                "page_start": hit.page_start,
                "page_end": hit.page_end,
                "score": hit.score,
                "content_preview": hit.content[:180],
            }
            for hit in hits[:5]
        ],
    }


def run(dataset: Path = DEFAULT_DATASET) -> dict[str, Any]:
    samples = load_jsonl(dataset)
    results = []
    for sample in samples:
        try:
            results.append(_score_sample(sample))
        except Exception as exc:  # noqa: BLE001 - eval should record sample failures
            results.append({"id": sample["id"], "status": "blocked", "reason": repr(exc)})
    counts = status_counts(results)
    passed_like = counts.get("passed", 0) + counts.get("partial", 0)
    return {
        "name": "rag_local_zh",
        "dataset": str(dataset),
        "generated_at": now_utc(),
        "total": len(samples),
        "status_counts": counts,
        "pass_rate": counts.get("passed", 0) / len(samples) if samples else 0.0,
        "pass_or_partial_rate": passed_like / len(samples) if samples else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local RAG retrieval evals.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=RESULTS_DIR / "rag_local_eval.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = run(args.dataset)
    write_json(args.output, report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Dataset: {report['dataset']}")
        print(f"Total: {report['total']}")
        print(f"Status counts: {report['status_counts']}")
        print(f"Pass rate: {report['pass_rate']:.1%}")
        print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
