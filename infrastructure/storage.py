
"""Shared file-storage utilities for the OmaxasAI backend."""

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from django.core.files.base import ContentFile
from django.core.files.storage import Storage, default_storage
from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB
DEFAULT_CHUNK_SIZE = 1024 * 1024  # 1 MB


class StorageOperationError(Exception):
    """Raised when a file-storage operation fails."""


class UploadValidationError(StorageOperationError):
    """Raised when an uploaded file fails validation."""


@dataclass(frozen=True)
class StoredFile:
    """Metadata returned after successfully storing a file."""

    name: str
    size_bytes: int
    sha256: str
    content_type: str | None = None


def sanitize_filename(filename: str | None) -> str:
    """
    Return a safe filename without directory components.

    The original filename should be stored separately if it is needed
    for display or download purposes.
    """

    raw_name = str(filename or "upload.bin")
    raw_name = raw_name.replace("\\", "/").split("/")[-1]

    # Remove control characters and characters unsuitable for a storage key.
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name)
    safe_name = safe_name.strip("._")

    if not safe_name:
        safe_name = "upload.bin"

    # Avoid excessively long storage filenames.
    if len(safe_name) > 120:
        suffix = Path(safe_name).suffix[:15]
        stem = safe_name[: 120 - len(suffix)].rstrip("._")
        safe_name = f"{stem or 'upload'}{suffix}"

    return safe_name


def sanitize_storage_prefix(prefix: str) -> str:
    """
    Normalize a storage prefix and reject traversal components.

    Example:
        knowledge/documents
    """

    if not isinstance(prefix, str) or not prefix.strip():
        raise ValueError("Storage prefix must be a non-empty string.")

    normalized = prefix.replace("\\", "/")
    parts = normalized.split("/")

    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("Storage prefix contains an invalid path component.")

    safe_parts = []

    for part in parts:
        safe_part = re.sub(r"[^A-Za-z0-9_-]+", "_", part).strip("_")

        if not safe_part:
            raise ValueError("Storage prefix contains an invalid component.")

        safe_parts.append(safe_part)

    return "/".join(safe_parts)


def build_storage_name(
    *,
    prefix: str,
    filename: str,
) -> str:
    """Create a unique, server-generated storage key."""

    safe_prefix = sanitize_storage_prefix(prefix)
    safe_filename = sanitize_filename(filename)
    now = timezone.now()

    return (
        f"{safe_prefix}/{now:%Y/%m}/"
        f"{uuid4().hex}_{safe_filename}"
    )


def _validate_max_size(max_size: int) -> None:
    """Validate a maximum file size argument."""

    if (
        isinstance(max_size, bool)
        or not isinstance(max_size, int)
        or max_size <= 0
    ):
        raise ValueError("max_size must be a positive integer.")


def _iter_file_chunks(uploaded_file):
    """Yield bounded-size file chunks."""

    chunks_method = getattr(uploaded_file, "chunks", None)

    if callable(chunks_method):
        yield from chunks_method(DEFAULT_CHUNK_SIZE)
        return

    read_method = getattr(uploaded_file, "read", None)

    if not callable(read_method):
        raise UploadValidationError(
            "The uploaded object cannot be read."
        )

    while True:
        chunk = read_method(DEFAULT_CHUNK_SIZE)

        if not chunk:
            break

        yield chunk


def inspect_uploaded_file(
    uploaded_file,
    *,
    allowed_extensions: set[str] | None = None,
    max_size: int = DEFAULT_MAX_UPLOAD_SIZE,
) -> StoredFile:
    """
    Check file size and extension, then calculate SHA-256.

    This function restores the file pointer to the beginning when seeking
    is supported. A filename extension and a MIME type alone do not prove
    that a file's contents are safe.
    """

    _validate_max_size(max_size)

    filename = getattr(uploaded_file, "name", None)
    safe_filename = sanitize_filename(filename)
    extension = Path(safe_filename).suffix.lower()

    if allowed_extensions is not None:
        normalized_extensions = {
            item.lower() if item.startswith(".") else f".{item.lower()}"
            for item in allowed_extensions
        }

        if extension not in normalized_extensions:
            raise UploadValidationError(
                "This file extension is not supported."
            )

    reported_size = getattr(uploaded_file, "size", None)

    if reported_size is not None:
        if (
            isinstance(reported_size, bool)
            or not isinstance(reported_size, int)
            or reported_size < 0
        ):
            raise UploadValidationError(
                "The uploaded file size is invalid."
            )

        if reported_size > max_size:
            raise UploadValidationError(
                "The uploaded file exceeds the permitted size limit."
            )

    try:
        seekable = callable(getattr(uploaded_file, "seek", None))
        if seekable:
            uploaded_file.seek(0)

        digest = hashlib.sha256()
        actual_size = 0

        for chunk in _iter_file_chunks(uploaded_file):
            if not isinstance(chunk, bytes):
                raise UploadValidationError(
                    "The uploaded file must provide binary content."
                )

            actual_size += len(chunk)

            if actual_size > max_size:
                raise UploadValidationError(
                    "The uploaded file exceeds the permitted size limit."
                )

            digest.update(chunk)

        if actual_size == 0:
            raise UploadValidationError(
                "Empty files are not supported."
            )

        if seekable:
            uploaded_file.seek(0)

    except StorageOperationError:
        raise
    except Exception:
        logger.warning(
            "Could not inspect an uploaded file. error during file reading."
        )
        raise UploadValidationError(
            "The uploaded file could not be read."
        ) from None

    return StoredFile(
        name=safe_filename,
        size_bytes=actual_size,
        sha256=digest.hexdigest(),
        content_type=getattr(uploaded_file, "content_type", None),
    )


