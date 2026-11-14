"""Single-round baseline for DeepResearch Bench: one search round, then one writer call.

Two model requests per task: the first proposes up to three search queries, the second
writes the report from the fetched pages. Uses the application's model and search service.
Output layout matches ``run_agent.py`` so ``prepare.py`` exports it unchanged.
"""

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path

from app.agent.llm import get_model
from app.agent.research_date import research_date_context
from app.search.models import SearchRequest
from app.search.service import get_search_service
from evals.drb_osodt.checkpoint import open_run, pending_case
from evals.drb_osodt.tasks import select
from evals.worker_supervisor import atomic_json

PAGE_CHARS = 6000
QUERIES = (
    "Propose up to three web search queries that together cover the research task. "
    "Reply with a JSON array of strings only."
)
WRITER = (
    "Write a complete research report answering the task, in the language of the task, "
    "using the numbered sources. Cite sources as [n] after the statements they support and "
    "do not cite a source for content it does not contain. Use Markdown headings."
)


async def run_case(
    row,
    output,
    backend,
    max_tokens,
    *,
    current_date: date | None = None,
    include_search_snippets: bool = False,
):
    attempt = output / f"drb_{row['id']}" / "attempt-0001"
    attempt.mkdir(parents=True)
    started = time.monotonic()
    report, error, usage, sources = "", None, [], []
    queries = []
    writer_prompt = WRITER
    if current_date is not None:
        writer_prompt = research_date_context(current_date) + "\n\n" + writer_prompt
    try:
        model = get_model()
        if backend is not None:
            planned = await model.bind(temperature=0, max_tokens=300).ainvoke(
                [{"role": "system", "content": QUERIES}, {"role": "user", "content": row["prompt"]}]
            )
            usage.append(planned.usage_metadata)
            text = planned.content[planned.content.find("[") : planned.content.rfind("]") + 1]
            queries = [str(q) for q in json.loads(text)][:3] or [row["prompt"][:200]]
            found = await asyncio.to_thread(
                get_search_service().search,
                SearchRequest(queries, backend=backend, fetch_full_page=True, max_fetched_pages=6),
            )
            sources = [
                {
                    "n": n,
                    "title": r.title,
                    "url": r.url,
                    "text": (r.raw_content or r.content)[:PAGE_CHARS],
                }
                for n, r in enumerate(found.results, start=1)
            ]
            if include_search_snippets:
                for source, result in zip(sources, found.results):
                    if result.raw_content and result.content:
                        source["search_snippet"] = result.content[:1200]
                    if not result.raw_content:
                        source["source_kind"] = "search_snippet_only"
        written = await model.bind(temperature=0, max_tokens=max_tokens).ainvoke(
            [
                {"role": "system", "content": writer_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"task": row["prompt"], "sources": sources}, ensure_ascii=False
                    ),
                },
            ]
        )
        usage.append(written.usage_metadata)
        report = str(written.content)
        if sources:
            report += "\n\n## Sources\n" + "\n".join(
                f"[{s['n']}] {s['title']} {s['url']}" for s in sources
            )
    except Exception as exc:  # noqa: BLE001 - a failed case is a result, not a crash
        error = type(exc).__name__
    status = "completed" if report.strip() and error is None else "failed"
    record = {
        "case_id": f"drb:{row['id']}",
        "seconds": round(time.monotonic() - started, 1),
        "error": error,
        "usage": usage,
        "sources": len(sources),
    }
    (attempt / "report.md").write_text(report, "utf-8")
    (attempt / "sources.json").write_text(json.dumps(sources, ensure_ascii=False), "utf-8")
    if current_date is not None:
        atomic_json(attempt / "search_plan.json", {"queries": queries})
    atomic_json(attempt / "research_result.json", {"status": status})
    atomic_json(attempt / "worker_result.json", record)
    print(json.dumps({**record, "status": status, "characters": len(report)}), flush=True)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--per-language", type=int, default=3)
    parser.add_argument("--ids", type=int, nargs="*", help="Subset of the selected task ids")
    parser.add_argument("--backend", default="duckduckgo")
    parser.add_argument("--max-tokens", type=int, default=8000)
    args = parser.parse_args()

    rows = [r for r in select(args.per_language) if not args.ids or r["id"] in args.ids]
    manifest = {
        "workflow": "single_round",
        "backend": args.backend,
        "model": get_model().model_name,
        "max_tokens": args.max_tokens,
        "tasks": [r["id"] for r in rows],
    }
    open_run(args.output, manifest)
    for row in rows:
        if not pending_case(args.output, row["id"]):
            print(f"drb:{row['id']} reused", flush=True)
            continue
        await run_case(row, args.output, args.backend, args.max_tokens)


if __name__ == "__main__":
    asyncio.run(main())
