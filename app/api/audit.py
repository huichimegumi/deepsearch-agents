"""按会话落盘的结构化审计日志。"""

import datetime
import json
from pathlib import Path
from typing import Any

from app.api.context import get_thread_context

LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
MAX_STRING_LENGTH = 4000


def _safe_value(value: Any) -> Any:
    """把任意对象转换成可写入 JSONL 的安全值。"""
    if isinstance(value, str):
        if len(value) > MAX_STRING_LENGTH:
            return value[:MAX_STRING_LENGTH] + "...[已截断]"
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_value(item) for item in value]
    return str(value)


def write_audit_event(
    event: str,
    data: dict[str, Any] | None = None,
    thread_id: str | None = None,
) -> None:
    """写入一条会话审计日志；日志失败不影响主流程。"""
    resolved_thread_id = thread_id or get_thread_context() or "unknown"
    payload = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "thread_id": resolved_thread_id,
        "event": event,
        "data": _safe_value(data or {}),
    }

    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOG_DIR / f"session_{resolved_thread_id}.jsonl"
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as exc:
        print(f"[Audit] 写入审计日志失败: {exc}")
