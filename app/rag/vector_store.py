"""Qdrant adapter for persistent chunk vectors."""

from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from app.rag.config import get_rag_settings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings = get_rag_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection(vector_size: int) -> None:
    settings = get_rag_settings()
    client = get_qdrant_client()
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
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
