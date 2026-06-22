"""Tests for local RAG parsing helpers that do not require infrastructure."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.rag.config import get_rag_settings
from app.rag.parsing import ParsedBlock, chunk_blocks, lexicalize, parse_document


class RagParsingTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_rag_settings.cache_clear()

    def test_markdown_sections_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guide.md"
            path.write_text(
                "# 第一章\n\n这是第一段。\n\n## 第二章\n\n这是第二段。", encoding="utf-8"
            )

            blocks = parse_document(path)

        self.assertEqual(blocks[1].section, "第一章")
        self.assertEqual(blocks[-1].section, "第二章")

    def test_long_blocks_keep_page_metadata(self):
        with patch.dict(os.environ, {"RAG_CHUNK_SIZE": "30", "RAG_CHUNK_OVERLAP": "5"}):
            get_rag_settings.cache_clear()
            chunks = chunk_blocks([ParsedBlock("测试内容。" * 20, page=7)])

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(item.page_start == 7 and item.page_end == 7 for item in chunks))

    def test_lexicalize_adds_chinese_bigrams(self):
        tokens = lexicalize("人工智能 AI2026").split()

        self.assertIn("人工", tokens)
        self.assertIn("智能", tokens)
        self.assertIn("ai2026", tokens)


if __name__ == "__main__":
    unittest.main()
