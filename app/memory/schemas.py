"""Pydantic contracts for user memory APIs."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    memory_type: str = Field(default="fact", max_length=32)
    thread_id: str | None = Field(default=None, max_length=80)
    confidence: float = Field(default=0.9, ge=0, le=1)
    metadata: dict[str, Any] | None = None


class MemoryUpdate(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=4000)
    memory_type: str | None = Field(default=None, max_length=32)
    confidence: float | None = Field(default=None, ge=0, le=1)
    is_deleted: bool | None = None
    metadata: dict[str, Any] | None = None


class MemoryResponse(BaseModel):
    id: str
    user_id: str
    thread_id: str | None
    source_message_id: str | None
    memory_type: str
    content: str
    summary: str
    confidence: float
    access_count: int
    metadata: dict[str, Any] | None
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=6, ge=1, le=20)


class MemorySearchHit(MemoryResponse):
    score: float
