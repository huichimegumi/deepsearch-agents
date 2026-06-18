"""
Local knowledge-base RAG tools.

This module mirrors the RAGFlow tool contract without importing or calling
RAGFlow. It is intentionally not wired into knowledge_base_agent.py yet, so the
current project behavior stays unchanged until that import is switched.
"""

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from langchain_core.tools import tool

from app.api.monitor import monitor

try:
    import docx
except ImportError:  # pragma: no cover - optional dependency guard
    docx = None

try:
    import pypdf
except ImportError:  # pragma: no cover - optional dependency guard
    pypdf = None


APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
DEFAULT_KNOWLEDGE_ROOT = PROJECT_ROOT / "docs" / "knowledge_base"

SUPPORTED_EXTENSIONS = {".pdf", ".md", ".txt", ".docx"}
CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
TOP_K = 6


@dataclass(frozen=True)
class DocumentChunk:
    """A retrievable text chunk with enough source metadata for citations."""

    knowledge_base: str
    source_path: Path
    title: str
    text: str
    page: int | None = None
    chunk_index: int = 0

    @property
    def source_label(self) -> str:
        page_part = f", 第 {self.page} 页" if self.page is not None else ""
        return f"{self.knowledge_base}/{self.title}{page_part}"


@dataclass
class LocalRagIndex:
    """In-memory BM25-style index over local knowledge-base documents."""

    chunks: list[DocumentChunk]
    tokenized_chunks: list[list[str]]
    document_frequency: Counter
    average_doc_len: float
    fingerprint: tuple[tuple[str, int, int], ...]


_INDEX_CACHE: LocalRagIndex | None = None


def _knowledge_root() -> Path:
    return DEFAULT_KNOWLEDGE_ROOT


def _assistant_directories() -> list[Path]:
    root = _knowledge_root()
    if not root.exists():
        return []
    return sorted([path for path in root.iterdir() if path.is_dir()], key=lambda p: p.name)


def _fingerprint_files() -> tuple[tuple[str, int, int], ...]:
    root = _knowledge_root()
    if not root.exists():
        return ()

    files = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            stat = path.stat()
            files.append((str(path.relative_to(root)), int(stat.st_mtime), stat.st_size))
    return tuple(files)


def _read_text_file(path: Path) -> list[tuple[str, int | None]]:
    return [(path.read_text(encoding="utf-8", errors="ignore"), None)]


def _read_docx(path: Path) -> list[tuple[str, int | None]]:
    if docx is None:
        return []
    document = docx.Document(str(path))
    return [("\n".join(paragraph.text for paragraph in document.paragraphs), None)]


def _read_pdf(path: Path) -> list[tuple[str, int | None]]:
    if pypdf is None:
        return []

    reader = pypdf.PdfReader(str(path))
    pages = []
    for page_index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append((text, page_index))
    return pages


def _load_document(path: Path) -> list[tuple[str, int | None]]:
    ext = path.suffix.lower()
    if ext in {".md", ".txt"}:
        return _read_text_file(path)
    if ext == ".docx":
        return _read_docx(path)
    if ext == ".pdf":
        return _read_pdf(path)
    return []


def _split_text(text: str, chunk_size: int = CHUNK_SIZE) -> Iterable[str]:
    clean_text = re.sub(r"\s+", " ", text).strip()
    if not clean_text:
        return

    start = 0
    while start < len(clean_text):
        end = min(start + chunk_size, len(clean_text))
        yield clean_text[start:end]
        if end == len(clean_text):
            break
        start = max(0, end - CHUNK_OVERLAP)


def _knowledge_base_name(path: Path) -> str:
    root = _knowledge_root()
    try:
        relative = path.relative_to(root)
    except ValueError:
        return "默认知识库"
    return relative.parts[0] if len(relative.parts) > 1 else "默认知识库"


def _iter_chunks() -> list[DocumentChunk]:
    root = _knowledge_root()
    if not root.exists():
        return []

    chunks: list[DocumentChunk] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        knowledge_base = _knowledge_base_name(path)
        for text, page in _load_document(path):
            for chunk_index, chunk_text in enumerate(_split_text(text)):
                chunks.append(
                    DocumentChunk(
                        knowledge_base=knowledge_base,
                        source_path=path,
                        title=path.name,
                        text=chunk_text,
                        page=page,
                        chunk_index=chunk_index,
                    )
                )
    return chunks


def _tokenize(text: str) -> list[str]:
    lower_text = text.lower()
    latin_tokens = re.findall(r"[a-z0-9][a-z0-9_\-\.]{1,}", lower_text)
    cjk_chars = re.findall(r"[\u4e00-\u9fff]", lower_text)
    cjk_bigrams = [
        cjk_chars[index] + cjk_chars[index + 1]
        for index in range(max(0, len(cjk_chars) - 1))
    ]
    return latin_tokens + cjk_chars + cjk_bigrams


def _build_index() -> LocalRagIndex:
    chunks = _iter_chunks()
    tokenized_chunks = [_tokenize(chunk.text) for chunk in chunks]
    document_frequency: Counter = Counter()

    for tokens in tokenized_chunks:
        document_frequency.update(set(tokens))

    average_doc_len = (
        sum(len(tokens) for tokens in tokenized_chunks) / len(tokenized_chunks)
        if tokenized_chunks
        else 0.0
    )

    return LocalRagIndex(
        chunks=chunks,
        tokenized_chunks=tokenized_chunks,
        document_frequency=document_frequency,
        average_doc_len=average_doc_len,
        fingerprint=_fingerprint_files(),
    )


