"""Short-term LangGraph checkpoint memory with Postgres and memory fallback."""

from __future__ import annotations

import asyncio
import atexit
import inspect
import os
import sys
from dataclasses import dataclass
from typing import Any

from app.rag.config import get_rag_settings


def _ensure_windows_selector_event_loop_policy() -> bool:
    if sys.platform != "win32":
        return False
    policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy_factory is None:
        return False
    if isinstance(asyncio.get_event_loop_policy(), policy_factory):
        return False
    asyncio.set_event_loop_policy(policy_factory())
    return True


_WINDOWS_SELECTOR_EVENT_LOOP_POLICY_SET = _ensure_windows_selector_event_loop_policy()


@dataclass(frozen=True)
class ShortTermMemoryStatus:
    requested_backend: str
    active_backend: str
    persistent: bool
    detail: str = ""


_checkpointer: Any | None = None
_pool: Any | None = None
_status = ShortTermMemoryStatus(
    requested_backend="uninitialized",
    active_backend="uninitialized",
    persistent=False,
)


def _reset_state() -> None:
    global _checkpointer, _pool, _status

    _checkpointer = None
    _pool = None
    _status = ShortTermMemoryStatus(
        requested_backend="uninitialized",
        active_backend="uninitialized",
        persistent=False,
    )


def _normalize_backend(value: str | None) -> str:
    backend = (value or "postgres").strip().lower()
    if backend in {"", "auto"}:
        return "postgres"
    if backend in {"memory", "inmemory", "in-memory", "none", "disabled"}:
        return "memory"
    return backend


def _checkpoint_conninfo(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg://")
    if database_url.startswith("postgresql+psycopg2://"):
        return "postgresql://" + database_url.removeprefix("postgresql+psycopg2://")
    return database_url


def _build_memory_checkpointer(requested_backend: str, detail: str = ""):
    global _status

    from langgraph.checkpoint.memory import InMemorySaver

    _status = ShortTermMemoryStatus(
        requested_backend=requested_backend,
        active_backend="memory",
        persistent=False,
        detail=detail,
    )
    return InMemorySaver()


async def _build_postgres_checkpointer():
    global _pool, _status

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    settings = get_rag_settings()
    conninfo = _checkpoint_conninfo(
        settings.short_term_memory_database_url or settings.database_url
    )
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    _pool = AsyncConnectionPool(
        conninfo=conninfo,
        max_size=settings.short_term_memory_pool_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await _pool.open(wait=True)
    saver = AsyncPostgresSaver(_pool)
    setup = getattr(saver, "setup", None)
    if callable(setup):
        await setup()
    _status = ShortTermMemoryStatus(
        requested_backend="postgres",
        active_backend="postgres",
        persistent=True,
        detail="Postgres checkpoint saver is active.",
    )
    return saver


async def setup_short_term_checkpointer():
    """Initialize and return the process-wide LangGraph checkpointer."""
    global _checkpointer

    if _checkpointer is not None:
        return _checkpointer

    settings = get_rag_settings()
    requested_backend = _normalize_backend(settings.short_term_memory_backend)
    if requested_backend == "memory":
        _checkpointer = _build_memory_checkpointer(
            requested_backend,
            "Short-term memory backend is configured as memory.",
        )
        return _checkpointer

    if requested_backend != "postgres":
        detail = f"Unsupported short-term memory backend: {requested_backend}"
        if not settings.short_term_memory_fallback_enabled:
            raise RuntimeError(detail)
        _checkpointer = _build_memory_checkpointer(requested_backend, detail)
        return _checkpointer

    try:
        _checkpointer = await _build_postgres_checkpointer()
    except Exception as exc:
        detail = f"Postgres short-term memory unavailable; using InMemorySaver: {exc!r}"
        await aclose_short_term_checkpointer()
        if not settings.short_term_memory_fallback_enabled:
            raise RuntimeError(detail) from exc
        _checkpointer = _build_memory_checkpointer(requested_backend, detail)
    return _checkpointer


def get_short_term_checkpointer():
    """Return the initialized checkpointer, or memory fallback outside app lifespan."""
    global _checkpointer

    if _checkpointer is not None:
        return _checkpointer

    settings = get_rag_settings()
    requested_backend = _normalize_backend(settings.short_term_memory_backend)
    if requested_backend == "postgres":
        detail = "Postgres short-term memory requires async setup; using InMemorySaver."
        if not settings.short_term_memory_fallback_enabled:
            raise RuntimeError(detail)
        _checkpointer = _build_memory_checkpointer(requested_backend, detail)
        return _checkpointer
    _checkpointer = _build_memory_checkpointer(
        requested_backend,
        "Short-term memory backend is configured as memory.",
    )
    return _checkpointer


def get_short_term_memory_status() -> ShortTermMemoryStatus:
    if _checkpointer is None:
        get_short_term_checkpointer()
    return _status


def clear_short_term_memory_for_thread(thread_id: str) -> bool:
    saver = get_short_term_checkpointer()
    delete_thread = getattr(saver, "delete_thread", None)
    if not callable(delete_thread):
        return False
    delete_thread(thread_id)
    return True


async def aclose_short_term_checkpointer() -> None:
    if _pool is not None:
        close = getattr(_pool, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result
    _reset_state()


def close_short_term_checkpointer() -> None:
    try:
        asyncio.run(aclose_short_term_checkpointer())
    except RuntimeError:
        _reset_state()


def reset_short_term_checkpointer_for_tests() -> None:
    close_short_term_checkpointer()


atexit.register(close_short_term_checkpointer)
