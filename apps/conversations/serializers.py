
"""
Serializers for OmaxasAI conversations, messages,
file attachments, and feedback.
"""

from rest_framework import serializers

from .models import (
    Conversation,
    Feedback,
    FileAttachment,
    Message,
)


class ConversationSerializer(serializers.ModelSerializer):
    """Serialize a user's chat sessions."""

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "is_archived",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_title(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Conversation title cannot be empty."
            )

        return value


class MessageSerializer(serializers.ModelSerializer):
    """Read-only representation of a stored conversation message."""

    class Meta:
        model = Message
        fields = (
            "id",
            "conversation",
            "role",
            "content",
            "mode",
            "provider",
            "model_name",
            "web_search_used",
            "metadata",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UserMessageCreateSerializer(serializers.ModelSerializer):
    """
    Validate a new user message.

    The view/service must assign role='user' on the server.
    Clients cannot submit assistant messages through this serializer.
    """

    conversation = serializers.PrimaryKeyRelatedField(
        queryset=Conversation.objects.none(),
    )

    class Meta:
        model = Message
        fields = (
            "conversation",
            "content",
            "mode",
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            fields["conversation"].queryset = Conversation.objects.filter(
                user=request.user
            )

        return fields

    def validate_content(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Message cannot be empty."
            )

        if len(value) > 100000:
            raise serializers.ValidationError(
                "Message is too long."
            )

        return value

    def create(self, validated_data):
        # The message role is always assigned by the backend.
        return Message.objects.create(
            role=Message.RoleChoices.USER,
            **validated_data,
        )


class FileAttachmentSerializer(serializers.ModelSerializer):
    """
    Serialize attachment metadata without exposing storage secrets.

    Actual file uploads and storage authorization are handled
    by the upload service and its API view.
    """

    conversation = serializers.PrimaryKeyRelatedField(
        queryset=Conversation.objects.none(),
    )

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.none(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = FileAttachment
        fields = (
            "id",
            "conversation",
            "message",
            "original_filename",
            "file_type",
            "mime_type",
            "size_bytes",
            "status",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "created_at",
            "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            fields["conversation"].queryset = Conversation.objects.filter(
                user=request.user
            )

            fields["message"].queryset = Message.objects.filter(
                conversation__user=request.user
            )

        return fields

    def validate(self, attrs):
        conversation = attrs.get("conversation")
        message = attrs.get("message")

        if message and conversation and message.conversation_id != conversation.id:
            raise serializers.ValidationError(
                {
                    "message": (
                        "The message must belong to the selected conversation."
                    )
                }
            )

        return attrs

    def validate_original_filename(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "A filename is required."
            )

        if len(value) > 255:
            raise serializers.ValidationError(
                "Filename cannot exceed 255 characters."
            )

        if "/" in value or "\\" in value:
            raise serializers.ValidationError(
                "Provide a filename, not a filesystem path."
            )

        return value


class FeedbackSerializer(serializers.ModelSerializer):
    """Create or read feedback on an assistant message."""

    message = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.none(),
    )

    class Meta:
        model = Feedback
        fields = (
            "id",
            "message",
            "rating",
            "comment",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "created_at",
            "updated_at",
        )

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        if request and request.user.is_authenticated:
            fields["message"].queryset = Message.objects.filter(
                conversation__user=request.user,
                role=Message.RoleChoices.ASSISTANT,
            )

        return fields

    def validate_comment(self, value):
        return value.strip()

    def create(self, validated_data):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required to submit feedback."
            )

        return Feedback.objects.create(
            user=request.user,
            **validated_data,
        )

