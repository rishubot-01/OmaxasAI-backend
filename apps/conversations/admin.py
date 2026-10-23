
"""
Admin configuration for OmaxasAI conversations.
"""

from django.contrib import admin

from .models import Conversation, Feedback, FileAttachment, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    """Manage chat sessions."""

    list_display = (
        "id",
        "title",
        "user",
        "is_archived",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_archived",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "user__email",
        "user__display_name",
    )

    list_editable = ("is_archived",)
    list_select_related = ("user",)
    ordering = ("-updated_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Inspect messages exchanged in conversations."""

    list_display = (
        "id",
        "conversation",
        "role",
        "mode",
        "provider",
        "model_name",
        "web_search_used",
        "created_at",
    )

    list_filter = (
        "role",
        "mode",
        "web_search_used",
        "created_at",
    )

    search_fields = (
        "content",
        "conversation__title",
        "conversation__user__email",
        "provider",
        "model_name",
    )

    list_select_related = (
        "conversation",
        "conversation__user",
    )

    ordering = ("-created_at",)

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    # Do not allow staff to create fake chat messages
    # through the admin panel.
    def has_add_permission(self, request):
        return False


@admin.register(FileAttachment)
class FileAttachmentAdmin(admin.ModelAdmin):
    """Inspect uploaded-file metadata."""

    list_display = (
        "id",
        "original_filename",
        "conversation",
        "file_type",
        "mime_type",
        "size_bytes",
        "status",
        "created_at",
    )

    list_filter = (
        "file_type",
        "status",
        "storage_provider",
        "created_at",
    )

    search_fields = (
        "original_filename",
        "conversation__title",
        "conversation__user__email",
    )

    list_select_related = (
        "conversation",
        "conversation__user",
    )

    ordering = ("-created_at",)

    # Attachment records should be created by the upload service.
    # Storage keys are not exposed in the admin list.
    readonly_fields = tuple(
        field.name for field in FileAttachment._meta.fields
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    """Review feedback submitted on assistant messages."""

    list_display = (
        "id",
        "user",
        "message",
        "rating",
        "created_at",
    )

    list_filter = (
        "rating",
        "created_at",
    )

    search_fields = (
        "user__email",
        "message__content",
        "message__conversation__title",
        "comment",
    )

    list_select_related = (
        "user",
        "message",
        "message__conversation",
    )

    ordering = ("-created_at",)

    readonly_fields = tuple(
        field.name for field in Feedback._meta.fields
    )

    # Feedback is submitted through the application API.
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

