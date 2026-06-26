"""Qdrant adapter for persistent chunk vectors."""

from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from app.rag.config import get_rag_settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings = get_rag_settings()
    return QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
        timeout=settings.qdrant_timeout_seconds,
    )


def ensure_collection(vector_size: int) -> None:
    ensure_named_collection(get_rag_settings().qdrant_collection, vector_size)


def ensure_named_collection(collection_name: str, vector_size: int) -> None:
    client = get_qdrant_client()
    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
        )


def upsert_chunks(points: list[tuple[str, list[float], dict[str, Any]]]) -> None:
    if not points:
        return
    ensure_collection(len(points[0][1]))
    settings = get_rag_settings()
    get_qdrant_client().upsert(
        collection_name=settings.qdrant_collection,
        points=[
            models.PointStruct(id=point_id, vector=vector, payload=payload)
            for point_id, vector, payload in points
        ],
        wait=True,
    )


def upsert_points(
    collection_name: str,
    points: list[tuple[str, list[float], dict[str, Any]]],
) -> None:
    if not points:
        return
    ensure_named_collection(collection_name, len(points[0][1]))
    get_qdrant_client().upsert(
        collection_name=collection_name,
        points=[
            models.PointStruct(id=point_id, vector=vector, payload=payload)
            for point_id, vector, payload in points
        ],
        wait=True,
    )


def delete_document_vectors(document_id: str) -> None:
    settings = get_rag_settings()
    client = get_qdrant_client()
    if not client.collection_exists(settings.qdrant_collection):
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="document_id", match=models.MatchValue(value=document_id)
                    )
                ]
            )
        ),
        wait=True,
    )


def delete_points(collection_name: str, point_ids: list[str]) -> None:
    if not point_ids:
        return
    client = get_qdrant_client()
    if not client.collection_exists(collection_name):
        return
    client.delete(
        collection_name=collection_name,
        points_selector=models.PointIdsList(points=point_ids),
        wait=True,
    )


def search_vectors(
    vector: list[float], knowledge_base_id: str, limit: int
) -> list[tuple[str, float]]:
    settings = get_rag_settings()
    client = get_qdrant_client()
    if not client.collection_exists(settings.qdrant_collection):
        return []
    response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="knowledge_base_id",
                    match=models.MatchValue(value=knowledge_base_id),
                )
            ]
        ),
        limit=limit,
        with_payload=False,
    )
    return [(str(point.id), float(point.score)) for point in response.points]


def search_payload_vectors(
    collection_name: str,
    vector: list[float],
    filters: dict[str, Any],
    limit: int,
) -> list[tuple[str, float]]:
    client = get_qdrant_client()
    if not client.collection_exists(collection_name):
        return []
    response = client.query_points(
        collection_name=collection_name,
        query=vector,
        query_filter=models.Filter(
            must=[
                models.FieldCondition(key=key, match=models.MatchValue(value=value))
                for key, value in filters.items()
            ]
        ),
        limit=limit,
        with_payload=False,
    )
    return [(str(point.id), float(point.score)) for point in response.points]
