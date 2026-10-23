
"""Database models for document knowledge and retrieval."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def validate_document_source(document):
    """Validate the source associated with a knowledge document."""

    if document.source_type == KnowledgeDocument.SourceType.UPLOAD:
        if not document.file:
            raise ValidationError({"file": "An uploaded file is required."})

    elif document.source_type == KnowledgeDocument.SourceType.URL:
        if not document.source_url:
            raise ValidationError(
                {"source_url": "A URL is required for URL-based documents."}
            )

    elif document.source_type == KnowledgeDocument.SourceType.TEXT:
        if not document.source_text.strip():
            raise ValidationError(
                {"source_text": "Text content is required for text documents."}
            )


class KnowledgeDocument(models.Model):
    """A document or text source owned by a user."""

    class SourceType(models.TextChoices):
        UPLOAD = "upload", "Uploaded file"
        URL = "url", "Web URL"
        TEXT = "text", "Plain text"

    class ProcessingStatus(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="knowledge_documents",
    )

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.UPLOAD,
    )

    file = models.FileField(
        upload_to="knowledge/documents/%Y/%m/",
        blank=True,
    )
    original_filename = models.CharField(max_length=255, blank=True)
    mime_type = models.CharField(max_length=150, blank=True)
    size_bytes = models.PositiveBigIntegerField(null=True, blank=True)

    source_url = models.URLField(max_length=2048, blank=True)
    source_text = models.TextField(blank=True)

    content_sha256 = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )

    status = models.CharField(
        max_length=12,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.UPLOADED,
        db_index=True,
    )

    error_message = models.TextField(blank=True)
    chunk_count = models.PositiveIntegerField(default=0)

    metadata = models.JSONField(default=dict, blank=True)

    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(
                fields=["owner", "status"],
                name="knowledge_owner_status_idx",
            ),
            models.Index(
                fields=["owner", "-created_at"],
                name="knowledge_owner_created_idx",
            ),
        ]

    def clean(self):
        """Validate the selected document source."""

        super().clean()
        validate_document_source(self)

    def __str__(self):
        return f"{self.title} ({self.status})"


class DocumentChunk(models.Model):
    """A text segment extracted from a knowledge document."""

    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )

    chunk_index = models.PositiveIntegerField()
    content = models.TextField()

    token_count = models.PositiveIntegerField(null=True, blank=True)

    # Store embedding vectors as a list of numbers.
    # A dedicated vector database can be added later if needed.
    embedding = models.JSONField(null=True, blank=True)
    embedding_model = models.CharField(max_length=150, blank=True)

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["chunk_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["document", "chunk_index"],
                name="knowledge_unique_document_chunk",
            ),
        ]

    def __str__(self):
        return f"Document {self.document_id} — chunk {self.chunk_index}"

