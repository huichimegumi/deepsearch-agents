"""Rolling per-thread conversation summaries for prompt memory."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select

from app.rag.database import session_scope
from app.rag.models import ChatConversation, ChatMessage, utcnow

RECENT_MESSAGE_LIMIT = 8
MAX_MESSAGE_CHARS = 1200
MAX_SUMMARY_CHARS = 2800


@dataclass(frozen=True)
class ConversationContext:
    summary: str
    recent_messages: list[tuple[str, str]]


def _clip_text(value: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    clean = " ".join(value.strip().split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _format_messages(messages: list[tuple[str, str]]) -> str:
    lines: list[str] = []
    for role, content in messages:
        label = "用户" if role == "user" else "助手"
        lines.append(f"- {label}: {_clip_text(content)}")
    return "\n".join(lines)


def get_conversation_context(
    *,
    user_id: str,
    thread_id: str,
    recent_limit: int = RECENT_MESSAGE_LIMIT,
    exclude_message_id: str | None = None,
) -> ConversationContext:
    with session_scope() as session:
        conversation = session.scalar(
            select(ChatConversation).where(
                ChatConversation.user_id == user_id,
                ChatConversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return ConversationContext(summary="", recent_messages=[])

        statement = select(ChatMessage).where(ChatMessage.conversation_id == conversation.id)
        if exclude_message_id:
            statement = statement.where(ChatMessage.id != exclude_message_id)
        rows = session.scalars(
            statement.order_by(ChatMessage.created_at.desc()).limit(recent_limit)
        ).all()

        recent = [(message.role, message.content) for message in reversed(rows)]
        return ConversationContext(summary=conversation.summary or "", recent_messages=recent)


def format_conversation_context_for_prompt(context: ConversationContext) -> str:
    if not context.summary and not context.recent_messages:
        return ""

    sections = [
        "【当前会话历史记忆】",
        "以下内容概括当前 thread 的历史。若与用户本轮明确要求冲突，以本轮要求为准。",
    ]
    if context.summary:
        sections.append(f"会话摘要:\n{context.summary}")
    if context.recent_messages:
        sections.append(f"最近消息:\n{_format_messages(context.recent_messages)}")
    return "\n\n".join(sections)


def build_summary_prompt(
    *,
    existing_summary: str,
    new_messages: list[tuple[str, str]],
) -> str:
    return f"""
你是会话摘要维护器。请更新当前 thread 的滚动摘要，供后续同一会话继续使用。

要求:
1. 只保留对后续对话有帮助的信息，包括用户目标、已完成结论、关键约束、待办事项、文件/产物线索。
2. 不要保存 API key、密码、token、验证码等敏感秘密。
3. 不要加入助手猜测或未确认事实。
4. 用中文，控制在 {MAX_SUMMARY_CHARS} 字以内。
5. 输出纯摘要文本，不要 Markdown 标题。

已有摘要:
{existing_summary or "无"}

新增消息:
{_format_messages(new_messages)}
"""


def summarize_conversation(existing_summary: str, new_messages: list[tuple[str, str]]) -> str:
    if not new_messages:
        return existing_summary

    from app.agent.llm import get_model

    response = get_model().invoke(
        [{"role": "user", "content": build_summary_prompt(
            existing_summary=existing_summary,
            new_messages=new_messages,
        )}]
    )
    content = getattr(response, "content", str(response)).strip()
    return _clip_text(content, MAX_SUMMARY_CHARS)


def update_conversation_summary(*, user_id: str, thread_id: str) -> str:
    with session_scope() as session:
        conversation = session.scalar(
            select(ChatConversation).where(
                ChatConversation.user_id == user_id,
                ChatConversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return ""

        message_count = session.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.conversation_id == conversation.id
            )
        )
        message_count = int(message_count or 0)
        previous_count = int(conversation.summary_message_count or 0)
        if message_count <= previous_count:
            return conversation.summary or ""

        rows = session.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation.id)
            .order_by(ChatMessage.created_at.asc())
            .offset(previous_count)
        ).all()
        new_messages = [(message.role, message.content) for message in rows]
        existing_summary = conversation.summary or ""

    summary = summarize_conversation(existing_summary, new_messages)

    with session_scope() as session:
        conversation = session.scalar(
            select(ChatConversation).where(
                ChatConversation.user_id == user_id,
                ChatConversation.thread_id == thread_id,
            )
        )
        if conversation is None:
            return summary
        conversation.summary = summary
        conversation.summary_message_count = message_count
        conversation.summary_updated_at = utcnow()
        session.flush()
    return summary
