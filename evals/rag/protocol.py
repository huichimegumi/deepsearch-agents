"""Validate frozen dataset/configuration/corpus contracts before executing a test split."""

import hashlib
import json
from pathlib import Path

from evals.rag.scoring import normalized, validate_cases
from evals.runners.common import load_jsonl

MODES = ("A_vector", "B_hybrid", "C_hybrid_rerank")
CONFIG_KEYS = (
    "embedding_model",
    "rerank_model",
    "vector_top_k",
    "lexical_top_k",
    "chunk_size",
    "chunk_overlap",
    "top_k",
    "relevance_threshold",
    "score_scope",
)


def canonical_sha256(value) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def validate_splits(development: list[dict], test: list[dict]) -> None:
    validate_cases(development + test)
    if any(case["split"] != "dev" for case in development):
        raise ValueError("Development dataset contains another split")
    if any(case["split"] != "test" for case in test):
        raise ValueError("Test dataset contains another split")
    dev_questions = {normalized(case["question"]) for case in development}
    if any(normalized(case["question"]) in dev_questions for case in test):
        raise ValueError("A test question duplicates a development question")


def check_lock(
    path: Path,
    cases: list[dict],
    split: str,
    configuration: dict,
    corpus_sha256: str,
    model_artifacts: list[dict],
) -> dict:
    lock = json.loads(path.read_text(encoding="utf-8"))
    if canonical_sha256(cases) != lock["datasets"][split]["canonical_sha256"]:
        raise ValueError("Frozen dataset content changed")
    if corpus_sha256 != lock["corpus_sha256"]:
        raise ValueError("Frozen indexed corpus changed")
    if {key: configuration[key] for key in CONFIG_KEYS} != lock["configuration"]:
        raise ValueError("Frozen retrieval configuration changed")
    if sorted(configuration["knowledge_base_names"]) != lock["knowledge_base_names"]:
        raise ValueError("Frozen knowledge base scope changed")
    if model_artifacts != lock["model_artifacts"]:
        raise ValueError("Frozen local model artifacts changed")
    if lock["modes"] != list(MODES):
        raise ValueError("Frozen retrieval modes changed")
    return lock


def check_dataset_files(lock_path: Path) -> None:
    """Also detect development/test overlap or unintentional edits to the other split."""
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    datasets = {}
    for split, spec in lock["datasets"].items():
        path = (lock_path.parent / spec["path"]).resolve()
        if not path.is_relative_to(lock_path.parent.resolve()):
            raise ValueError("Frozen dataset path is outside its suite directory")
        datasets[split] = load_jsonl(path)
        if canonical_sha256(datasets[split]) != spec["canonical_sha256"]:
            raise ValueError(f"Frozen {split} dataset content changed")
        if len(datasets[split]) != spec["count"]:
            raise ValueError("Frozen dataset count changed")
    validate_splits(datasets["dev"], datasets["test"])
