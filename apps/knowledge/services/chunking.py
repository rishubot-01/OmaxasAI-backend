
"""Text chunking utilities for OmaxasAI Knowledge retrieval."""

import re
from typing import Any


DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150

MAX_CHUNK_SIZE = 8000
MAX_CHUNK_OVERLAP = 2000
MAX_INPUT_CHARACTERS = 500_000


class DocumentChunkingError(Exception):
    """Raised when document text cannot be split into chunks."""


def _validate_parameters(
    text: str,
    chunk_size: int,
    overlap: int,
) -> None:
    """Validate the text and chunking configuration."""

    if not isinstance(text, str):
        raise DocumentChunkingError("Document text must be a string.")

    if not text.strip():
        raise DocumentChunkingError("Document text cannot be empty.")

    if len(text) > MAX_INPUT_CHARACTERS:
        raise DocumentChunkingError(
            "Document text cannot exceed 500,000 characters."
        )

    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int):
        raise DocumentChunkingError("chunk_size must be an integer.")

    if not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise DocumentChunkingError(
            f"chunk_size must be between 1 and {MAX_CHUNK_SIZE}."
        )

    if isinstance(overlap, bool) or not isinstance(overlap, int):
        raise DocumentChunkingError("overlap must be an integer.")

    if not 0 <= overlap <= MAX_CHUNK_OVERLAP:
        raise DocumentChunkingError(
            f"overlap must be between 0 and {MAX_CHUNK_OVERLAP}."
        )

    if overlap >= chunk_size:
        raise DocumentChunkingError(
            "overlap must be smaller than chunk_size."
        )


def _normalize_text(text: str) -> str:
    """Normalize line endings and remove unwanted null characters."""

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\x00", "")

    # Remove unnecessary spaces without destroying paragraph boundaries.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def _find_split_point(
    text: str,
    start: int,
    limit: int,
    chunk_size: int,
) -> int:
    """
    Find a natural chunk boundary near the requested size.

    Prefer paragraph and sentence boundaries when they occur close enough
    to the target. Otherwise, split at whitespace or at the hard limit.
    """

    if limit >= len(text):
        return len(text)

    minimum_boundary = start + int(chunk_size * 0.65)

    # Prefer larger semantic boundaries before ordinary spaces.
    separators = (
        "\n\n",
        "\n",
        ". ",
        "? ",
        "! ",
        "; ",
        ", ",
        " ",
    )

    for separator in separators:
        position = text.rfind(
            separator,
            minimum_boundary,
            limit,
        )

        if position >= minimum_boundary:
            split_point = position + len(separator)

            if split_point > start:
                return split_point

    # A long string without whitespace may require a hard split.
    return limit


def _estimate_token_count(text: str) -> int:
    """
    Estimate tokens from character count.

    This is an approximation, not an exact tokenizer count. Actual token
    counts depend on the model and language.
    """

    if not text:
        return 0

    return max(1, (len(text) + 3) // 4)


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[dict[str, Any]]:
    """
    Split document text into overlapping chunks.

    Args:
        text: Extracted document text.
        chunk_size: Maximum target chunk size in characters.
        overlap: Number of characters shared between neighboring chunks.

    Returns:
        A list of dictionaries ready to use when creating DocumentChunk
        records. Each dictionary contains chunk_index, content,
        token_count, and metadata with character offsets.
    """

    _validate_parameters(text, chunk_size, overlap)

    normalized_text = _normalize_text(text)

    if not normalized_text:
        raise DocumentChunkingError(
            "No text remains after normalization."
        )

    if len(normalized_text) > MAX_INPUT_CHARACTERS:
        raise DocumentChunkingError(
            "Normalized text exceeds the maximum input size."
        )

    chunks: list[dict[str, Any]] = []
    start = 0
    text_length = len(normalized_text)

    while start < text_length:
        limit = min(start + chunk_size, text_length)

        end = _find_split_point(
            normalized_text,
            start,
            limit,
            chunk_size,
        )

        content = normalized_text[start:end].strip()

        if content:
            # Find the actual content boundaries after trimming whitespace.
            left_trim = len(normalized_text[start:end]) - len(
                normalized_text[start:end].lstrip()
            )
            right_trimmed_end = end - (
                len(normalized_text[start:end])
                - len(normalized_text[start:end].rstrip())
            )

            actual_start = start + left_trim
            actual_end = max(actual_start, right_trimmed_end)

            chunks.append(
                {
                    "chunk_index": len(chunks),
                    "content": content,
                    "token_count": _estimate_token_count(content),
                    "metadata": {
                        "start_char": actual_start,
                        "end_char": actual_end,
                    },
                }
            )

        if end >= text_length:
            break

        next_start = max(start + 1, end - overlap)

        # Prefer to begin the next chunk at a word boundary.
        whitespace_position = normalized_text.rfind(
            " ",
            next_start,
            end,
        )

        if whitespace_position > start:
            next_start = whitespace_position + 1

        # Defensive guard to guarantee forward progress.
        if next_start <= start or next_start >= end:
            next_start = end

        start = next_start

    if not chunks:
        raise DocumentChunkingError(
            "Unable to create chunks from this document."
        )

    return chunks

