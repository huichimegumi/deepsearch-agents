"""Tests for conversation summary prompt memory helpers."""

import unittest

from app.memory.conversation import (
    ConversationContext,
    build_summary_prompt,
    format_conversation_context_for_prompt,
)


class ConversationMemoryTests(unittest.TestCase):
    def test_empty_context_formats_to_empty_prompt(self):
        context = ConversationContext(summary="", recent_messages=[])

        self.assertEqual(format_conversation_context_for_prompt(context), "")

    def test_context_includes_summary_and_recent_messages(self):
        context = ConversationContext(
            summary="用户正在整理金融行业报告。",
            recent_messages=[
                ("user", "请继续上一轮分析。"),
                ("assistant", "上一轮已经完成投资者情绪部分。"),
            ],
        )

        prompt = format_conversation_context_for_prompt(context)

        self.assertIn("当前会话历史记忆", prompt)
        self.assertIn("金融行业报告", prompt)
        self.assertIn("请继续上一轮分析", prompt)

    def test_summary_prompt_keeps_existing_summary_and_new_messages(self):
        prompt = build_summary_prompt(
            existing_summary="已有摘要",
            new_messages=[("user", "新增要求"), ("assistant", "新增结果")],
        )

        self.assertIn("已有摘要", prompt)
        self.assertIn("新增要求", prompt)
        self.assertIn("新增结果", prompt)


if __name__ == "__main__":
    unittest.main()
