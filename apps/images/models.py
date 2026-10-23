
"""Database models for OmaxasAI image generation and image history."""

import uuid

from django.conf import settings
from django.db import models


class ImageGenerationRequest(models.Model):
    """Track a user's image generation request and its processing status."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    class Style(models.TextChoices):
        AUTO = "auto", "Automatic"
        PHOTOREALISTIC = "photorealistic", "Photorealistic"
        CINEMATIC = "cinematic", "Cinematic"
        ANIME = "anime", "Anime"
        ILLUSTRATION = "illustration", "Illustration"
        THREE_D = "3d", "3D"
        WATERCOLOR = "watercolor", "Watercolor"
        PIXEL_ART = "pixel_art", "Pixel Art"
        CUSTOM = "custom", "Custom"

    class AspectRatio(models.TextChoices):
        SQUARE = "1:1", "Square"
        LANDSCAPE = "3:2", "Landscape"
        PORTRAIT = "2:3", "Portrait"
        WIDE = "16:9", "Wide"
        TALL = "9:16", "Tall"
        CLASSIC = "4:3", "Classic"
        CLASSIC_PORTRAIT = "3:4", "Classic Portrait"

    class Resolution(models.TextChoices):
        SMALL = "512x512", "512 × 512"
        MEDIUM = "1024x1024", "1024 × 1024"
        LANDSCAPE = "1536x1024", "1536 × 1024"
        PORTRAIT = "1024x1536", "1024 × 1536"

    class OutputFormat(models.TextChoices):
        PNG = "png", "PNG"
        JPEG = "jpeg", "JPEG"
        WEBP = "webp", "WebP"

    request_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="image_generation_requests",
    )

    prompt = models.TextField()
    negative_prompt = models.TextField(blank=True)

    style = models.CharField(
        max_length=20,
        choices=Style.choices,
        default=Style.AUTO,
    )

    aspect_ratio = models.CharField(
        max_length=20,
        choices=AspectRatio.choices,
        default=AspectRatio.SQUARE,
    )

    resolution = models.CharField(
        max_length=20,
        choices=Resolution.choices,
        default=Resolution.MEDIUM,
    )

    output_format = models.CharField(
        max_length=10,
        choices=OutputFormat.choices,
        default=OutputFormat.PNG,
    )

    requested_count = models.PositiveSmallIntegerField(default=1)
    generated_count = models.PositiveSmallIntegerField(default=0)

    provider = models.CharField(max_length=100, blank=True)
    model_name = models.CharField(max_length=150, blank=True)

    seed = models.BigIntegerField(null=True, blank=True)

    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )

    # Store non-secret generation settings only.
    generation_parameters = models.JSONField(
        default=dict,
        blank=True,
    )

    # Keep public-safe error identifiers separate from internal logs.
    error_code = models.CharField(max_length=100, blank=True)
    error_message = models.CharField(max_length=500, blank=True)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["user", "status"],
                name="img_user_status_idx",
            ),
            models.Index(
                fields=["user", "-created_at"],
                name="img_user_created_idx",
            ),
        ]

    def __str__(self):
        return f"Image request {self.request_id} ({self.status})"


class GeneratedImage(models.Model):
    """Store generated image files or references to externally stored images."""

    class StorageProvider(models.TextChoices):
        DEFAULT = "default", "Django configured storage"
        CLOUDINARY = "cloudinary", "Cloudinary"
        EXTERNAL = "external", "External URL"

    generation = models.ForeignKey(
        ImageGenerationRequest,
        on_delete=models.CASCADE,
        related_name="images",
    )

    image_index = models.PositiveSmallIntegerField(default=0)

    # The file may be stored using Django's configured storage backend.
    image_file = models.ImageField(
        upload_to="omaxasai/images/%Y/%m/",
        blank=True,
    )

    # Can hold a trusted provider/storage URL when a local file is not used.
    # Prefer a controlled storage URL instead of a temporary provider URL.
    image_url = models.URLField(
        max_length=2048,
        blank=True,
    )

    storage_provider = models.CharField(
        max_length=20,
        choices=StorageProvider.choices,
        default=StorageProvider.DEFAULT,
    )

    mime_type = models.CharField(max_length=100, blank=True)
    file_size_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)

    alt_text = models.CharField(max_length=500, blank=True)

    content_sha256 = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )

    is_public = models.BooleanField(default=False)

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["image_index", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["generation", "image_index"],
                name="img_unique_gen_index",
            ),
        ]
        indexes = [
            models.Index(
                fields=["generation", "created_at"],
                name="img_gen_created_idx",
            ),
        ]

    def __str__(self):
        return (
            f"Generated image {self.pk} "
            f"for request {self.generation_id}"
        )

