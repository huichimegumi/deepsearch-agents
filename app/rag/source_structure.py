"""Opt-in exact document resolution and conservative indexed TOC selection.

Pure planning only: no model, database access, label lookup or production routing.
"""

import re
import unicodedata
from dataclasses import dataclass, replace


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
    resolution_methods: tuple[str, ...] = ()


def indexed_page_suffix_key(filename: str, indexed_page_end: int | None) -> str | None:
    """An attested indexed last page, not a claim about the original PDF page total."""
    if type(indexed_page_end) is not int or indexed_page_end < 1:
        return None
    match = re.fullmatch(r"(.+?)([1-9]\d{0,3})页", document_key(filename))
    if not match or match.group(1).endswith(("第", "页")):
        return None
    prefix, pages = match.groups()
    if prefix[-1].isdigit() or int(pages) != indexed_page_end:
        return None
    return prefix


def document_inventory(corpus: dict) -> list[dict]:
    """Caller supplies a complete scoped snapshot or attested metadata, never partial recall."""
    inventory = {}
    for row in corpus.values():
        key = (row["filename"], row["document_sha256"])
        entry = inventory.setdefault(
            key, {"filename": key[0], "document_sha256": key[1], "indexed_page_end": None}
        )
        page = row.get("indexed_page_end") or row.get("page_end")
        if page is not None:
            entry["indexed_page_end"] = max(entry["indexed_page_end"] or 0, page)
    return list(inventory.values())


def requests_toc(query: str) -> bool:
    clauses = re.split(r"[。！？!?；;，,\n]", query)
    cue = r"(?:目录|table\s+of\s+contents)"
    negative = r"(?:不要|不得|无需|不需要|不必|不用|不想|不是|不列|不生成|请勿|勿列|勿生成|勿给出|勿提供|勿展示|勿输出|(?<![\u4e00-\u9fff])(?:请|先|暂时|这次|本次)*别|do\s+not\b|don't\b|without\b|no\s+)"
    return any(
        re.search(cue, clause, re.I)
        and not re.search(negative + r".{0,32}" + cue, clause, re.I)
        and not re.search(cue + r".{0,8}" + negative, clause, re.I)
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
            number = match.group(1) or match.group(2)
            entries.add(str(int(number)) if number.isdecimal() else number)
    return len(entries) >= 2


def resolve_document_sources(
    query: str, documents, *, allow_page_suffix=False
) -> SourceStructurePlan:
    """Resolve metadata only, before reading document bodies or planning structure."""
    titles = list(dict.fromkeys(re.findall(r"《([^《》\n]+)》", query)))
    if not titles:
        return SourceStructurePlan("no_explicit_source")
    if re.search(r"(?:不要|不得|不使用|不查|无需|排除|不依据|不参考).{0,20}《", query):
        return SourceStructurePlan("unsupported_source_constraint")
    inventory = {}
    exact = {}
    for row in documents:
        key = document_key(row["filename"])
        inventory.setdefault(key, set()).add(row["document_sha256"])
        exact.setdefault(key, set()).add(row["document_sha256"])
        alias = (
            indexed_page_suffix_key(row["filename"], row.get("indexed_page_end"))
            if allow_page_suffix
            else None
        )
        if alias:
            inventory.setdefault(alias, set()).add(row["document_sha256"])
    resolved = []
    methods = []
    for title in titles:
        documents = inventory.get(document_key(title), set())
        if not documents:
            return SourceStructurePlan("unresolved_source")
        if len(documents) != 1:
            return SourceStructurePlan("ambiguous_source")
        resolved.extend(documents)
        methods.append("exact_filename" if document_key(title) in exact else "indexed_page_suffix")
    documents = tuple(dict.fromkeys(resolved))
    return SourceStructurePlan("resolved", documents, resolution_methods=tuple(methods))


def plan_source_structure(
    query: str,
    corpus: dict,
    candidate_ids: list[str],
    *,
    allow_page_suffix=False,
) -> SourceStructurePlan:
    """All source names must resolve; never guess aliases or pull chunks outside the pool."""
    if len(candidate_ids) != len(set(candidate_ids)) or any(i not in corpus for i in candidate_ids):
        raise ValueError("invalid_candidate_membership")
    resolution = resolve_document_sources(
        query, document_inventory(corpus), allow_page_suffix=allow_page_suffix
    )
    if resolution.status != "resolved":
        return resolution
    documents = resolution.document_sha256
    if not requests_toc(query):
        return resolution
    if len(documents) > 2:
        return replace(resolution, structure_status="source_limit")
    selected = []
    for document in documents:
        toc_ids = [
            i
            for i, row in corpus.items()
            if row["document_sha256"] == document and is_toc(row["content"])
        ]
        if len(toc_ids) != 1:
            return replace(
                resolution,
                structure_status=("structure_missing" if not toc_ids else "ambiguous_structure"),
            )
        if toc_ids[0] not in candidate_ids:
            return replace(resolution, structure_status="structure_outside_pool")
        selected.extend(toc_ids)
    return replace(resolution, structural_ids=tuple(selected), structure_status="selected")


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
