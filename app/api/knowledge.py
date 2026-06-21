"""Knowledge-base management, ingestion and retrieval HTTP API."""

from hashlib import sha256
from pathlib import Path
import tempfile

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.rag.database import session_scope
from app.rag.models import Document, IndexJob, KnowledgeBase
from app.rag.parsing import SUPPORTED_EXTENSIONS
from app.rag.retrieval import hybrid_search
from app.rag.schemas import (
    DocumentResponse,
    IndexJobResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    UploadDocumentResponse,
)
from app.rag.storage import delete_object, upload_path
from app.rag.tasks import index_document
from app.rag.vector_store import delete_document_vectors


router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])
MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def _knowledge_response(item: KnowledgeBase, document_count: int) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        document_count=document_count,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _document_response(item: Document) -> DocumentResponse:
    return DocumentResponse(
        id=item.id,
        knowledge_base_id=item.knowledge_base_id,
        filename=item.filename,
        content_type=item.content_type,
        size_bytes=item.size_bytes,
        sha256=item.sha256,
        status=item.status,
        chunk_count=item.chunk_count,
        error_message=item.error_message,
        created_at=item.created_at,
        indexed_at=item.indexed_at,
    )


def _job_response(item: IndexJob) -> IndexJobResponse:
    return IndexJobResponse(
        id=item.id,
        document_id=item.document_id,
        knowledge_base_id=item.knowledge_base_id,
        celery_task_id=item.celery_task_id,
        kind=item.kind,
        status=item.status,
        progress=item.progress,
        message=item.message,
        error_message=item.error_message,
        created_at=item.created_at,
        started_at=item.started_at,
        finished_at=item.finished_at,
    )


def _enqueue(job_id: str) -> None:
    try:
        task = index_document.delay(job_id)
        with session_scope() as session:
            job = session.get(IndexJob, job_id)
            if job:
                job.celery_task_id = task.id
    except Exception as exc:
        with session_scope() as session:
            job = session.get(IndexJob, job_id)
            if job:
                job.status = "failed"
                job.error_message = f"无法提交 Celery 任务: {exc}"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="索引服务暂不可用，请确认 Redis 和 Celery worker 已启动",
        ) from exc


@router.get("", response_model=list[KnowledgeBaseResponse])
def list_knowledge_bases():
    with session_scope() as session:
        rows = session.execute(
            select(KnowledgeBase, func.count(Document.id))
            .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.created_at.desc())
        ).all()
        return [_knowledge_response(item, count) for item, count in rows]


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
def create_knowledge_base(payload: KnowledgeBaseCreate):
    try:
        with session_scope() as session:
            item = KnowledgeBase(name=payload.name.strip(), description=payload.description.strip())
            session.add(item)
            session.flush()
            return _knowledge_response(item, 0)
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="知识库名称已存在") from exc


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(knowledge_base_id: str, payload: KnowledgeBaseUpdate):
    with session_scope() as session:
        item = session.get(KnowledgeBase, knowledge_base_id)
        if item is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        if payload.name is not None:
            item.name = payload.name.strip()
        if payload.description is not None:
            item.description = payload.description.strip()
        count = session.scalar(
            select(func.count(Document.id)).where(Document.knowledge_base_id == item.id)
        ) or 0
        return _knowledge_response(item, count)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentResponse])
