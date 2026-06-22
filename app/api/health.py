"""Liveness and dependency-readiness endpoints."""

import asyncio
import socket
from collections.abc import Callable
from urllib.parse import urlparse

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.rag.config import get_rag_settings
from app.rag.database import get_engine

router = APIRouter(prefix="/health", tags=["health"])


def _check_llm_config() -> None:
    get_settings().validate_llm()


def _check_postgres() -> None:
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))


def _check_tcp_url(value: str, default_port: int) -> None:
    parsed = urlparse(value if "://" in value else f"tcp://{value}")
    host = parsed.hostname
    port = parsed.port or default_port
    if not host:
        raise ValueError(f"无法解析服务地址: {value}")
    with socket.create_connection((host, port), timeout=2):
        pass


def _readiness_checks() -> dict[str, Callable[[], None]]:
    rag = get_rag_settings()
    return {
        "llm_config": _check_llm_config,
        "postgres": _check_postgres,
        "redis": lambda: _check_tcp_url(rag.redis_url, 6379),
        "qdrant": lambda: _check_tcp_url(rag.qdrant_url, 6333),
        "minio": lambda: _check_tcp_url(rag.minio_endpoint, 9000),
    }


async def collect_readiness(
    checks: dict[str, Callable[[], None]] | None = None,
) -> dict[str, dict[str, str]]:
    selected = checks or _readiness_checks()

    async def run_check(name: str, check: Callable[[], None]):
        try:
            await asyncio.to_thread(check)
            return name, {"status": "ok"}
        except Exception as exc:
            return name, {"status": "error", "detail": str(exc)}

    results = await asyncio.gather(*(run_check(name, check) for name, check in selected.items()))
    return dict(results)


@router.get("/live")
def liveness():
    return {"status": "ok"}


@router.get("/ready")
async def readiness():
    services = await collect_readiness()
    ready = all(item["status"] == "ok" for item in services.values())
    payload = {"status": "ok" if ready else "error", "services": services}
    if ready:
        return payload
    return JSONResponse(status_code=503, content=payload)
