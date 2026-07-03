"""Tests for long-term memory extraction guardrails."""

import unittest

from app.memory.extraction import _is_auto_memory_candidate


class MemoryExtractionTests(unittest.TestCase):
    def test_auto_memory_candidates_are_limited_to_durable_types(self):
        self.assertTrue(
            _is_auto_memory_candidate(
                content="用户偏好先给结论再列证据。",
                memory_type="preference",
                confidence=0.9,
            )
        )
        self.assertFalse(
            _is_auto_memory_candidate(
                content="今天查询了某个网页。",
                memory_type="fact",
                confidence=0.95,
            )
        )
        self.assertFalse(
            _is_auto_memory_candidate(
                content="用户可能喜欢表格。",
                memory_type="preference",
                confidence=0.6,
            )
        )

    def test_auto_memory_candidates_reject_secret_like_content(self):
        self.assertFalse(
            _is_auto_memory_candidate(
                content="请记住我的 api_key 是 abc。",
                memory_type="instruction",
                confidence=0.99,
            )
        )


if __name__ == "__main__":
    unittest.main()
