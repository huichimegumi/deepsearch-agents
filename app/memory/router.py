"""User memory management API."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import get_current_user
from app.memory.schemas import (
    MemoryCreate,
    MemoryResponse,
    MemorySearchHit,
    MemorySearchRequest,
    MemoryUpdate,
)
from app.memory.service import (
    MemoryHit,
    create_memory,
    delete_memory,
    list_memories,
    search_memories,
    update_memory,
)
from app.rag.models import User, UserMemory

router = APIRouter(prefix="/api/memories", tags=["memories"])


def _memory_response(memory: UserMemory) -> MemoryResponse:
    return MemoryResponse(
        id=memory.id,
        user_id=memory.user_id,
        thread_id=memory.thread_id,
        source_message_id=memory.source_message_id,
        memory_type=memory.memory_type,
        content=memory.content,
        summary=memory.summary,
        confidence=memory.confidence,
        access_count=memory.access_count,
        metadata=memory.metadata_,
        is_deleted=memory.is_deleted,
        created_at=memory.created_at,
        updated_at=memory.updated_at,
        last_used_at=memory.last_used_at,
    )


def _search_hit_response(hit: MemoryHit) -> MemorySearchHit:
    return MemorySearchHit(**_memory_response(hit.memory).model_dump(), score=hit.score)


@router.get("", response_model=list[MemoryResponse])
def list_user_memories(
    include_deleted: bool = Query(default=False),
    memory_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    rows = list_memories(
        user_id=current_user.id,
        include_deleted=include_deleted,
        memory_type=memory_type,
    )
    return [_memory_response(item) for item in rows]


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
def create_user_memory(payload: MemoryCreate, current_user: User = Depends(get_current_user)):
    try:
        memory = create_memory(
            user_id=current_user.id,
            thread_id=payload.thread_id,
            content=payload.content,
            memory_type=payload.memory_type,
            confidence=payload.confidence,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _memory_response(memory)


@router.post("/search", response_model=list[MemorySearchHit])
def search_user_memories(
    payload: MemorySearchRequest,
    current_user: User = Depends(get_current_user),
):
    hits = search_memories(user_id=current_user.id, query=payload.query, limit=payload.limit)
    return [_search_hit_response(hit) for hit in hits]


@router.patch("/{memory_id}", response_model=MemoryResponse)
def patch_user_memory(
    memory_id: str,
    payload: MemoryUpdate,
    current_user: User = Depends(get_current_user),
):
    try:
        memory = update_memory(
            user_id=current_user.id,
            memory_id=memory_id,
            content=payload.content,
            memory_type=payload.memory_type,
            confidence=payload.confidence,
            is_deleted=payload.is_deleted,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return _memory_response(memory)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_memory(memory_id: str, current_user: User = Depends(get_current_user)):
    if not delete_memory(user_id=current_user.id, memory_id=memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
