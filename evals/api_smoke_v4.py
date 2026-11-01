"""Exercise HTTP task submission and the real bounded executor, with isolated API storage."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import uuid
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from evals.worker_supervisor import atomic_json


async def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    database = output / "smoke.sqlite"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS items (name TEXT)")
        conn.execute("DELETE FROM items")
        conn.executemany("INSERT INTO items VALUES (?)", [("one",), ("two",), ("three",)])
    from app.agent.llm import get_model
    from app.config import get_settings

    env = {
        "RESEARCH_WORKFLOW": "bounded",
        "LLM_PROVIDER": "deepseek",
        "EVIDENCE_SQLITE_PATH": str(database.resolve()),
        "CUDA_VISIBLE_DEVICES": "-1",
    }
    messages = []

    def append(**kwargs):
        messages.append(kwargs)
        return SimpleNamespace(id=f"message_{len(messages)}")

    with patch.dict(os.environ, env):
        get_settings.cache_clear()
        get_model.cache_clear()
        from app.api import server
        from app.auth.dependencies import get_current_user

        server.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="e6_smoke")
        try:
            with (
                patch.object(server, "session_scope", lambda: nullcontext(None)),
                patch.object(server, "get_or_create_conversation"),
                patch.object(server, "append_message", append),
                patch.object(server, "get_conversation_context", return_value=[]),
                patch.object(server, "format_conversation_context_for_prompt", return_value=""),
                patch.object(server, "extract_and_store_memories"),
                patch.object(server, "update_conversation_summary"),
            ):
                session_id = f"bounded_smoke_{uuid.uuid4().hex}"
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=server.app), base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/api/task",
                        json={
                            "query": "Use only SQL. Count all rows in items, report the numeric metric item_count with its evidence.",
                            "thread_id": session_id,
                            "sources": ["sql"],
                        },
                    )
                    response.raise_for_status()
                    pending = list(server.active_tasks.values())
                    await asyncio.gather(*pending)
                parent = Path(server.output_dir) / "user_e6_smoke" / f"session_{session_id}"
                artifacts = list(parent.glob("research_*/research_result.json"))
                if len(artifacts) != 1:
                    raise RuntimeError("missing_api_delivery")
                result = json.loads(artifacts[0].read_text())
                facts = {row["metric"]: row["value"] for row in result["report"]["facts"]}
                summary = {
                    "http_status": response.status_code,
                    "runtime_status": result["status"],
                    "item_count": facts.get("item_count"),
                    "saved_assistant_messages": sum(row["role"] == "assistant" for row in messages),
                    "model_reservations": result["model_reservations"],
                    "artifact": str(artifacts[0]),
                    "limitations": "Identity and conversation storage replaced; actual HTTP handler, shared executor, SQL and provider exercised.",
                }
                atomic_json(output / "summary.json", summary)
                if result["status"] != "completed" or facts.get("item_count") != "3":
                    raise RuntimeError("api_smoke_did_not_deliver_correct_count")
                return summary
        finally:
            server.app.dependency_overrides.pop(get_current_user, None)
            get_model.cache_clear()
            get_settings.cache_clear()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args.output)), indent=2))


if __name__ == "__main__":
    main()
