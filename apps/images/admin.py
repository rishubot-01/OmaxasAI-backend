
"""Django admin configuration for OmaxasAI Images."""

from django.contrib import admin

from .models import GeneratedImage, ImageGenerationRequest


class GeneratedImageInline(admin.TabularInline):
    """Show generated images inside their generation request."""

    model = GeneratedImage
    extra = 0
    fields = (
        "image_index",
        "image_file",
        "image_url",
        "storage_provider",
        "mime_type",
        "file_size_bytes",
        "width",
        "height",
        "is_public",
        "created_at",
    )
    readonly_fields = fields
    ordering = ("image_index", "id")
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        """Images should be created through the image service."""
        return False


@admin.register(ImageGenerationRequest)
class ImageGenerationRequestAdmin(admin.ModelAdmin):
    """Admin interface for image-generation requests."""

    list_display = (
        "id",
        "request_id",
        "user",
        "short_prompt",
        "style",
        "resolution",
        "requested_count",
        "generated_count",
        "status",
        "provider",
        "created_at",
    )

    list_filter = (
        "status",
        "style",
        "aspect_ratio",
        "resolution",
        "output_format",
        "provider",
        "created_at",
    )

    search_fields = (
        "request_id",
        "user__email",
        "prompt",
        "provider",
        "model_name",
        "error_code",
    )

    readonly_fields = (
        "request_id",
        "generated_count",
        "provider",
        "model_name",
        "status",
        "generation_parameters",
        "error_code",
        "error_message",
        "started_at",
        "completed_at",
        "duration_ms",
        "created_at",
        "updated_at",
    )

    date_hierarchy = "created_at"
    list_select_related = ("user",)
    list_per_page = 25
    ordering = ("-created_at", "-id")
    inlines = (GeneratedImageInline,)

    fieldsets = (
        (
            "Request",
            {
                "fields": (
                    "request_id",
                    "user",
                    "prompt",
                    "negative_prompt",
                    "style",
                )
            },
        ),
        (
            "Output settings",
            {
                "fields": (
                    "aspect_ratio",
                    "resolution",
                    "output_format",
                    "requested_count",
                    "generated_count",
                    "seed",
                )
            },
        ),
        (
            "Provider and status",
            {
                "fields": (
                    "provider",
                    "model_name",
                    "status",
                    "generation_parameters",
                )
            },
        ),
        (
            "Processing details",
            {
                "fields": (
                    "error_code",
                    "error_message",
                    "started_at",
                    "completed_at",
                    "duration_ms",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Prompt")
    def short_prompt(self, obj):
        """Show a shortened prompt in the list view."""
        prompt = obj.prompt or ""
        if len(prompt) > 60:
            return f"{prompt[:57]}..."
        return prompt


@admin.register(GeneratedImage)
class GeneratedImageAdmin(admin.ModelAdmin):
    """Read-only admin view of generated image records."""

    list_display = (
        "id",
        "generation",
        "image_index",
        "storage_provider",
        "mime_type",
        "file_size_bytes",
        "width",
        "height",
        "is_public",
        "created_at",
    )

    list_filter = (
        "storage_provider",
        "mime_type",
        "is_public",
        "created_at",
    )

    search_fields = (
        "generation__request_id",
        "generation__user__email",
        "generation__prompt",
        "content_sha256",
    )

    readonly_fields = tuple(
        field.name for field in GeneratedImage._meta.fields
    )

    list_select_related = ("generation", "generation__user")
    list_per_page = 25
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        """Images should be created through the image service."""
        return False

    def has_change_permission(self, request, obj=None):
        """Prevent manual edits to generated image records."""
        return request.method in ("GET", "HEAD", "OPTIONS") and super().has_change_permission(
            request, obj
        )

    def has_delete_permission(self, request, obj=None):
        """Prevent accidental deletion from the image list."""
        return False

