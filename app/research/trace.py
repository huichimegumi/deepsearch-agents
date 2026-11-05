"""Incremental private research artifacts, including rejected model/tool candidates."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from app.research.storage import write_json

_ACTIVE: ContextVar[ResearchTrace | None] = ContextVar("research_trace", default=None)


class ResearchTrace:
    def __init__(self, output: Path):
        self.directory = output / "trace"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.sequence = len(list(self.directory.glob("model-*-request.json")))

    @contextmanager
    def activate(self):
        token = _ACTIVE.set(self)
        try:
            yield self
        finally:
            _ACTIVE.reset(token)

    def event(self, event: str, **data):
        with (self.directory / "events.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"event": event, **data}, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def request(self, schema, instruction, payload):
        self.sequence += 1
        key = f"model-{self.sequence:03d}"
        write_json(
            self.directory / f"{key}-request.json",
            {
                "schema": schema.__name__,
                "schema_json": schema.model_json_schema(),
                "instruction": instruction,
                "payload": payload,
            },
        )
        return key

    def response(self, key, response, metadata):
        raw = response.get("raw")
        parsed = response.get("parsed")
        write_json(
            self.directory / f"{key}-response.json",
            {
                "parsed": parsed.model_dump() if hasattr(parsed, "model_dump") else None,
                "tool_calls": getattr(raw, "tool_calls", None),
                "invalid_tool_calls": getattr(raw, "invalid_tool_calls", None),
                "raw_message": raw.model_dump(mode="json") if hasattr(raw, "model_dump") else None,
                "content": getattr(raw, "content", None),
                "parsing_error": str(response.get("parsing_error"))
                if response.get("parsing_error")
                else None,
                "metadata": metadata,
            },
        )


def current_trace():
    return _ACTIVE.get()
