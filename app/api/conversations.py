"""Chat conversation history API."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.conversation_store import get_or_create_conversation
from app.auth.dependencies import get_current_user
from app.memory.checkpoint import clear_short_term_memory_for_thread
from app.rag.database import session_scope
from app.rag.models import ChatConversation, ChatMessage, User
from app.rag.schemas import (
    ChatConversationCreate,
    ChatConversationDetail,
    ChatConversationResponse,
    ChatConversationUpdate,
    ChatMessageResponse,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def _conversation_response(item: ChatConversation) -> ChatConversationResponse:
    return ChatConversationResponse(
        id=item.id,
        thread_id=item.thread_id,
        title=item.title,
        is_archived=item.is_archived,
        created_at=item.created_at,
        updated_at=item.updated_at,
        last_message_at=item.last_message_at,
    )


def _message_response(item: ChatMessage) -> ChatMessageResponse:
    return ChatMessageResponse(
        id=item.id,
        role=item.role,
        content=item.content,
        events=item.events,
        files=item.files,
        created_at=item.created_at,
    )


@router.get("", response_model=list[ChatConversationResponse])
def list_conversations(current_user: User = Depends(get_current_user)):
    with session_scope() as session:
        items = session.scalars(
            select(ChatConversation)
            .where(
                ChatConversation.user_id == current_user.id,
                ChatConversation.is_archived.is_(False),
            )
            .order_by(ChatConversation.last_message_at.desc())
            .limit(50)
        ).all()
        return [_conversation_response(item) for item in items]


@router.post("", response_model=ChatConversationResponse, status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ChatConversationCreate,
    current_user: User = Depends(get_current_user),
):
    thread_id = payload.thread_id or str(uuid.uuid4())
    with session_scope() as session:
        item = get_or_create_conversation(
            session,
            user_id=current_user.id,
            thread_id=thread_id,
            title=(payload.title or "新聊天").strip() or "新聊天",
        )
        return _conversation_response(item)


@router.get("/{thread_id}", response_model=ChatConversationDetail)
def get_conversation(thread_id: str, current_user: User = Depends(get_current_user)):
    with session_scope() as session:
        item = session.scalar(
            select(ChatConversation).where(
                ChatConversation.user_id == current_user.id,
                ChatConversation.thread_id == thread_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        messages = session.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == item.id)
            .order_by(ChatMessage.created_at.asc())
        ).all()
        return ChatConversationDetail(
            **_conversation_response(item).model_dump(),
            messages=[_message_response(message) for message in messages],
        )


@router.patch("/{thread_id}", response_model=ChatConversationResponse)
def update_conversation(
    thread_id: str,
    payload: ChatConversationUpdate,
    current_user: User = Depends(get_current_user),
):
    with session_scope() as session:
        item = session.scalar(
            select(ChatConversation).where(
                ChatConversation.user_id == current_user.id,
                ChatConversation.thread_id == thread_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        if payload.title is not None:
            item.title = payload.title.strip()
        if payload.is_archived is not None:
            item.is_archived = payload.is_archived
        session.flush()
        return _conversation_response(item)


@router.delete("/{thread_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(thread_id: str, current_user: User = Depends(get_current_user)):
    with session_scope() as session:
        item = session.scalar(
            select(ChatConversation).where(
                ChatConversation.user_id == current_user.id,
                ChatConversation.thread_id == thread_id,
            )
        )
        if item is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        item.is_archived = True
        session.flush()
    try:
        clear_short_term_memory_for_thread(f"{current_user.id}__{thread_id}")
    except Exception:
        pass
