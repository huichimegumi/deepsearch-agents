"""Persistent user memory storage and retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text

from app.rag.config import get_rag_settings
from app.rag.database import session_scope
from app.rag.models import UserMemory, utcnow

ALLOWED_MEMORY_TYPES = {"fact", "preference", "project", "instruction", "summary"}
MEMORY_TYPE_PRIORITY = {
    "instruction": 1,
    "project": 2,
    "preference": 3,
    "fact": 4,
    "summary": 5,
}
MEMORY_TYPE_LABELS = {
    "instruction": "持续指令 / Standing instruction",
    "project": "项目背景 / Project context",
    "preference": "用户偏好 / User preference",
    "fact": "稳定事实 / Stable fact",
    "summary": "摘要 / Summary",
}
SENSITIVE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"api[_ -]?key",
        r"password",
        r"secret",
        r"token",
        r"bearer\s+[a-z0-9._-]+",
        r"sk-[a-z0-9]{12,}",
    )
]


@dataclass(frozen=True)
class MemoryHit:
    memory: UserMemory
    score: float


def normalize_memory_type(memory_type: str | None) -> str:
    normalized = (memory_type or "fact").strip().lower()
    return normalized if normalized in ALLOWED_MEMORY_TYPES else "fact"


def summarize_content(content: str) -> str:
    clean = " ".join(content.strip().split())
    return clean[:180]


def _clip_memory_content(content: str, limit: int = 240) -> str:
    clean = " ".join(content.strip().split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def is_safe_to_store(content: str) -> bool:
    if len(content.strip()) < 4:
        return False
    return not any(pattern.search(content) for pattern in SENSITIVE_PATTERNS)


def _collection_name() -> str:
    return get_rag_settings().memory_qdrant_collection


def _memory_payload(memory: UserMemory) -> dict[str, Any]:
    return {
        "user_id": memory.user_id,
        "thread_id": memory.thread_id or "",
        "memory_type": memory.memory_type,
        "is_deleted": memory.is_deleted,
    }


def _lexicalize_memory(text_value: str) -> str:
    normalized = text_value.lower()
    latin_tokens = re.findall(r"[a-z0-9_]+", normalized)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    chinese_bigrams = [
        "".join(chinese_chars[index : index + 2])
        for index in range(max(0, len(chinese_chars) - 1))
    ]
    return " ".join(latin_tokens + chinese_bigrams)


def _index_memory(memory: UserMemory) -> None:
    from app.rag.embeddings import embed_query
    from app.rag.vector_store import upsert_points

    vector = embed_query(memory.content)
    upsert_points(_collection_name(), [(memory.id, vector, _memory_payload(memory))])


def create_memory(
    *,
    user_id: str,
    content: str,
    memory_type: str = "fact",
    thread_id: str | None = None,
    source_message_id: str | None = None,
    confidence: float = 0.8,
    metadata: dict[str, Any] | None = None,
) -> UserMemory:
    if not is_safe_to_store(content):
        raise ValueError("Memory content is empty or appears to contain sensitive secrets.")

    with session_scope() as session:
        existing = session.scalar(
            select(UserMemory).where(
                UserMemory.user_id == user_id,
                UserMemory.content == content.strip(),
                UserMemory.is_deleted.is_(False),
            )
        )
        if existing is not None:
            existing.updated_at = utcnow()
            existing.confidence = max(existing.confidence, max(0.0, min(1.0, confidence)))
            session.flush()
            session.refresh(existing)
            return existing

        now = utcnow()
        memory = UserMemory(
            user_id=user_id,
            thread_id=thread_id,
            source_message_id=source_message_id,
            memory_type=normalize_memory_type(memory_type),
            content=content.strip(),
            summary=summarize_content(content),
            confidence=max(0.0, min(1.0, confidence)),
            metadata_=metadata,
            created_at=now,
            updated_at=now,
        )
        session.add(memory)
        session.flush()
        session.refresh(memory)

    try:
        _index_memory(memory)
    except Exception:
        # The database remains the source of truth; lexical fallback keeps memory usable.
        pass
    return memory


def update_memory(
    *,
    user_id: str,
    memory_id: str,
    content: str | None = None,
    memory_type: str | None = None,
    confidence: float | None = None,
    is_deleted: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> UserMemory | None:
    needs_reindex = False
    with session_scope() as session:
        memory = session.scalar(
            select(UserMemory).where(UserMemory.id == memory_id, UserMemory.user_id == user_id)
        )
        if memory is None:
            return None
        if content is not None:
            if not is_safe_to_store(content):
                raise ValueError("Memory content is empty or appears to contain sensitive secrets.")
            memory.content = content.strip()
            memory.summary = summarize_content(content)
            needs_reindex = True
        if memory_type is not None:
            memory.memory_type = normalize_memory_type(memory_type)
            needs_reindex = True
        if confidence is not None:
            memory.confidence = max(0.0, min(1.0, confidence))
        if metadata is not None:
            memory.metadata_ = metadata
        if is_deleted is not None:
            memory.is_deleted = is_deleted
            needs_reindex = not is_deleted
        memory.updated_at = utcnow()
        session.flush()
        session.refresh(memory)

    if is_deleted:
        try:
            from app.rag.vector_store import delete_points

            delete_points(_collection_name(), [memory_id])
        except Exception:
            pass
    elif needs_reindex:
        try:
            _index_memory(memory)
        except Exception:
            pass
    return memory


def delete_memory(*, user_id: str, memory_id: str) -> bool:
    memory = update_memory(user_id=user_id, memory_id=memory_id, is_deleted=True)
    return memory is not None


def list_memories(
    *,
    user_id: str,
    include_deleted: bool = False,
    memory_type: str | None = None,
    limit: int = 100,
) -> list[UserMemory]:
    statement = select(UserMemory).where(UserMemory.user_id == user_id)
    if not include_deleted:
        statement = statement.where(UserMemory.is_deleted.is_(False))
    if memory_type:
        statement = statement.where(UserMemory.memory_type == normalize_memory_type(memory_type))
    statement = statement.order_by(UserMemory.updated_at.desc()).limit(limit)
    with session_scope() as session:
        return list(session.scalars(statement).all())


def _lexical_search(user_id: str, query: str, limit: int) -> list[tuple[str, float]]:
    tokens = _lexicalize_memory(query).split()
    settings = get_rag_settings()
    if not tokens:
        return []
    ts_query = " | ".join(list(dict.fromkeys(tokens))[:64])
    statement = text(
        """
        SELECT id,
               ts_rank_cd(to_tsvector('simple', content), to_tsquery('simple', :ts_query))
               AS score
        FROM user_memories
        WHERE user_id = :user_id
          AND is_deleted = false
          AND confidence >= :min_confidence
          AND to_tsvector('simple', content) @@ to_tsquery('simple', :ts_query)
        ORDER BY score DESC
        LIMIT :limit
        """
    )
    with session_scope() as session:
        rows = session.execute(
            statement,
            {
                "user_id": user_id,
                "ts_query": ts_query,
                "limit": limit,
                "min_confidence": settings.memory_min_confidence,
            },
        ).all()
    return [(str(row.id), float(row.score)) for row in rows]


def search_memories(*, user_id: str, query: str, limit: int | None = None) -> list[MemoryHit]:
    settings = get_rag_settings()
    top_k = limit or settings.memory_top_k
    semantic: list[tuple[str, float]] = []
    try:
        from app.rag.embeddings import embed_query
        from app.rag.vector_store import search_payload_vectors

        semantic = search_payload_vectors(
            _collection_name(),
            embed_query(query),
            {"user_id": user_id, "is_deleted": False},
            top_k * 2,
        )
    except Exception:
        semantic = []

    lexical = _lexical_search(user_id, query, top_k * 2)
    fused: dict[str, float] = {}
    for results in (semantic, lexical):
        for rank, (memory_id, raw_score) in enumerate(results, start=1):
            fused[memory_id] = fused.get(memory_id, 0.0) + raw_score + 1.0 / (60 + rank)
    if not fused:
        return []

    ordered_ids = [
        item[0] for item in sorted(fused.items(), key=lambda item: item[1], reverse=True)
    ]
    with session_scope() as session:
        rows = session.scalars(
            select(UserMemory).where(
                UserMemory.id.in_(ordered_ids),
                UserMemory.user_id == user_id,
                UserMemory.is_deleted.is_(False),
                UserMemory.confidence >= settings.memory_min_confidence,
            )
        ).all()
        by_id = {item.id: item for item in rows}
        now = utcnow()
        hits: list[MemoryHit] = []
        for memory_id in ordered_ids:
            memory = by_id.get(memory_id)
            if memory is None:
                continue
            memory.access_count += 1
            memory.last_used_at = now
            hits.append(MemoryHit(memory=memory, score=float(fused[memory_id])))
            if len(hits) >= top_k:
                break
        session.flush()
        return hits


def format_memories_for_prompt(hits: list[MemoryHit]) -> str:
    if not hits:
        return ""
    sorted_hits = sorted(
        hits,
        key=lambda hit: (
            MEMORY_TYPE_PRIORITY.get(hit.memory.memory_type, 9),
            -hit.memory.confidence,
            -hit.score,
        ),
    )
    lines = [
        "【长期记忆 / Long-term memory】",
        "Use these user-managed memories only when relevant. "
        "The current user request always has higher priority.",
        "Priority: P1 standing instructions, P2 project context, "
        "P3 preferences, P4 stable facts, P5 summaries.",
    ]
    for hit in sorted_hits:
        memory = hit.memory
        priority = MEMORY_TYPE_PRIORITY.get(memory.memory_type, 9)
        label = MEMORY_TYPE_LABELS.get(memory.memory_type, memory.memory_type)
        lines.append(
            f"- P{priority} | {label} | confidence {memory.confidence:.2f} | "
            f"{_clip_memory_content(memory.content)}"
        )
    return "\n".join(lines)
