"""Exact normalized passage anchors, with distinct evidence units and alternative locations."""

import hashlib
import re


def normalized(text: str) -> str:
    return re.sub(r"\s+", "", text)


def passage_sha256(text: str) -> str:
    return hashlib.sha256(normalized(text).encode("utf-8")).hexdigest()


def matches(unit: dict, hit: dict) -> bool:
    content = normalized(hit["content"])
    return any(
        hit["document_sha256"] == location["document_sha256"]
        and normalized(location["anchor"]) in content
        for location in unit["locations"]
    )


def score_retrieval(case: dict, hits: list[dict], k: int = 5) -> dict:
    if not case["answerable"]:
        return {
            "recall_at_5": None,
            "mrr_at_5": None,
            "all_evidence_found": None,
            "no_answer": True,
            "retrieved_candidates": len(hits[:k]),
            "abstention_evaluated": False,
        }
    units = case["evidence_units"]
    found = {
        unit["id"]: next((rank for rank, hit in enumerate(hits[:k], 1) if matches(unit, hit)), None)
        for unit in units
    }
    ranks = [rank for rank in found.values() if rank is not None]
    return {
        "recall_at_5": len(ranks) / len(units),
        "mrr_at_5": 1 / min(ranks) if ranks else 0.0,
        "all_evidence_found": len(ranks) == len(units),
        "evidence_unit_ranks": found,
        "no_answer": False,
    }


def validate_cases(cases: list[dict]) -> None:
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case IDs")
    for case in cases:
        units = case["evidence_units"]
        if case["split"] not in {"dev", "test"}:
            raise ValueError("Invalid dataset split")
        if not case["question"].strip() or bool(units) != case["answerable"]:
            raise ValueError("Question/answerability and evidence units disagree")
        if len({unit["id"] for unit in units}) != len(units):
            raise ValueError("Duplicate evidence unit IDs")
        for unit in units:
            if not unit["locations"]:
                raise ValueError("Evidence unit needs at least one location")
            for location in unit["locations"]:
                if not normalized(location["anchor"]):
                    raise ValueError("Empty evidence anchor")
                if passage_sha256(location["anchor"]) != location["anchor_sha256"]:
                    raise ValueError("Evidence anchor hash mismatch")
