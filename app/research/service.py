"""Application research entry point, including user/session delivery context."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import shutil
from pathlib import Path

from app.api.context import (
    reset_session_context,
    set_session_context,
    set_thread_context,
    set_user_context,
)
from app.api.monitor import monitor
from app.config import get_settings
from app.research.bounded import execute
from app.research.source_scope import requires_local_only
from app.research.sources import SourceCatalog

ROOT = Path(__file__).resolve().parents[1]


async def run_research(
    task_query: str,
    session_id: str,
    *,
    user_id: str | None = None,
    monitor_thread_id: str | None = None,
    conversation_memory: str = "",
    sources: list[str] | None = None,
    rfc_demo: bool = False,
    rfc_sources_only: bool = False,
) -> str:
    settings = get_settings()
    if settings.research_workflow == "legacy" and sources is None and not rfc_demo:
        from app.agent.main_agent import run_deep_agent

        return await run_deep_agent(
            task_query,
            session_id,
            user_id=user_id,
            monitor_thread_id=monitor_thread_id,
            conversation_memory=conversation_memory,
        )
    if settings.research_workflow not in {"bounded", "legacy", "adaptive"}:
        raise ValueError("invalid_research_workflow")
    for component in (session_id, user_id):
        if component is not None and (
            not re.fullmatch(r"[a-zA-Z0-9_.-]{1,200}", component) or component in {".", ".."}
        ):
            raise ValueError("invalid_session_component")
    parent = ROOT / "output"
    uploaded = ROOT / "updated"
    if user_id:
        parent /= f"user_{user_id}"
        uploaded /= f"user_{user_id}"
    session_dir = parent / f"session_{session_id}"
    session_dir.mkdir(parents=True, exist_ok=True)
    if rfc_demo:
        from app.research.rfc_demo import run_rfc_qa

        session_token = set_session_context(str(session_dir))
        thread_token = set_thread_context(monitor_thread_id or session_id)
        user_token = set_user_context(user_id)
        try:
            monitor.report_session_dir(str(session_dir))
            monitor.report_research_phase("rfc_qa", "HTTP 规范问答", "start")
            result = await run_rfc_qa(task_query, session_dir, sources_only=rfc_sources_only)
            monitor.report_research_phase(
                "rfc_qa", "HTTP 规范问答", "end", {"runtime_status": result["status"]}
            )
            monitor.report_task_result(result["answer"])
            return result["answer"]
        finally:
            reset_session_context(session_token, thread_token, user_token)
    # Per-run artifacts retain previous attempts in the same conversation.
    import uuid

    run_dir = session_dir / f"research_{uuid.uuid4().hex}"
    documents = []
    upload_dir = uploaded / f"session_{session_id}"
    if upload_dir.is_dir():
        from app.rag.parsing import SUPPORTED_EXTENSIONS, parse_document

        for path in upload_dir.iterdir():
            if (
                not path.is_file()
                or path.is_symlink()
                or path.suffix.lower() not in SUPPORTED_EXTENSIONS
            ):
                continue
            shutil.copy2(path, session_dir / path.name)
            blocks = await asyncio.to_thread(parse_document, path)
            text = "\n\n".join(block.text for block in blocks)
            documents.append(
                {
                    "title": path.name,
                    "text": text,
                    "locator": f"document://sha256/{hashlib.sha256(path.read_bytes()).hexdigest()}",
                }
            )
    sql_path = os.getenv("EVIDENCE_SQLITE_PATH")
    allowed = ("sql", "local_document", "web") if sql_path else ("local_document", "web")
    if os.getenv("DABSTEP_DATA_DIR"):
        allowed += ("fee_engine",)
    if sources is not None:
        if not sources or not set(sources) <= set(allowed):
            raise ValueError("requested_source_not_configured")
        allowed = tuple(dict.fromkeys(sources))
    if requires_local_only(task_query):
        allowed = ("local_document",)
    catalog = SourceCatalog(
        sqlite_path=Path(sql_path) if sql_path else None,
        documents=documents or None,
        allowed_sources=allowed,
    )
    session_token = set_session_context(str(session_dir))
    thread_token = set_thread_context(monitor_thread_id or session_id)
    user_token = set_user_context(user_id)
    try:
        monitor.report_session_dir(str(session_dir))
        monitor.report_research_phase("bounded", "Evidence research", "start")
        question = task_query + (
            "\nConversation context (not source evidence):\n" + conversation_memory
            if conversation_memory
            else ""
        )
        result = await execute(
            question,
            catalog,
            run_dir,
            timeout_seconds=min(330, settings.agent_max_runtime_seconds),
            workflow="adaptive" if settings.research_workflow == "adaptive" else "bounded",
        )
        monitor.report_file_created(str(run_dir / "report.md"))
        monitor.report_research_phase(
            "bounded", "Evidence research", "end", {"runtime_status": result["status"]}
        )
        monitor.report_task_result(result["answer"])
        return result["answer"]
    finally:
        reset_session_context(session_token, thread_token, user_token)
