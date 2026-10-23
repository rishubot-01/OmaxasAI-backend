"""Serializers for OmaxasAI Knowledge documents."""

import os

from rest_framework import serializers

from .models import DocumentChunk, KnowledgeDocument


MAX_DOCUMENT_SIZE = 20 * 1024 * 1024  # 20 MB
MAX_SOURCE_TEXT_LENGTH = 500_000

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".md",
    ".csv",
    ".docx",
}

ALLOWED_MIME_TYPES = {
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {
        "text/markdown",
        "text/plain",
        "application/octet-stream",
    },
    ".csv": {
        "text/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
    },
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
}


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    """Validate document input and expose safe document metadata."""

    file = serializers.FileField(
        required=False,
        write_only=True,
    )

    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = KnowledgeDocument
        fields = [
            "id",
            "owner",
            "title",
            "description",
            "source_type",
            "file",
            "original_filename",
            "mime_type",
            "size_bytes",
            "source_url",
            "source_text",
            "content_sha256",
            "status",
            "error_message",
            "chunk_count",
            "metadata",
            "processed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "original_filename",
            "mime_type",
            "size_bytes",
            "content_sha256",
            "status",
            "error_message",
            "chunk_count",
            "metadata",
            "processed_at",
            "created_at",
            "updated_at",
        ]

    def validate_title(self, value):
        """Require a non-empty document title."""

        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Document title cannot be empty."
            )

        return value

    def validate_source_text(self, value):
        """Limit manually submitted text."""

        if len(value) > MAX_SOURCE_TEXT_LENGTH:
            raise serializers.ValidationError(
                "Source text cannot exceed 500,000 characters."
            )

        return value

    def validate_file(self, uploaded_file):
        """Check the file's size, extension, and reported MIME type."""

        if uploaded_file.size <= 0:
            raise serializers.ValidationError(
                "Empty files are not supported."
            )

        if uploaded_file.size > MAX_DOCUMENT_SIZE:
            raise serializers.ValidationError(
                "File size cannot exceed 20 MB."
            )

        filename = os.path.basename(uploaded_file.name or "")
        extension = os.path.splitext(filename)[1].lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                "Unsupported file type. Allowed types: PDF, TXT, MD, CSV, DOCX."
            )

        reported_mime = getattr(uploaded_file, "content_type", None)

        if (
            reported_mime
            and reported_mime.lower() not in ALLOWED_MIME_TYPES[extension]
        ):
            raise serializers.ValidationError(
                "The file's reported content type does not match its extension."
            )

        return uploaded_file

    def validate(self, attrs):
        """Validate fields together according to the selected source type."""

        instance = self.instance

        source_type = attrs.get(
            "source_type",
            instance.source_type if instance else KnowledgeDocument.SourceType.UPLOAD,
        )

        uploaded_file = attrs.get("file")
        existing_file = getattr(instance, "file", None) if instance else None

        source_url = attrs.get(
            "source_url",
            instance.source_url if instance else "",
        )

        source_text = attrs.get(
            "source_text",
            instance.source_text if instance else "",
        )

        # File is required when creating an upload-based document.
        if source_type == KnowledgeDocument.SourceType.UPLOAD:
            has_file = bool(uploaded_file) or bool(existing_file)

            if not has_file:
                raise serializers.ValidationError({
                    "file": "Upload a file for this source type."
                })

            if source_url or source_text:
                raise serializers.ValidationError({
                    "source_url": (
                        "URL and text sources must not be supplied "
                        "for an upload-based document."
                    )
                })

        elif source_type == KnowledgeDocument.SourceType.URL:
            if uploaded_file:
                raise serializers.ValidationError({
                    "file": "Do not upload a file for a URL-based document."
                })

            if not source_url.strip():
                raise serializers.ValidationError({
                    "source_url": "Enter a URL for this document."
                })

            if source_text.strip():
                raise serializers.ValidationError({
                    "source_text": "Text content is not used for URL sources."
                })

        elif source_type == KnowledgeDocument.SourceType.TEXT:
            if uploaded_file:
                raise serializers.ValidationError({
                    "file": "Do not upload a file for a text-based document."
                })

            if not source_text.strip():
                raise serializers.ValidationError({
                    "source_text": "Enter text for this document."
                })

            if source_url.strip():
                raise serializers.ValidationError({
                    "source_url": "URL is not used for text-based documents."
                })

        return attrs

    def create(self, validated_data):
        """Populate basic metadata for newly uploaded files."""

        uploaded_file = validated_data.get("file")

        if uploaded_file:
            validated_data["original_filename"] = os.path.basename(
                uploaded_file.name
            )
            validated_data["mime_type"] = (
                getattr(uploaded_file, "content_type", "") or ""
            )[:150]
            validated_data["size_bytes"] = uploaded_file.size

        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Update document details and metadata for a replacement file."""

        uploaded_file = validated_data.get("file")

        if uploaded_file:
            validated_data["original_filename"] = os.path.basename(
                uploaded_file.name
            )
            validated_data["mime_type"] = (
                getattr(uploaded_file, "content_type", "") or ""
            )[:150]
            validated_data["size_bytes"] = uploaded_file.size

        return super().update(instance, validated_data)


class DocumentChunkSerializer(serializers.ModelSerializer):
    """Read-only representation of a document chunk."""

    class Meta:
        model = DocumentChunk
        fields = [
            "id",
            "document",
            "chunk_index",
            "content",
            "token_count",
            "embedding_model",
            "metadata",
            "created_at",
        ]
        read_only_fields = fields
