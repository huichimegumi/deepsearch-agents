"""Import an existing directory tree into the local knowledge-base stack."""

import argparse
from hashlib import sha256
import mimetypes
from pathlib import Path

from sqlalchemy import select

from app.rag.database import init_schema, session_scope
from app.rag.models import Document, IndexJob, KnowledgeBase
from app.rag.parsing import SUPPORTED_EXTENSIONS
from app.rag.storage import upload_path
from app.rag.tasks import index_document


def import_directory(root: Path) -> tuple[int, int]:
    init_schema()
    knowledge_base_count = 0
    document_count = 0
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        with session_scope() as session:
            knowledge_base = session.scalar(
                select(KnowledgeBase).where(KnowledgeBase.name == directory.name)
            )
            if knowledge_base is None:
                knowledge_base = KnowledgeBase(
                    name=directory.name,
                    description=f"从 {directory.name} 示例目录导入的本地知识库",
                )
                session.add(knowledge_base)
                session.flush()
            knowledge_base_id = knowledge_base.id
        knowledge_base_count += 1

        for path in sorted(directory.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            checksum = sha256(path.read_bytes()).hexdigest()
            with session_scope() as session:
                existing = session.scalar(
                    select(Document).where(
                        Document.knowledge_base_id == knowledge_base_id,
                        Document.sha256 == checksum,
                    )
                )
                if existing:
                    continue
                document = Document(
                    knowledge_base_id=knowledge_base_id,
                    filename=path.name,
                    object_key="pending",
                    content_type=mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream",
                    size_bytes=path.stat().st_size,
                    sha256=checksum,
                )
                session.add(document)
                session.flush()
                document.object_key = f"{knowledge_base_id}/{document.id}/{path.name}"
                job = IndexJob(
                    document_id=document.id,
                    knowledge_base_id=knowledge_base_id,
                    message="示例文档已导入，等待索引",
                )
                session.add(job)
                session.flush()
                object_key = document.object_key
                content_type = document.content_type
                job_id = job.id
            upload_path(path, object_key, content_type)
            task = index_document.delay(job_id)
            with session_scope() as session:
                job = session.get(IndexJob, job_id)
                if job:
                    job.celery_task_id = task.id
            document_count += 1
    return knowledge_base_count, document_count


def main() -> None:
    parser = argparse.ArgumentParser(description="批量导入本地知识库文档")
    parser.add_argument("root", type=Path, nargs="?", default=Path("docs/knowledge_base"))
    args = parser.parse_args()
    if not args.root.is_dir():
        raise SystemExit(f"知识库目录不存在: {args.root}")
    knowledge_bases, documents = import_directory(args.root)
    print(f"已扫描 {knowledge_bases} 个知识库，提交 {documents} 份新文档索引任务。")


if __name__ == "__main__":
    main()

