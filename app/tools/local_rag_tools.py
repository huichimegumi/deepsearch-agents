"""DeepAgents tools for the PostgreSQL/Qdrant local knowledge-base service."""

from dataclasses import replace
from time import monotonic

from langchain_core.tools import tool
from sqlalchemy import func, select

from app.api.audit import write_audit_event
from app.api.monitor import monitor
from app.config import get_settings
from app.rag.database import session_scope
from app.rag.models import Document, KnowledgeBase
from app.rag.retrieval import RetrievedChunk, hybrid_search, hybrid_search_many

ASSISTANT_LIST_TOOL = "本地知识库助手列表查询工具：get_assistant_list"
ASK_KNOWLEDGE_BASE_TOOL = "本地知识库混合检索工具：ask_knowledge_base"


def _ready_knowledge_bases() -> list[tuple[KnowledgeBase, int]]:
    with session_scope() as session:
        rows = session.execute(
            select(KnowledgeBase, func.count(Document.id))
            .join(
                Document,
                (Document.knowledge_base_id == KnowledgeBase.id) & (Document.status == "ready"),
                isouter=True,
            )
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.name)
        ).all()
        return [(knowledge_base, int(count)) for knowledge_base, count in rows]


def _resolve_knowledge_bases(chat_name: str) -> list[KnowledgeBase]:
    normalized = chat_name.strip()
    with session_scope() as session:
        statement = select(KnowledgeBase).order_by(KnowledgeBase.name)
        if normalized not in {"", "全部知识库", "本地知识库", "all", "local"}:
            candidates = {
                normalized,
                normalized.removesuffix("助手"),
                normalized.removesuffix("知识库"),
            }
            statement = statement.where(KnowledgeBase.name.in_(candidates))
        return list(session.scalars(statement).all())


def _format_context(hits: list[RetrievedChunk]) -> str:
    return "\n\n".join(
        f"[{index}] 来源：{hit.citation}\n{hit.content}" for index, hit in enumerate(hits, start=1)
    )


def _limit_hits_for_answer(hits: list[RetrievedChunk]) -> tuple[list[RetrievedChunk], dict]:
    settings = get_settings()
    max_hits = max(1, settings.rag_answer_max_hits)
    max_context_chars = max(1, settings.rag_answer_max_context_chars)
    limited_hits: list[RetrievedChunk] = []
    truncated_by_chars = False

    for hit in hits[:max_hits]:
        prefix_chars = len(f"[{len(limited_hits) + 1}] 来源：{hit.citation}\n")
        remaining = max_context_chars - len(_format_context(limited_hits)) - prefix_chars
        if remaining <= 0:
            truncated_by_chars = True
            break
        content = hit.content
        if len(content) > remaining:
            content = content[:remaining].rstrip() + "\n[片段内容已按上下文预算截断]"
            truncated_by_chars = True
        limited_hits.append(replace(hit, content=content))
        if len(_format_context(limited_hits)) >= max_context_chars:
            truncated_by_chars = True
            break

    return limited_hits, {
        "candidate_hits": len(hits),
        "answer_hits": len(limited_hits),
        "max_answer_hits": max_hits,
        "context_chars": len(_format_context(limited_hits)),
        "max_context_chars": max_context_chars,
        "truncated": len(hits) > len(limited_hits) or truncated_by_chars,
        "truncated_by_hits": len(hits) > max_hits,
        "truncated_by_chars": truncated_by_chars,
    }


def _hit_metadata(hit: RetrievedChunk) -> dict:
    return {
        "chunk_id": hit.chunk_id,
        "filename": hit.filename,
        "page_start": hit.page_start,
        "page_end": hit.page_end,
        "section": hit.section,
        "score": hit.score,
        "citation": hit.citation,
    }


def _answer(question: str, hits: list[RetrievedChunk]) -> str:
    context = _format_context(hits)
    prompt = f"""
你是企业内部知识库问答助手。只能根据检索片段回答，不得补充片段之外的事实。
回答要求：
1. 先给出直接结论，再列出关键依据。
2. 每项事实后使用 [1]、[2] 这样的编号引用，编号必须来自检索片段。
3. 最后输出“来源”列表，完整保留文件名和页码。
4. 如果证据不足，明确说明“本地知识库没有足够依据”。

用户问题：{question}

检索片段：
{context}
"""
    from app.agent.llm import get_model

    response = get_model().invoke([{"role": "user", "content": prompt}])
    return getattr(response, "content", str(response))


