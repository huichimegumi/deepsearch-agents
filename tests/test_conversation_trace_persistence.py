"""Regression tests for persisted chat traces."""

import asyncio
import json
import unittest
from types import SimpleNamespace

import pytest

import app.api.server as server
from app.api.audit import _safe_value
from app.api.trace_utils import trace_files, trace_result, trace_terminal_message
from app.memory.conversation import ConversationContext


class ConversationTracePersistenceTests(unittest.TestCase):
    def test_trace_payload_values_are_json_safe(self):
        class CustomValue:
            def __str__(self) -> str:
                return "custom-value"

        events = [
            {
                "type": "monitor_event",
                "event": "tool_start",
                "message": "start",
                "data": _safe_value({"args": {"custom": CustomValue(), "items": {2, 1}}}),
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        ]

        self.assertEqual(events[0]["data"]["args"]["custom"], "custom-value")
        self.assertCountEqual(events[0]["data"]["args"]["items"], [1, 2])
        json.dumps(events)

    def test_trace_result_recovers_final_answer_from_events(self):
        events = [
            {
                "event": "session_created",
                "message": "created",
                "data": {"path": "/tmp/session"},
            },
            {
                "event": "task_result",
                "message": "done",
                "data": {"result": "final answer"},
            },
        ]

        self.assertEqual(trace_result(events), "final answer")
        self.assertEqual(trace_terminal_message(events), "")

    def test_trace_files_collects_file_created_events(self):
        events = [
            {
                "event": "file_created",
                "data": {
                    "name": "report.md",
                    "type": "file",
                    "path": "/tmp/session/report.md",
                    "size": 42,
                    "mtime": 100.0,
                },
            }
        ]

        self.assertEqual(
            trace_files(events),
            [
                {
                    "name": "report.md",
                    "type": "file",
                    "path": "/tmp/session/report.md",
                    "size": 42,
                    "mtime": 100.0,
                }
            ],
        )


@pytest.mark.asyncio
async def test_successful_turn_postprocess_does_not_block_task_completion(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def fake_agent(*args, **kwargs):
        return "final answer"

    async def fake_postprocess(*args, **kwargs):
        started.set()
        await release.wait()
        finished.set()

    monkeypatch.setattr(server, "run_deep_agent", fake_agent)
    monkeypatch.setattr(
        server,
        "get_conversation_context",
        lambda **kwargs: ConversationContext(summary="", recent_messages=[]),
    )
    monkeypatch.setattr(
        server,
        "append_message",
        lambda **kwargs: SimpleNamespace(id="assistant-message-id"),
    )
    monkeypatch.setattr(server, "_run_conversation_postprocess", fake_postprocess)
    server.postprocess_tasks.clear()

    await server._run_task_and_record(
        query="hello",
        thread_id="thread-id",
        user_id="user-id",
        monitor_thread_id="user-id__thread-id",
        user_message_id="user-message-id",
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    assert not finished.is_set()
    release.set()
    await asyncio.gather(*server.postprocess_tasks)
    assert finished.is_set()


if __name__ == "__main__":
    unittest.main()
