"""DeepAgents tools for the PostgreSQL/Qdrant local knowledge-base service."""

from langchain_core.tools import tool
from sqlalchemy import func, select

from app.api.monitor import monitor
from app.rag.database import session_scope
from app.rag.models import Document, KnowledgeBase
from app.rag.retrieval import RetrievedChunk, hybrid_search


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
    from app.agent.llm import model

    response = model.invoke([{"role": "user", "content": prompt}])
    return getattr(response, "content", str(response))


@tool
def get_assistant_list() -> str:
    """查询本地可用知识库助手及其中已完成索引的文档数量。"""
    monitor.report_tool(tool_name="本地知识库助手列表查询工具：get_assistant_list")
    try:
        rows = _ready_knowledge_bases()
        if not rows:
            return "当前没有可用的本地知识库，请先通过知识库管理页面上传并完成索引。"
        lines = [
            f"助手名称:{item.name}; 功能介绍:{item.description or '本地企业文档检索'}; "
            f"关联知识库:{item.name}; 已索引文档:{count}"
            for item, count in rows
        ]
        lines.append("助手名称:全部知识库; 功能介绍:跨全部本地知识库混合检索")
        return "\n".join(lines)
    except Exception as exc:
        return f"查询本地知识库失败：{exc}"


@tool
def create_ask_delete(chat_name: str, question: str) -> str:
    """
    向指定本地知识库助手提问，并返回经过混合检索和 rerank 的带页码答案。

    :param chat_name: 来自 get_assistant_list 的助手名称，也可以使用“全部知识库”
    :param question: 需要根据内部文档回答的问题
    """
    monitor.report_tool(
        tool_name="本地知识库混合检索工具：create_ask_delete",
        args={"chat_name": chat_name, "question": question},
    )
    try:
        knowledge_bases = _resolve_knowledge_bases(chat_name)
        if not knowledge_bases:
            return f"没有找到名为“{chat_name}”的本地知识库。"
        hits: list[RetrievedChunk] = []
        for knowledge_base in knowledge_bases:
            hits.extend(hybrid_search(question, knowledge_base.id))
        hits.sort(key=lambda item: item.score, reverse=True)
        hits = hits[:8]
        if not hits:
            return "本地知识库没有检索到足以回答该问题的内容。"
        return _answer(question, hits)
    except Exception as exc:
        return f"本地知识库问答失败：{exc}"
