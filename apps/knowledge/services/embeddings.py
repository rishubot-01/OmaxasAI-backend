"""Embedding generation and storage for OmaxasAI Knowledge."""

import logging
import math
import os
import re
from collections.abc import Sequence
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_BATCH_SIZE = 32

MAX_BATCH_SIZE = 128
MAX_TEXTS_PER_REQUEST = 1000
MAX_TEXT_CHARACTERS = 50_000


class EmbeddingServiceError(Exception):
    """Base exception for embedding service failures."""


class EmbeddingConfigurationError(EmbeddingServiceError):
    """Raised when embedding configuration or credentials are missing."""


def _get_embedding_config() -> tuple[str, str | None, str | None]:
    """
    Read embedding configuration from environment variables.

    Supported settings:
        OMAXASAI_EMBEDDING_MODEL
        OMAXASAI_EMBEDDING_API_KEY_ENV
        OMAXASAI_EMBEDDING_API_BASE

    API keys are read from the environment variable whose name is configured.
    Actual API keys must never be stored in the database.
    """

    model = os.getenv(
        "OMAXASAI_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    ).strip()

    if not model:
        raise EmbeddingConfigurationError(
            "OMAXASAI_EMBEDDING_MODEL cannot be empty."
        )

    key_env_name = os.getenv(
        "OMAXASAI_EMBEDDING_API_KEY_ENV",
        "OPENAI_API_KEY",
    ).strip()

    api_base = (
        os.getenv("OMAXASAI_EMBEDDING_API_BASE", "").strip() or None
    )

    if key_env_name and not re.fullmatch(
        r"[A-Z_][A-Z0-9_]*",
        key_env_name,
    ):
        raise EmbeddingConfigurationError(
            "The embedding API key environment variable name is invalid."
        )

    api_key = os.getenv(key_env_name) if key_env_name else None

    # A custom endpoint may be configured for a self-hosted model that
    # does not require an API key. Remote endpoint security is the operator's
    # responsibility; never take this URL directly from an API request.
    if not api_key and not api_base:
        raise EmbeddingConfigurationError(
            f"Set {key_env_name or 'the embedding API key'} "
            "or configure OMAXASAI_EMBEDDING_API_BASE."
        )

    return model, api_key, api_base


def _validate_texts(texts: Sequence[str]) -> list[str]:
    """Validate and normalize the texts sent to the embedding provider."""

    if isinstance(texts, (str, bytes)):
        raise EmbeddingServiceError(
            "Pass a list of texts, not a single string."
        )

    if not isinstance(texts, Sequence):
        raise EmbeddingServiceError(
            "Texts must be supplied as a sequence."
        )

    if not texts:
        raise EmbeddingServiceError(
            "At least one text is required."
        )

    if len(texts) > MAX_TEXTS_PER_REQUEST:
        raise EmbeddingServiceError(
            f"A request cannot exceed {MAX_TEXTS_PER_REQUEST} texts."
        )

    validated: list[str] = []

    for index, text in enumerate(texts):
        if not isinstance(text, str):
            raise EmbeddingServiceError(
                f"Text at position {index} must be a string."
            )

        text = text.strip()

        if not text:
            raise EmbeddingServiceError(
                f"Text at position {index} cannot be empty."
            )

        if len(text) > MAX_TEXT_CHARACTERS:
            raise EmbeddingServiceError(
                f"Text at position {index} exceeds the character limit."
            )

        validated.append(text)

    return validated


def _extract_vectors(response: Any, expected_count: int) -> list[list[float]]:
    """Extract and validate vectors from a LiteLLM embedding response."""

    data = (
        response.get("data")
        if isinstance(response, dict)
        else getattr(response, "data", None)
    )

    if not isinstance(data, (list, tuple)):
        raise EmbeddingServiceError(
            "The embedding provider returned an invalid response."
        )

    if len(data) != expected_count:
        raise EmbeddingServiceError(
            "The embedding provider returned an unexpected number of vectors."
        )

    # Preserve input order when the provider supplies embedding indexes.
    if all(
        isinstance(item, dict) and isinstance(item.get("index"), int)
        for item in data
    ):
        data = sorted(data, key=lambda item: item["index"])

    vectors: list[list[float]] = []

    for index, item in enumerate(data):
        raw_vector = (
            item.get("embedding")
            if isinstance(item, dict)
            else getattr(item, "embedding", None)
        )

        if not isinstance(raw_vector, (list, tuple)) or not raw_vector:
            raise EmbeddingServiceError(
                f"Embedding vector {index} is missing or invalid."
            )

        vector: list[float] = []

        for value in raw_vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingServiceError(
                    f"Embedding vector {index} contains a non-numeric value."
                )

            number = float(value)

            if not math.isfinite(number):
                raise EmbeddingServiceError(
                    f"Embedding vector {index} contains an invalid number."
                )

            vector.append(number)

        vectors.append(vector)

    dimensions = {len(vector) for vector in vectors}

    if len(dimensions) != 1:
        raise EmbeddingServiceError(
            "The embedding provider returned inconsistent vector dimensions."
        )

    return vectors


def embed_texts(
    texts: Sequence[str],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> list[list[float]]:
    """
    Generate an embedding vector for every text.

    The vectors are returned in the same order as the input texts.
    They are not automatically stored in the database by this function.
    """

    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise EmbeddingServiceError("batch_size must be an integer.")

    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise EmbeddingServiceError(
            f"batch_size must be between 1 and {MAX_BATCH_SIZE}."
        )

    validated_texts = _validate_texts(texts)
    model, api_key, api_base = _get_embedding_config()

    try:
        from litellm import embedding
    except ImportError as exc:
        raise EmbeddingConfigurationError(
            "LiteLLM is not installed. Install it using "
            "'python -m pip install litellm'."
        ) from exc

    all_vectors: list[list[float]] = []

    for start in range(0, len(validated_texts), batch_size):
        batch = validated_texts[start : start + batch_size]

        options: dict[str, Any] = {
            "model": model,
            "input": batch,
        }

        if api_key:
            options["api_key"] = api_key

        if api_base:
            options["api_base"] = api_base

        try:
            response = embedding(**options)
            vectors = _extract_vectors(response, len(batch))
        except EmbeddingServiceError:
            raise
        except Exception as exc:
            # Avoid placing raw provider responses or credentials in errors.
            logger.warning(
                "Embedding provider request failed. Model: %s; Error type: %s",
                model,
                type(exc).__name__,
            )
            raise EmbeddingServiceError(
                "Could not generate embeddings. Check provider settings, "
                "model support, network access, and API quota."
            ) from None

        all_vectors.extend(vectors)

    return all_vectors


def embed_text(text: str) -> list[float]:
    """Generate a single text embedding."""

    return embed_texts([text])[0]


def embed_document_chunks(
    document,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """
    Generate and save embeddings for an existing document's chunks.

    Returns the number of chunks updated. Existing embeddings are replaced.
    The document must already have DocumentChunk records.
    """

    from apps.knowledge.models import DocumentChunk, KnowledgeDocument

    if not isinstance(document, KnowledgeDocument):
        raise EmbeddingServiceError(
            "A valid KnowledgeDocument instance is required."
        )

    chunks = list(
        DocumentChunk.objects.filter(document=document).order_by("chunk_index")
    )

    if not chunks:
        raise EmbeddingServiceError(
            "This document has no chunks to embed."
        )

    model, _, _ = _get_embedding_config()

    vectors = embed_texts(
        [chunk.content for chunk in chunks],
        batch_size=batch_size,
    )

    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
        chunk.embedding_model = model

    DocumentChunk.objects.bulk_update(
        chunks,
        fields=["embedding", "embedding_model"],
        batch_size=batch_size,
    )

    logger.info(
        "Generated embeddings for knowledge document %s (%s chunks).",
        document.pk,
        len(chunks),
    )

    return len(chunks)
