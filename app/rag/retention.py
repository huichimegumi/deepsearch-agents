"""Deterministic candidate-retention prototype; production search does not enable it."""

from collections.abc import Sequence


def retain_vector_head(
    vector_ids: Sequence[str], reranked_ids: Sequence[str], *, budget: int = 6, protected: int = 3
) -> list[str]:
    """Protect a bounded vector head, then fill with threshold-qualified reranked IDs.

    Protected candidates bypass the reranker threshold. This is not a relevance guarantee.
    An empty reranked tail does not admit more than the protected head.
    """
    if budget < 1 or not 0 <= protected <= budget:
        raise ValueError("invalid_retention_budget")
    vector = list(dict.fromkeys(vector_ids))
    return list(dict.fromkeys(vector[:protected] + list(reranked_ids)))[:budget]


def order_retained_by_rerank(retained_ids: Sequence[str], rerank_order: Sequence[str]) -> list[str]:
    """Reorder already-budgeted members without changing membership or source text."""
    ranks = {value: rank for rank, value in enumerate(rerank_order)}
    if len(set(retained_ids)) != len(retained_ids) or any(
        value not in ranks for value in retained_ids
    ):
        raise ValueError("unbound_retained_members")
    return sorted(retained_ids, key=ranks.__getitem__)