def list_documents(knowledge_base_id: str):
    with session_scope() as session:
        if session.get(KnowledgeBase, knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        items = session.scalars(
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.created_at.desc())
        ).all()
        return [_document_response(item) for item in items]


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=UploadDocumentResponse,
    status_code=202,
)
async def upload_document(knowledge_base_id: str, file: UploadFile = File(...)):
    filename = Path(file.filename or "document").name
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"不支持的文档格式: {extension}")

    with session_scope() as session:
        if session.get(KnowledgeBase, knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="知识库不存在")

    temporary = tempfile.NamedTemporaryFile(delete=False, suffix=extension)
    temporary_path = Path(temporary.name)
    digest = sha256()
    size = 0
    try:
        with temporary:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="文档不能超过 100MB")
                digest.update(chunk)
                temporary.write(chunk)
        checksum = digest.hexdigest()

        with session_scope() as session:
            existing = session.scalar(
                select(Document).where(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.sha256 == checksum,
                )
            )
            if existing:
                latest_job = session.scalar(
                    select(IndexJob)
                    .where(IndexJob.document_id == existing.id)
                    .order_by(IndexJob.created_at.desc())
                )
                return UploadDocumentResponse(
                    document=_document_response(existing),
                    job=_job_response(latest_job) if latest_job else None,
                    deduplicated=True,
                )

            document = session.scalar(
                select(Document).where(
                    Document.knowledge_base_id == knowledge_base_id,
                    Document.filename == filename,
                )
            )
            if document is None:
                document = Document(
                    knowledge_base_id=knowledge_base_id,
                    filename=filename,
                    object_key="pending",
                    content_type=file.content_type or "application/octet-stream",
                    size_bytes=size,
                    sha256=checksum,
                )
                session.add(document)
                session.flush()
                document.object_key = f"{knowledge_base_id}/{document.id}/{filename}"
            else:
                document.content_type = file.content_type or "application/octet-stream"
                document.size_bytes = size
                document.sha256 = checksum
                document.status = "pending"
                document.error_message = None
                document.chunk_count = 0
            job = IndexJob(
                document_id=document.id,
                knowledge_base_id=knowledge_base_id,
                message="文档已上传，等待索引",
            )
            session.add(job)
            session.flush()
            document_id = document.id
            job_id = job.id
            object_key = document.object_key
            document_response = _document_response(document)
            job_response = _job_response(job)

        try:
            upload_path(temporary_path, object_key, file.content_type or "application/octet-stream")
        except Exception as exc:
            with session_scope() as session:
                failed_document = session.get(Document, document_id)
                failed_job = session.get(IndexJob, job_id)
                if failed_document:
                    failed_document.status = "failed"
                    failed_document.error_message = f"MinIO 上传失败: {exc}"
                if failed_job:
                    failed_job.status = "failed"
                    failed_job.error_message = f"MinIO 上传失败: {exc}"
            raise HTTPException(
                status_code=503,
                detail="对象存储暂不可用，请确认 MinIO 已启动",
            ) from exc
        _enqueue(job_id)
        return UploadDocumentResponse(document=document_response, job=job_response)
    finally:
        temporary_path.unlink(missing_ok=True)


@router.post("/documents/{document_id}/reindex", response_model=IndexJobResponse, status_code=202)
def reindex_document(document_id: str):
    with session_scope() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        document.status = "pending"
        job = IndexJob(
            document_id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            message="等待重新索引",
        )
        session.add(job)
        session.flush()
        response = _job_response(job)
        job_id = job.id
    _enqueue(job_id)
    return response


@router.delete("/documents/{document_id}", status_code=204)
def remove_document(document_id: str):
    with session_scope() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="文档不存在")
        object_key = document.object_key
    delete_document_vectors(document_id)
    delete_object(object_key)
    with session_scope() as session:
        document = session.get(Document, document_id)
        if document:
            session.delete(document)


@router.delete("/{knowledge_base_id}", status_code=204)
def remove_knowledge_base(knowledge_base_id: str):
    with session_scope() as session:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
        documents = list(
            session.scalars(
                select(Document).where(Document.knowledge_base_id == knowledge_base_id)
            ).all()
        )
        stored_objects = [(document.id, document.object_key) for document in documents]
    for document_id, object_key in stored_objects:
        delete_document_vectors(document_id)
        delete_object(object_key)
    with session_scope() as session:
        knowledge_base = session.get(KnowledgeBase, knowledge_base_id)
        if knowledge_base:
            session.delete(knowledge_base)


@router.get("/index-jobs/{job_id}", response_model=IndexJobResponse)
def get_index_job(job_id: str):
    with session_scope() as session:
        job = session.get(IndexJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="索引任务不存在")
        return _job_response(job)


@router.post("/{knowledge_base_id}/search", response_model=SearchResponse)
def search_knowledge_base(knowledge_base_id: str, payload: SearchRequest):
    with session_scope() as session:
        if session.get(KnowledgeBase, knowledge_base_id) is None:
            raise HTTPException(status_code=404, detail="知识库不存在")
    hits = hybrid_search(payload.query, knowledge_base_id)
    return SearchResponse(
        query=payload.query,
        hits=[
            SearchHitResponse(
                chunk_id=hit.chunk_id,
                content=hit.content,
                filename=hit.filename,
                page_start=hit.page_start,
                page_end=hit.page_end,
                section=hit.section,
                score=hit.score,
                citation=hit.citation,
            )
            for hit in hits
        ],
    )
