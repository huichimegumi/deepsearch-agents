"""Tests for local memory helpers that do not require infrastructure."""

import unittest

from app.memory.service import (
    MemoryHit,
    format_memories_for_prompt,
    is_safe_to_store,
    normalize_memory_type,
)
from app.rag.models import UserMemory


class MemoryServiceTests(unittest.TestCase):
    def test_memory_type_defaults_unknown_values(self):
        self.assertEqual(normalize_memory_type("preference"), "preference")
        self.assertEqual(normalize_memory_type("unknown"), "fact")
        self.assertEqual(normalize_memory_type(None), "fact")

    def test_sensitive_secret_like_content_is_rejected(self):
        self.assertFalse(is_safe_to_store("my api_key is abc"))
        self.assertFalse(is_safe_to_store("password: test"))
        self.assertTrue(is_safe_to_store("用户偏好用中文输出简洁报告"))

    def test_format_memories_for_prompt_contains_ranked_items(self):
        memory = UserMemory(
            id="memory-1",
            user_id="user-1",
            memory_type="preference",
            content="用户偏好中文回答。",
            confidence=0.9,
            is_deleted=False,
        )

        prompt = format_memories_for_prompt([MemoryHit(memory=memory, score=1.0)])

        self.assertIn("用户长期记忆", prompt)
        self.assertIn("用户偏好中文回答", prompt)
        self.assertIn("preference", prompt)


if __name__ == "__main__":
    unittest.main()
