
"""Django admin configuration for OmaxasAI Knowledge."""

from django.contrib import admin

from .models import DocumentChunk, KnowledgeDocument


class DocumentChunkInline(admin.TabularInline):
    """Display a document's chunks on its admin detail page."""

    model = DocumentChunk
    extra = 0
    show_change_link = True
    fields = (
        "chunk_index",
        "content",
        "token_count",
        "embedding_model",
        "created_at",
    )
    readonly_fields = ("created_at",)
    ordering = ("chunk_index",)
    max_num = 0


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    """Admin interface for uploaded and text-based knowledge documents."""

    list_display = (
        "id",
        "title",
        "owner",
        "source_type",
        "status",
        "chunk_count",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "source_type",
        "status",
        "created_at",
    )

    search_fields = (
        "title",
        "description",
        "owner__email",
        "original_filename",
        "source_url",
    )

    readonly_fields = (
        "content_sha256",
        "status",
        "error_message",
        "chunk_count",
        "processed_at",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"
    list_select_related = ("owner",)
    list_per_page = 25
    ordering = ("-updated_at", "-id")
    inlines = (DocumentChunkInline,)

    fieldsets = (
        (
            "Document information",
            {
                "fields": (
                    "owner",
                    "title",
                    "description",
                    "source_type",
                )
            },
        ),
        (
            "Source",
            {
                "fields": (
                    "file",
                    "original_filename",
                    "mime_type",
                    "size_bytes",
                    "source_url",
                    "source_text",
                )
            },
        ),
        (
            "Processing",
            {
                "fields": (
                    "status",
                    "error_message",
                    "chunk_count",
                    "content_sha256",
                    "processed_at",
                )
            },
        ),
        (
            "Metadata and timestamps",
            {
                "fields": (
                    "metadata",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    """Admin interface for individual extracted text chunks."""

    list_display = (
        "id",
        "document",
        "chunk_index",
        "token_count",
        "embedding_model",
        "created_at",
    )

    search_fields = (
        "document__title",
        "document__owner__email",
        "content",
        "embedding_model",
    )

    list_filter = (
        "embedding_model",
        "created_at",
    )

    readonly_fields = ("created_at",)
    list_select_related = ("document", "document__owner")
    list_per_page = 25
    ordering = ("document_id", "chunk_index")

