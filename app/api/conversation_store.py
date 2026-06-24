"""Persistence helpers for chat conversations."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.rag.database import session_scope
from app.rag.models import ChatConversation, ChatMessage, utcnow


def build_title(content: str) -> str:
    clean = " ".join(content.strip().split())
    if not clean:
        return "新聊天"
    return clean[:48]


def get_or_create_conversation(
    session: Session,
    *,
    user_id: str,
    thread_id: str,
    title: str | None = None,
) -> ChatConversation:
    conversation = session.scalar(
        select(ChatConversation).where(
            ChatConversation.user_id == user_id,
            ChatConversation.thread_id == thread_id,
        )
    )
    if conversation is not None:
        return conversation

    now = utcnow()
    conversation = ChatConversation(
        user_id=user_id,
        thread_id=thread_id,
        title=title or "新聊天",
        created_at=now,
        updated_at=now,
        last_message_at=now,
    )
    session.add(conversation)
    session.flush()
    return conversation


def append_message(
    *,
    user_id: str,
    thread_id: str,
    role: str,
    content: str,
    events: list[dict[str, Any]] | None = None,
    files: list[dict[str, Any]] | None = None,
    created_at: datetime | None = None,
) -> ChatMessage:
    with session_scope() as session:
        conversation = get_or_create_conversation(
            session,
            user_id=user_id,
            thread_id=thread_id,
            title=build_title(content) if role == "user" else None,
        )
        message = ChatMessage(
            conversation_id=conversation.id,
            role=role,
            content=content,
            events=events,
            files=files,
            created_at=created_at or utcnow(),
        )
        session.add(message)

        if role == "user" and conversation.title == "新聊天":
            conversation.title = build_title(content)
        conversation.last_message_at = message.created_at
        conversation.updated_at = message.created_at
        session.flush()
        return message
