"""One-shot validation of the frozen hybrid RFC QA route; does not open references."""

import asyncio
import json
import subprocess

from sqlalchemy import select

from app.rag.database import session_scope
from app.rag.models import Chunk, Document, KnowledgeBase
from app.research.rfc_demo import DEMO_DIGESTS, KB_NAME, run_rfc_qa
from app.research.storage import write_json
from evals.public_benchmarks.score import model_for
from evals.rfc_demo.verify import HERE, ROOT, SEALED, sha

OUTPUT = ROOT / "evals/results/rfc-demo-v1-validation"
FROZEN = "ccab4ecb20d47f08118fe17c2bb4ca77c1bbd1f6"


def index_digest():
    with session_scope() as session:
        docs = session.execute(
            select(Document.filename, Document.sha256, Document.status)
            .join(KnowledgeBase)
            .where(KnowledgeBase.name == KB_NAME)
            .order_by(Document.filename)
        ).all()
        if len(docs) != len(DEMO_DIGESTS) or dict((n, h) for n, h, _ in docs) != DEMO_DIGESTS:
            raise ValueError("unexpected_validation_documents")
        if any(status != "ready" for _, _, status in docs):
            raise ValueError("validation_index_not_ready")
        rows = session.execute(
            select(Document.filename, Chunk.id, Chunk.chunk_index, Chunk.section, Chunk.content)
            .join(Document)
            .join(KnowledgeBase, Document.knowledge_base_id == KnowledgeBase.id)
            .where(KnowledgeBase.name == KB_NAME)
            .order_by(Document.filename, Chunk.chunk_index)
        ).all()
    if {row[0] for row in rows} != set(DEMO_DIGESTS):
        raise ValueError("empty_validation_index")
    return sha(json.dumps([tuple(r) for r in rows], ensure_ascii=False).encode())


async def run():
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    if commit != FROZEN or OUTPUT.exists():
        raise ValueError("validation_requires_original_commit_and_unused_output")
    lock = json.loads((HERE / "suite.lock.json").read_bytes())
    raw = (SEALED / "questions.json").read_bytes()
    if sha(raw) != lock["splits"]["sealed"]["sha256"]["questions.json"]:
        raise ValueError("sealed_questions_changed")
    tasks = json.loads(raw)
    if (
        len(tasks) != 5
        or [q["id"] for q in tasks] != [f"H{i:02d}" for i in range(1, 6)]
        or any(set(q) != {"id", "question"} for q in tasks)
    ):
        raise ValueError("unexpected_validation_packet")
    app_delta = subprocess.check_output(["git", "diff", "HEAD", "--", "app"], cwd=ROOT)
    if app_delta:
        raise ValueError("application_differs_from_frozen_commit")
    manifest = {
        "commit": commit,
        "route": "hybrid",
        "model": "qwen-flash",
        "question_sha256": sha(raw),
        "index_sha256": index_digest(),
        "runner_sha256": sha((HERE / "validate_demo.py").read_bytes()),
        "max_requests": 5,
    }
    model = model_for("qwen")
    OUTPUT.mkdir(mode=0o700, exist_ok=False)
    write_json(OUTPUT / "manifest.json", manifest)
    rows = []
    for task in tasks:
        if index_digest() != manifest["index_sha256"]:
            raise ValueError("validation_index_changed")
        result = await run_rfc_qa(
            task["question"], OUTPUT / task["id"], model=model, retry_format=False
        )
        rows.append({"id": task["id"], **result})
        write_json(OUTPUT / "results.json", {"complete": False, "rows": rows})
        print(task["id"], result["status"], flush=True)
    if index_digest() != manifest["index_sha256"]:
        raise ValueError("validation_index_changed")
    write_json(OUTPUT / "results.json", {"complete": True, "rows": rows})


if __name__ == "__main__":
    asyncio.run(run())
