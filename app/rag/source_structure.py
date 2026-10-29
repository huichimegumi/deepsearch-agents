"""Opt-in exact document resolution and conservative indexed TOC selection.

Pure planning only: no model, database access, label lookup or production routing.
"""

import re
import unicodedata
from dataclasses import dataclass


def document_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name).casefold()
    normalized = re.sub(r"\.(?:pdf|docx?|txt|md|html?)$", "", normalized.strip())
    return re.sub(r"\s+", "", normalized)


@dataclass(frozen=True)
class SourceStructurePlan:
    status: str
    document_sha256: tuple[str, ...] = ()
    structural_ids: tuple[str, ...] = ()
    structure_status: str = "not_requested"


def requests_toc(query: str) -> bool:
    clauses = re.split(r"[。！？!?；;\n]", query)
    return any(
        re.search(r"目录|table\s+of\s+contents", clause, re.I)
        and not re.match(r"\s*(?:请)?(?:不要|不得|无需|不需要|do\s+not\b|don't\b)", clause, re.I)
        for clause in clauses
    )


def is_toc(content: str) -> bool:
    lines = [unicodedata.normalize("NFKC", line).strip() for line in content.splitlines()]
    if not any(
        re.sub(r"\s+", "", line).casefold() in {"目录", "contents", "tableofcontents"}
        for line in lines
    ):
        return False
    entries = set()
    for line in lines:
        match = re.match(
            r"^(?:第([一二三四五六七八九十百\d]+)章\s*|([0-9]{1,3})[\s、.．)]+)\S+", line
        )
        if match:
            entries.add(match.group(1) or match.group(2))
    return len(entries) >= 2


def plan_source_structure(
    query: str, corpus: dict, candidate_ids: list[str]
) -> SourceStructurePlan:
    """All source names must resolve; never guess aliases or pull chunks outside the pool."""
    if len(candidate_ids) != len(set(candidate_ids)) or any(i not in corpus for i in candidate_ids):
        raise ValueError("invalid_candidate_membership")
    titles = list(dict.fromkeys(re.findall(r"《([^《》\n]+)》", query)))
    if not titles:
        return SourceStructurePlan("no_explicit_source")
    if re.search(r"(?:不要|不得|不使用|不查|无需|排除|不依据|不参考).{0,20}《", query):
        return SourceStructurePlan("unsupported_source_constraint")
    inventory = {}
    for row in corpus.values():
        inventory.setdefault(document_key(row["filename"]), set()).add(row["document_sha256"])
    resolved = []
    for title in titles:
        documents = inventory.get(document_key(title), set())
        if not documents:
            return SourceStructurePlan("unresolved_source")
        if len(documents) != 1:
            return SourceStructurePlan("ambiguous_source")
        resolved.extend(documents)
    documents = tuple(dict.fromkeys(resolved))
    if not requests_toc(query):
        return SourceStructurePlan("resolved", documents)
    if len(documents) > 2:
        return SourceStructurePlan("resolved", documents, structure_status="source_limit")
    selected = []
    for document in documents:
        toc_ids = [
            i
            for i, row in corpus.items()
            if row["document_sha256"] == document and is_toc(row["content"])
        ]
        if len(toc_ids) != 1:
            return SourceStructurePlan(
                "resolved",
                documents,
                structure_status=("structure_missing" if not toc_ids else "ambiguous_structure"),
            )
        if toc_ids[0] not in candidate_ids:
            return SourceStructurePlan(
                "resolved", documents, structure_status="structure_outside_pool"
            )
        selected.extend(toc_ids)
    return SourceStructurePlan("resolved", documents, tuple(selected), "selected")


def scoped_delivery_ids(plan: SourceStructurePlan, corpus: dict, policy: dict) -> list[str]:
    """Replay fixed scores, then reserve explicit structural evidence inside the same budget.

    Structural IDs intentionally bypass the semantic threshold. This is an explicit retrieval
    method, not a claim that the reranker accepted them. Caller must reapply the context limiter.
    """
    if plan.status != "resolved":
        return [hit["chunk_id"] for hit in policy["hits"]]
    ranked = policy["reranked_ids"]
    if any(i not in ranked for i in plan.structural_ids):
        raise ValueError("structure_outside_ranked_pool")
    retained = [
        i
        for i in ranked
        if corpus[i]["document_sha256"] in plan.document_sha256 and policy["rerank_scores"][i] >= 1
    ][:8]
    return list(dict.fromkeys([*plan.structural_ids, *retained]))[:8]
