
"""Semantic retrieval for OmaxasAI Knowledge documents."""

import logging
import math
import os
from typing import Any

from apps.knowledge.models import DocumentChunk, KnowledgeDocument
from apps.knowledge.services.embeddings import (
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingServiceError,
    embed_text,
)

logger = logging.getLogger(__name__)

MAX_QUERY_CHARACTERS = 10_000
DEFAULT_TOP_K = 5
MAX_TOP_K = 50


class KnowledgeRetrievalError(Exception):
    """Base error for knowledge retrieval."""


class KnowledgeRetrievalConfigurationError(KnowledgeRetrievalError):
    """Raised when embedding configuration is unavailable."""


def _validate_query(query: str) -> str:
    """Validate a semantic search query."""

    if not isinstance(query, str):
        raise KnowledgeRetrievalError("Search query must be text.")

    query = query.strip()

    if not query:
        raise KnowledgeRetrievalError("Search query cannot be empty.")

    if len(query) > MAX_QUERY_CHARACTERS:
        raise KnowledgeRetrievalError(
            f"Search query cannot exceed {MAX_QUERY_CHARACTERS} characters."
        )

    return query


def _validate_top_k(top_k: int) -> int:
    """Validate the requested number of results."""

    if isinstance(top_k, bool) or not isinstance(top_k, int):
        raise KnowledgeRetrievalError("top_k must be an integer.")

    if not 1 <= top_k <= MAX_TOP_K:
        raise KnowledgeRetrievalError(
            f"top_k must be between 1 and {MAX_TOP_K}."
        )

    return top_k


def _validate_min_score(min_score: float | None) -> float | None:
    """Validate the optional cosine-similarity threshold."""

    if min_score is None:
        return None

    if isinstance(min_score, bool) or not isinstance(
        min_score, (int, float)
    ):
        raise KnowledgeRetrievalError(
            "min_score must be a number or None."
        )

    min_score = float(min_score)

    if not math.isfinite(min_score) or not -1.0 <= min_score <= 1.0:
        raise KnowledgeRetrievalError(
            "min_score must be between -1.0 and 1.0."
        )

    return min_score


def _cosine_similarity(
    vector_a: Any,
    vector_b: Any,
) -> float | None:
    """
    Calculate cosine similarity between two numeric vectors.

    Invalid, empty, non-finite, mismatched, or zero-magnitude vectors
    are ignored rather than used for ranking.
    """

    if not isinstance(vector_a, (list, tuple)):
        return None

    if not isinstance(vector_b, (list, tuple)):
        return None

    if not vector_a or len(vector_a) != len(vector_b):
        return None

    values_a = []
    values_b = []

    for value in vector_a:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None

        number = float(value)

        if not math.isfinite(number):
            return None

        values_a.append(number)

    for value in vector_b:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None

        number = float(value)

        if not math.isfinite(number):
            return None

        values_b.append(number)

    dot_product = sum(
        a * b for a, b in zip(values_a, values_b)
    )

    magnitude_a = math.sqrt(sum(value * value for value in values_a))
    magnitude_b = math.sqrt(sum(value * value for value in values_b))

    if magnitude_a == 0 or magnitude_b == 0:
        return None

    return dot_product / (magnitude_a * magnitude_b)


def retrieve_relevant_chunks(
    *,
    user,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """
    Return the most relevant chunks from the current user's documents.

    Only documents whose processing status is READY are searched.
    Query and stored chunk embeddings must use the same embedding model.

    Each result contains:
        document_id, document_title, chunk_id, chunk_index,
        content, score, and metadata.
    """

    if not getattr(user, "is_authenticated", False):
        raise KnowledgeRetrievalError("Authentication is required.")

    query = _validate_query(query)
    top_k = _validate_top_k(top_k)
    min_score = _validate_min_score(min_score)

    model_name = os.getenv(
        "OMAXASAI_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    ).strip()

    if not model_name:
        raise KnowledgeRetrievalConfigurationError(
            "The embedding model is not configured."
        )

    # Enforce ownership in the database query itself.
    chunks = list(
        DocumentChunk.objects.filter(
            document__owner=user,
            document__status=KnowledgeDocument.ProcessingStatus.READY,
            embedding__isnull=False,
            embedding_model=model_name,
        )
        .select_related("document")
        .order_by("document_id", "chunk_index")
    )

    if not chunks:
        return []

    try:
        query_vector = embed_text(query)
    except EmbeddingServiceError as exc:
        logger.warning(
            "Query embedding generation failed; error type: %s",
            type(exc).__name__,
        )
        raise KnowledgeRetrievalConfigurationError(
            "Could not create a search embedding. Check the embedding "
            "provider configuration and API availability."
        ) from None

    results: list[dict[str, Any]] = []

    for chunk in chunks:
        score = _cosine_similarity(query_vector, chunk.embedding)

        if score is None:
            continue

        if min_score is not None and score < min_score:
            continue

        results.append(
            {
                "document_id": chunk.document_id,
                "document_title": chunk.document.title,
                "chunk_id": chunk.pk,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "score": score,
                "metadata": chunk.metadata or {},
            }
        )

    # Highest cosine similarity first; use IDs to keep ties deterministic.
    results.sort(
        key=lambda item: (
            -item["score"],
            item["document_id"],
            item["chunk_index"],
        )
    )

    return results[:top_k]


def search_knowledge(
    *,
    user,
    query: str,
    top_k: int = DEFAULT_TOP_K,
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """Convenience wrapper for semantic knowledge search."""

    return retrieve_relevant_chunks(
        user=user,
        query=query,
        top_k=top_k,
        min_score=min_score,
    )

