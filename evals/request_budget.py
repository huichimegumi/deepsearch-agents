"""Pre-dispatch model budget for one isolated evaluation worker."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path

_LOCK = threading.Lock()
_STATE: dict[str, tuple[int, int]] = {}


class EvaluationBudgetExceeded(RuntimeError):
    """A model request was refused before transport dispatch."""


def _estimated_input_tokens(payload: dict) -> tuple[int, str]:
    relevant = {
        key: payload.get(key)
        for key in ("messages", "tools", "tool_choice", "response_format", "functions")
        if key in payload
    }
    serialized = json.dumps(relevant, ensure_ascii=False, sort_keys=True, default=str)
    try:
        import tiktoken

        estimate = (
            len(tiktoken.get_encoding("cl100k_base").encode(serialized, disallowed_special=())) + 32
        )
    except ImportError:
        # Byte count overestimates ordinary BPE token counts and is safe as a fallback.
        estimate = len(serialized.encode("utf-8")) + 32
    return estimate, hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _ledger_usage(path: Path) -> tuple[int, int]:
    requests = 0
    reserved = 0
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
            if not line.endswith("\n"):
                break  # killed while writing a line: HTTP dispatch had not begun
            item = json.loads(line)
            if item.get("event") == "admitted":
                requests += 1
                reserved += int(item["reserved_tokens"])
    return requests, reserved


def usage(path: Path) -> dict[str, int]:
    requests, reserved = _ledger_usage(path)
    return {"requests": requests, "reserved_tokens": reserved}


def admit_request(payload: dict) -> None:
    """Reserve input estimate plus the output cap before any HTTP request starts."""
    ledger_setting = os.getenv("EVAL_LEDGER_PATH")
    if not ledger_setting:
        return
    path = Path(ledger_setting)
    estimated_input, request_hash = _estimated_input_tokens(payload)
    output_limit = int(
        payload.get("max_tokens")
        or payload.get("max_completion_tokens")
        or os.getenv("EVAL_DEFAULT_MAX_OUTPUT_TOKENS", "4000")
    )
    if output_limit <= 0:
        raise ValueError("invalid_eval_output_reservation")
    reservation = estimated_input + output_limit
    max_requests = int(os.getenv("EVAL_MAX_REQUESTS", "10"))
    max_reserved = int(os.getenv("EVAL_MAX_RESERVED_TOKENS", "180000"))
    if max_requests <= 0 or max_reserved <= 0:
        raise ValueError("invalid_eval_request_budget")
    with _LOCK:
        key = str(path.resolve())
        current_requests, current_reserved = _STATE.get(key, _ledger_usage(path))
        reason = None
        if current_requests >= max_requests:
            reason = "request_limit"
        elif current_reserved + reservation > max_reserved:
            reason = "token_reservation_limit"
        entry = {
            "event": "blocked" if reason else "admitted",
            "reason": reason,
            "model": payload.get("model"),
            "request_sha256": request_hash,
            "estimated_input_tokens": estimated_input,
            "output_reservation_tokens": output_limit,
            "reserved_tokens": reservation if not reason else 0,
            "requests_after": current_requests + (0 if reason else 1),
            "reserved_after": current_reserved + (0 if reason else reservation),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if reason:
            raise EvaluationBudgetExceeded(reason)
        _STATE[key] = current_requests + 1, current_reserved + reservation