def save_uploaded_file(
    uploaded_file,
    *,
    prefix: str,
    allowed_extensions: set[str] | None = None,
    max_size: int = DEFAULT_MAX_UPLOAD_SIZE,
    storage: Storage | None = None,
) -> StoredFile:
    """
    Validate and save an uploaded file using Django's configured storage.

    The returned name is the actual storage key, which may differ from the
    requested name if the storage backend resolves a name collision.
    """

    inspected = inspect_uploaded_file(
        uploaded_file,
        allowed_extensions=allowed_extensions,
        max_size=max_size,
    )

    target_storage = storage or default_storage
    storage_name = build_storage_name(
        prefix=prefix,
        filename=inspected.name,
    )

    try:
        if callable(getattr(uploaded_file, "seek", None)):
            uploaded_file.seek(0)

        actual_name = target_storage.save(
            storage_name,
            uploaded_file,
        )

        return StoredFile(
            name=actual_name,
            size_bytes=inspected.size_bytes,
            sha256=inspected.sha256,
            content_type=inspected.content_type,
        )

    except Exception:
        logger.exception(
            "Failed to save an uploaded file. prefix=%s",
            prefix,
        )
        raise StorageOperationError(
            "The uploaded file could not be stored."
        ) from None


def save_bytes(
    content: bytes,
    *,
    prefix: str,
    filename: str,
    max_size: int = DEFAULT_MAX_UPLOAD_SIZE,
    content_type: str | None = None,
    storage: Storage | None = None,
) -> StoredFile:
    """Validate and save in-memory binary content."""

    _validate_max_size(max_size)

    if not isinstance(content, bytes):
        raise UploadValidationError(
            "File content must be provided as bytes."
        )

    if not content:
        raise UploadValidationError("File content cannot be empty.")

    if len(content) > max_size:
        raise UploadValidationError(
            "File content exceeds the permitted size limit."
        )

    safe_filename = sanitize_filename(filename)
    target_storage = storage or default_storage

    storage_name = build_storage_name(
        prefix=prefix,
        filename=safe_filename,
    )

    digest = hashlib.sha256(content).hexdigest()

    try:
        actual_name = target_storage.save(
            storage_name,
            ContentFile(content, name=safe_filename),
        )

        return StoredFile(
            name=actual_name,
            size_bytes=len(content),
            sha256=digest,
            content_type=content_type,
        )

    except Exception:
        logger.exception(
            "Failed to save binary content. prefix=%s",
            prefix,
        )
        raise StorageOperationError(
            "The file content could not be stored."
        ) from None


def storage_file_exists(
    name: str,
    *,
    storage: Storage | None = None,
) -> bool:
    """Check whether a file exists in the configured storage backend."""

    if not isinstance(name, str) or not name.strip():
        return False

    target_storage = storage or default_storage

    try:
        return target_storage.exists(name)
    except Exception:
        logger.warning(
            "Storage existence check failed. error during storage access."
        )
        raise StorageOperationError(
            "The file's storage status could not be checked."
        ) from None


def delete_storage_file(
    name: str,
    *,
    storage: Storage | None = None,
    missing_ok: bool = True,
) -> bool:
    """
    Delete a stored file.

    Returns True when a file was deleted and False when the file was
    already absent and missing_ok is enabled.
    """

    if not isinstance(name, str) or not name.strip():
        if missing_ok:
            return False

        raise StorageOperationError("A valid storage key is required.")

    target_storage = storage or default_storage

    try:
        if not target_storage.exists(name):
            if missing_ok:
                return False

            raise StorageOperationError("The stored file does not exist.")

        target_storage.delete(name)
        return True

    except StorageOperationError:
        raise
    except Exception:
        logger.exception(
            "Failed to delete a stored file. error during storage access."
        )
        raise StorageOperationError(
            "The stored file could not be deleted."
        ) from None