def _get_index() -> LocalRagIndex:
    global _INDEX_CACHE

    fingerprint = _fingerprint_files()
    if _INDEX_CACHE is None or _INDEX_CACHE.fingerprint != fingerprint:
        _INDEX_CACHE = _build_index()
    return _INDEX_CACHE


def _matches_assistant(chunk: DocumentChunk, chat_name: str) -> bool:
    normalized = chat_name.strip()
    if normalized in {"", "全部知识库", "本地知识库", "local", "all"}:
        return True
    return normalized in {
        chunk.knowledge_base,
        f"{chunk.knowledge_base}助手",
        f"{chunk.knowledge_base}知识库",
    }


def _search(question: str, chat_name: str, top_k: int = TOP_K) -> list[tuple[float, DocumentChunk]]:
    index = _get_index()
    query_tokens = _tokenize(question)
    if not query_tokens or not index.chunks:
        return []

    query_counts = Counter(query_tokens)
    total_docs = len(index.chunks)
    k1 = 1.5
    b = 0.75
    scored: list[tuple[float, DocumentChunk]] = []

    for chunk, tokens in zip(index.chunks, index.tokenized_chunks):
        if not _matches_assistant(chunk, chat_name):
            continue

        token_counts = Counter(tokens)
        doc_len = len(tokens) or 1
        score = 0.0

        for token, query_weight in query_counts.items():
            frequency = token_counts.get(token, 0)
            if frequency == 0:
                continue

            df = index.document_frequency.get(token, 0)
            idf = math.log(1 + (total_docs - df + 0.5) / (df + 0.5))
            denominator = frequency + k1 * (
                1 - b + b * doc_len / max(index.average_doc_len, 1.0)
            )
            score += query_weight * idf * (frequency * (k1 + 1)) / denominator

        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top_k]


def _format_sources(matches: list[tuple[float, DocumentChunk]]) -> str:
    lines = []
    for rank, (score, chunk) in enumerate(matches, start=1):
        snippet = chunk.text[:500]
        lines.append(
            f"[{rank}] 来源: {chunk.source_label}; 相关度: {score:.2f}\n{snippet}"
        )
    return "\n\n".join(lines)


def _synthesize_answer(question: str, matches: list[tuple[float, DocumentChunk]]) -> str:
    context = _format_sources(matches)
    prompt = f"""
你是一个本地知识库问答助手。请只基于下面的检索片段回答用户问题。
如果片段不足以回答，请明确说明“本地知识库没有足够依据”。
回答需要包含：
1. 直接结论
2. 关键依据
3. 来源列表

用户问题：
{question}

检索片段：
{context}
"""
    try:
        from app.agent.llm import model

        response = model.invoke([{"role": "user", "content": prompt}])
        return getattr(response, "content", str(response))
    except Exception as exc:
        return (
            "本地知识库已完成检索，但调用大模型汇总失败。以下是最相关片段：\n\n"
            f"{context}\n\n"
            f"汇总失败原因：{exc}"
        )


@tool
def get_assistant_list() -> str:
    """
    查询本地可用知识库助手，以及每个助手覆盖的本地文档集合。

    本工具保持与 RAGFlow 版 get_assistant_list 相同的用途，方便后续把
    knowledge_base_agent.py 的 import 切换到本模块。
    """

    monitor.report_tool(tool_name="本地知识库助手列表查询工具：get_assistant_list")

    assistants = _assistant_directories()
    if not assistants:
        return f"没有任何可用本地知识库，期望目录：{_knowledge_root()}"

    lines = []
    for assistant_dir in assistants:
        files = [
            path.name
            for path in sorted(assistant_dir.rglob("*"))
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        description = (
            f"本地 {assistant_dir.name} 非结构化文档知识库，包含 {len(files)} 个文件"
        )
        sample_files = "、".join(files[:5])
        if len(files) > 5:
            sample_files += " 等"
        lines.append(
            f"助手名称:{assistant_dir.name};功能介绍：{description}; "
            f"关联的知识库：{assistant_dir.name}; 文档：{sample_files}"
        )

    lines.append(
        "助手名称:全部知识库;功能介绍：跨所有本地知识库检索; 关联的知识库：全部本地文档"
    )
    return "\n".join(lines)


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """
    向本地知识库助手提问。

    :param chat_name: 助手名称，建议来自 get_assistant_list 返回结果；也可传“全部知识库”
    :param question: 本次提问的问题
    :return: 基于本地文档召回片段生成的回答，含来源信息
    """

    monitor.report_tool(
        tool_name="本地知识库提问工具：create_ask_delete",
        args={"chat_name": chat_name, "question": question},
    )

    try:
        matches = _search(question=question, chat_name=chat_name)
        if not matches:
            return (
                f"本地知识库没有检索到可回答该问题的片段。"
                f"助手名称：{chat_name}；问题：{question}"
            )
        return _synthesize_answer(question=question, matches=matches)
    except Exception as exc:
        return f"本地知识库提问失败，错误原因：{exc}"
