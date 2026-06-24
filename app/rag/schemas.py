"""Pydantic request and response contracts for knowledge-base APIs."""

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    document_count: int
    created_at: datetime
    updated_at: datetime


class DocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    filename: str
    content_type: str
    size_bytes: int
    sha256: str
    status: str
    chunk_count: int
    error_message: str | None
    created_at: datetime
    indexed_at: datetime | None


class IndexJobResponse(BaseModel):
    id: str
    document_id: str | None
    knowledge_base_id: str
    celery_task_id: str | None
    kind: str
    status: str
    progress: int
    message: str
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class UploadDocumentResponse(BaseModel):
    document: DocumentResponse
    job: IndexJobResponse | None
    deduplicated: bool = False


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8000)


class SearchHitResponse(BaseModel):
    chunk_id: str
    content: str
    filename: str
    page_start: int | None
    page_end: int | None
    section: str | None
    score: float
    citation: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHitResponse]


class ChatConversationCreate(BaseModel):
    thread_id: str | None = None
    title: str | None = Field(default=None, max_length=180)


class ChatConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    is_archived: bool | None = None


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    events: list | None = None
    files: list | None = None
    created_at: datetime


class ChatConversationResponse(BaseModel):
    id: str
    thread_id: str
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime


class ChatConversationDetail(ChatConversationResponse):
    messages: list[ChatMessageResponse]
