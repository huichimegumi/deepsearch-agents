"""RAG inference must not claim a shared GPU in benchmark runs."""

from unittest.mock import patch

from app.rag.embeddings import _get_reranker, get_embedding_model


def test_embedding_and_reranker_explicitly_select_cpu():
    get_embedding_model.cache_clear()
    _get_reranker.cache_clear()
    try:
        with (
            patch("app.rag.embeddings.TextEmbedding") as embedding,
            patch("fastembed.rerank.cross_encoder.TextCrossEncoder") as reranker,
        ):
            get_embedding_model()
            _get_reranker()
        for call in (embedding.call_args, reranker.call_args):
            assert call.kwargs["providers"] == ["CPUExecutionProvider"]
            assert call.kwargs["cuda"] is False
    finally:
        get_embedding_model.cache_clear()
        _get_reranker.cache_clear()
