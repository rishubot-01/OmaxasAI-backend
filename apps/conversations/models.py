
from django.conf import settings
from django.db import models


class Conversation(models.Model):
    """
    Represents one chat session belonging to a user.
    Used for New Chat and Recents.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversations",
    )

    title = models.CharField(
        max_length=200,
        default="New chat",
    )

    is_archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(
                fields=["user", "-updated_at"],
                name="conv_user_updated_idx",
            ),
        ]
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"

    def __str__(self):
        return f"{self.title} - {self.user.email}"


class Message(models.Model):
    """
    Stores messages sent by users and responses generated
    by OmaxasAI.
    """

    class RoleChoices(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    class ModeChoices(models.TextChoices):
        AUTO = "auto", "Auto"
        THINK = "think", "Think"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=10,
        choices=RoleChoices.choices,
    )

    content = models.TextField()

    # Records which mode was used for this message.
    mode = models.CharField(
        max_length=10,
        choices=ModeChoices.choices,
        default=ModeChoices.AUTO,
    )

    # Optional metadata about the model that generated a response.
    provider = models.CharField(
        max_length=50,
        blank=True,
    )

    model_name = models.CharField(
        max_length=255,
        blank=True,
    )

    web_search_used = models.BooleanField(default=False)

    # Store non-secret message metadata only.
    metadata = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["conversation", "created_at"],
                name="conv_msg_date_idx",
            ),
        ]
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"{self.role} message #{self.pk}"


class FileAttachment(models.Model):
    """
    Stores metadata for files attached to chat messages.

    Actual file contents will be stored using a storage service,
    not directly inside PostgreSQL.
    """

    class FileTypeChoices(models.TextChoices):
        IMAGE = "image", "Image"
        DOCUMENT = "document", "Document"
        AUDIO = "audio", "Audio"
        VIDEO = "video", "Video"
        OTHER = "other", "Other"

    class StatusChoices(models.TextChoices):
        PENDING = "pending", "Pending"
        UPLOADED = "uploaded", "Uploaded"
        PROCESSING = "processing", "Processing"
        READY = "ready", "Ready"
        FAILED = "failed", "Failed"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="attachments",
    )

    message = models.ForeignKey(
        Message,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attachments",
    )

    original_filename = models.CharField(max_length=255)

    file_type = models.CharField(
        max_length=12,
        choices=FileTypeChoices.choices,
        default=FileTypeChoices.OTHER,
    )

    mime_type = models.CharField(
        max_length=150,
        blank=True,
    )

    size_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    # Object key/path in private cloud storage.
    # Do not put API secrets or permanent public links here.
    storage_key = models.CharField(
        max_length=1024,
        blank=True,
    )

    storage_provider = models.CharField(
        max_length=50,
        blank=True,
    )

    status = models.CharField(
        max_length=12,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["conversation", "created_at"],
                name="conv_file_date_idx",
            ),
        ]
        verbose_name = "File Attachment"
        verbose_name_plural = "File Attachments"

    def __str__(self):
        return self.original_filename


class Feedback(models.Model):
    """
    Stores user feedback about an assistant message.
    Each user can submit one feedback record per message.
    """

    class RatingChoices(models.TextChoices):
        HELPFUL = "helpful", "Helpful"
        UNHELPFUL = "unhelpful", "Unhelpful"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="message_feedback",
    )

    message = models.ForeignKey(
        Message,
        on_delete=models.CASCADE,
        related_name="feedback",
    )

    rating = models.CharField(
        max_length=10,
        choices=RatingChoices.choices,
    )

    comment = models.TextField(blank=True, max_length=2000)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "message"],
                name="conv_feedback_unique",
            ),
        ]
        indexes = [
            models.Index(
                fields=["message", "rating"],
                name="conv_feedback_rating_idx",
            ),
        ]
        verbose_name = "Feedback"
        verbose_name_plural = "Feedback"

    def __str__(self):
        return f"{self.rating} feedback for message #{self.message_id}"

