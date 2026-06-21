"""Page-aware document parsing and structure-preserving chunking."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable

import docx
import pypdf

from app.rag.config import get_rag_settings


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


@dataclass(frozen=True)
class ParsedBlock:
    text: str
    page: int | None = None
    section: str | None = None


@dataclass(frozen=True)
class ParsedChunk:
    content: str
    page_start: int | None
    page_end: int | None
    section: str | None


def parse_document(path: Path) -> list[ParsedBlock]:
    extension = path.suffix.lower()
    if extension == ".pdf":
        reader = pypdf.PdfReader(str(path))
        return [
            ParsedBlock(text=text.strip(), page=index)
            for index, page in enumerate(reader.pages, start=1)
            if (text := (page.extract_text() or "").strip())
        ]
    if extension == ".docx":
        document = docx.Document(str(path))
        blocks: list[ParsedBlock] = []
        section: str | None = None
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            if paragraph.style and paragraph.style.name.lower().startswith("heading"):
                section = text
            blocks.append(ParsedBlock(text=text, section=section))
        return blocks
    if extension in {".md", ".txt"}:
        blocks = []
        section = None
        for paragraph in re.split(r"\n\s*\n", path.read_text("utf-8", errors="ignore")):
            text = paragraph.strip()
            if not text:
                continue
            if extension == ".md" and text.startswith("#"):
                section = text.lstrip("#").strip()
            blocks.append(ParsedBlock(text=text, section=section))
        return blocks
    raise ValueError(f"不支持的文档格式: {extension}")


def _split_long_text(text: str, size: int, overlap: int) -> Iterable[str]:
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind(mark, start, end) for mark in "。！？；\n")
            if boundary > start + size // 2:
                end = boundary + 1
        yield text[start:end].strip()
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)


def chunk_blocks(blocks: list[ParsedBlock]) -> list[ParsedChunk]:
    settings = get_rag_settings()
    chunks: list[ParsedChunk] = []
    for block in blocks:
        clean = re.sub(r"[ \t]+", " ", block.text).strip()
        for piece in _split_long_text(clean, settings.chunk_size, settings.chunk_overlap):
            if piece:
                chunks.append(
                    ParsedChunk(
                        content=piece,
                        page_start=block.page,
                        page_end=block.page,
                        section=block.section,
                    )
                )
    return chunks


def lexicalize(text: str) -> str:
    """Produce PostgreSQL simple-dictionary tokens that also work for Chinese."""
    lowered = text.lower()
    latin = re.findall(r"[a-z0-9]{2,}", lowered)
    chars = re.findall(r"[\u4e00-\u9fff]", lowered)
    bigrams = [chars[index] + chars[index + 1] for index in range(len(chars) - 1)]
    return " ".join(latin + chars + bigrams)
