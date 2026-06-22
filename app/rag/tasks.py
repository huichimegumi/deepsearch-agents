"""Celery tasks that build and repair local RAG indexes."""

import shutil
import tempfile
from pathlib import Path

from celery.utils.log import get_task_logger
from redis import Redis
from sqlalchemy import delete

from app.rag.celery_app import celery_app
from app.rag.config import get_rag_settings
from app.rag.database import session_scope
from app.rag.embeddings import embed_documents
from app.rag.models import Chunk, Document, IndexJob, utcnow
from app.rag.parsing import chunk_blocks, lexicalize, parse_document
from app.rag.storage import download_path
from app.rag.vector_store import delete_document_vectors, upsert_chunks

logger = get_task_logger(__name__)


def _update_job(job_id: str, **values) -> None:
    with session_scope() as session:
        job = session.get(IndexJob, job_id)
        if job is None:
            return
        for key, value in values.items():
            setattr(job, key, value)


@celery_app.task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def index_document(self, job_id: str) -> dict[str, object]:
    _update_job(
        job_id,
        celery_task_id=self.request.id,
        status="running",
        progress=5,
        message="正在读取文档",
        started_at=utcnow(),
        error_message=None,
    )
    temporary_dir = Path(tempfile.mkdtemp(prefix="deepsearch-rag-"))
    document_lock = None
    try:
        with session_scope() as session:
            job = session.get(IndexJob, job_id)
            if job is None or job.document_id is None:
                raise ValueError(f"索引任务不存在: {job_id}")
            document = session.get(Document, job.document_id)
            if document is None:
                raise ValueError(f"文档不存在: {job.document_id}")
            document_id = document.id
            knowledge_base_id = document.knowledge_base_id
            object_key = document.object_key
            filename = document.filename
            document.status = "indexing"
            document.error_message = None

        document_lock = Redis.from_url(get_rag_settings().redis_url).lock(
            f"rag:index-document:{document_id}", timeout=3600
        )
        if not document_lock.acquire(blocking=True, blocking_timeout=30):
            raise RuntimeError("同一文档已有索引任务正在执行，请稍后重试")

        local_path = temporary_dir / Path(filename).name
        download_path(object_key, local_path)
        parsed_chunks = chunk_blocks(parse_document(local_path))
        if not parsed_chunks:
            raise ValueError("文档解析后没有可索引文本")

        _update_job(job_id, progress=35, message="正在生成本地向量")
        vectors = embed_documents([chunk.content for chunk in parsed_chunks])

        _update_job(job_id, progress=70, message="正在写入检索索引")
        delete_document_vectors(document_id)
        with session_scope() as session:
            session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            rows: list[Chunk] = []
            for index, item in enumerate(parsed_chunks):
                row = Chunk(
                    document_id=document_id,
                    knowledge_base_id=knowledge_base_id,
                    chunk_index=index,
                    content=item.content,
                    lexical_text=lexicalize(item.content),
                    page_start=item.page_start,
                    page_end=item.page_end,
                    section=item.section,
                    token_count=len(item.content),
                )
                session.add(row)
                rows.append(row)
            session.flush()
            points = [
                (
                    row.id,
                    vector,
                    {
                        "document_id": document_id,
                        "knowledge_base_id": knowledge_base_id,
                        "chunk_index": row.chunk_index,
                        "page_start": row.page_start,
                        "page_end": row.page_end,
                    },
                )
                for row, vector in zip(rows, vectors)
            ]
            upsert_chunks(points)

            document = session.get(Document, document_id)
            if document is not None:
                document.status = "ready"
                document.chunk_count = len(rows)
                document.indexed_at = utcnow()
                document.error_message = None

        _update_job(
            job_id,
            status="completed",
            progress=100,
            message=f"索引完成，共 {len(parsed_chunks)} 个片段",
            finished_at=utcnow(),
        )
        return {"document_id": document_id, "chunk_count": len(parsed_chunks)}
    except Exception as exc:
        logger.exception("Document indexing failed for job %s", job_id)
        _update_job(
            job_id,
            status="failed",
            message="索引失败",
            error_message=str(exc),
            finished_at=utcnow(),
        )
        with session_scope() as session:
            job = session.get(IndexJob, job_id)
            if job and job.document_id:
                document = session.get(Document, job.document_id)
                if document:
                    document.status = "failed"
                    document.error_message = str(exc)
        raise
    finally:
        if document_lock is not None and document_lock.owned():
            document_lock.release()
        shutil.rmtree(temporary_dir, ignore_errors=True)