@tool
def get_assistant_list() -> str:
    """List ready local knowledge bases and document counts."""
    started_at = monotonic()
    monitor.report_tool(tool_name=ASSISTANT_LIST_TOOL)
    try:
        rows = _ready_knowledge_bases()
        if not rows:
            result = "当前没有可用的本地知识库，请先通过知识库管理页面上传并完成索引。"
        else:
            lines = [
                f"助手名称:{item.name}; 功能介绍:{item.description or '本地企业文档检索'}; "
                f"关联知识库:{item.name}; 已索引文档:{count}"
                for item, count in rows
            ]
            lines.append("助手名称:全部知识库; 功能介绍:跨全部本地知识库混合检索")
            result = "\n".join(lines)
        monitor.report_tool_end(
            ASSISTANT_LIST_TOOL,
            {
                "elapsed_ms": round((monotonic() - started_at) * 1000),
                "knowledge_base_count": len(rows),
                "returned_chars": len(result),
            },
        )
        return result
    except Exception as exc:
        monitor.report_tool_error(
            ASSISTANT_LIST_TOOL,
            repr(exc),
            {"elapsed_ms": round((monotonic() - started_at) * 1000)},
        )
        return f"查询本地知识库失败：{exc}"


@tool
def ask_knowledge_base(chat_name: str, question: str) -> str:
    """
    Ask one local knowledge base, or all local knowledge bases, using hybrid retrieval and rerank.

    :param chat_name: Assistant name from get_assistant_list, or "全部知识库".
    :param question: Question that must be answered from indexed local documents.
    """
    tool_started_at = monotonic()
    monitor.report_tool(
        tool_name=ASK_KNOWLEDGE_BASE_TOOL,
        args={"chat_name": chat_name, "question": question},
    )
    try:
        knowledge_bases = _resolve_knowledge_bases(chat_name)
        if not knowledge_bases:
            payload = {
                "chat_name": chat_name,
                "question": question,
                "status": "knowledge_base_not_found",
                "elapsed_ms": round((monotonic() - tool_started_at) * 1000),
            }
            write_audit_event("rag_search", payload)
            monitor.report_tool_end(ASK_KNOWLEDGE_BASE_TOOL, payload)
            return f"没有找到名为“{chat_name}”的本地知识库。"

        retrieval_started_at = monotonic()
        if len(knowledge_bases) == 1:
            hits = hybrid_search(question, knowledge_bases[0].id)
        else:
            hits = hybrid_search_many(question, [knowledge_base.id for knowledge_base in knowledge_bases])
        retrieval_elapsed_ms = round((monotonic() - retrieval_started_at) * 1000)

        hits.sort(key=lambda item: item.score, reverse=True)
        write_audit_event(
            "rag_search",
            {
                "chat_name": chat_name,
                "knowledge_bases": [item.name for item in knowledge_bases],
                "knowledge_base_ids": [item.id for item in knowledge_bases],
                "question": question,
                "hit_count": len(hits),
                "elapsed_ms": retrieval_elapsed_ms,
                "hits": [_hit_metadata(hit) for hit in hits[:8]],
            },
        )

        limited_hits, budget_metadata = _limit_hits_for_answer(hits)
        if not limited_hits:
            result = "本地知识库没有检索到足以回答该问题的内容。"
            payload = {
                "chat_name": chat_name,
                "question": question,
                "knowledge_bases": [item.name for item in knowledge_bases],
                "retrieval_elapsed_ms": retrieval_elapsed_ms,
                "answer_elapsed_ms": 0,
                "elapsed_ms": round((monotonic() - tool_started_at) * 1000),
                "returned_chars": len(result),
                **budget_metadata,
            }
            write_audit_event("rag_search_empty", payload)
            monitor.report_tool_end(ASK_KNOWLEDGE_BASE_TOOL, payload)
            return result

        answer_started_at = monotonic()
        result = _answer(question, limited_hits)
        answer_elapsed_ms = round((monotonic() - answer_started_at) * 1000)
        payload = {
            "chat_name": chat_name,
            "question": question,
            "knowledge_bases": [item.name for item in knowledge_bases],
            "knowledge_base_ids": [item.id for item in knowledge_bases],
            "retrieval_elapsed_ms": retrieval_elapsed_ms,
            "answer_elapsed_ms": answer_elapsed_ms,
            "elapsed_ms": round((monotonic() - tool_started_at) * 1000),
            "returned_chars": len(result),
            **budget_metadata,
        }
        write_audit_event("rag_answer", payload)
        monitor.report_tool_end(ASK_KNOWLEDGE_BASE_TOOL, payload)
        return result
    except Exception as exc:
        payload = {
            "chat_name": chat_name,
            "question": question,
            "error": repr(exc),
            "elapsed_ms": round((monotonic() - tool_started_at) * 1000),
        }
        write_audit_event("rag_search_error", payload)
        monitor.report_tool_error(ASK_KNOWLEDGE_BASE_TOOL, repr(exc), payload)
        return f"本地知识库问答失败：{exc}"
