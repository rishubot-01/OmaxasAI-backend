
"""Serializers for OmaxasAI image generation APIs."""

from rest_framework import serializers

from .models import GeneratedImage, ImageGenerationRequest


MAX_PROMPT_LENGTH = 10_000
MAX_NEGATIVE_PROMPT_LENGTH = 5_000
MAX_IMAGES_PER_REQUEST = 4
MAX_ALT_TEXT_LENGTH = 500


class ImageGenerationRequestSerializer(serializers.ModelSerializer):
    """Validate an image-generation request from an authenticated user."""

    request_id = serializers.UUIDField(read_only=True)

    requested_count = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=MAX_IMAGES_PER_REQUEST,
    )

    prompt = serializers.CharField(
        max_length=MAX_PROMPT_LENGTH,
        trim_whitespace=True,
    )

    negative_prompt = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=MAX_NEGATIVE_PROMPT_LENGTH,
        trim_whitespace=True,
    )

    class Meta:
        model = ImageGenerationRequest
        fields = [
            "id",
            "request_id",
            "prompt",
            "negative_prompt",
            "style",
            "aspect_ratio",
            "resolution",
            "output_format",
            "requested_count",
            "generated_count",
            "provider",
            "model_name",
            "seed",
            "status",
            "generation_parameters",
            "error_code",
            "error_message",
            "started_at",
            "completed_at",
            "duration_ms",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
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
        ]

    def validate_prompt(self, value):
        """Reject empty prompts after trimming whitespace."""

        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Image prompt cannot be empty."
            )

        return value

    def validate_negative_prompt(self, value):
        """Normalize the optional negative prompt."""

        return value.strip()

    def validate_seed(self, value):
        """Allow non-negative seeds when a seed is provided."""

        if value is not None and value < 0:
            raise serializers.ValidationError(
                "Seed must be a non-negative integer."
            )

        return value

    def validate(self, attrs):
        """Apply request-wide validation."""

        prompt = attrs.get(
            "prompt",
            getattr(self.instance, "prompt", ""),
        )

        if not prompt or not prompt.strip():
            raise serializers.ValidationError({
                "prompt": "Image prompt cannot be empty."
            })

        return attrs

    def create(self, validated_data):
        """
        Create a generation request.

        The API view must pass the authenticated user explicitly:
            serializer.save(user=request.user)
        """

        if "user" not in validated_data:
            raise serializers.ValidationError(
                "The authenticated user must be assigned by the API."
            )

        return super().create(validated_data)


class GeneratedImageSerializer(serializers.ModelSerializer):
    """Read-only representation of a generated image."""

    class Meta:
        model = GeneratedImage
        fields = [
            "id",
            "generation",
            "image_index",
            "image_file",
            "image_url",
            "storage_provider",
            "mime_type",
            "file_size_bytes",
            "width",
            "height",
            "alt_text",
            "content_sha256",
            "is_public",
            "metadata",
            "created_at",
            "updated_at",
        ]

        read_only_fields = fields


class ImageGenerationDetailSerializer(
    ImageGenerationRequestSerializer
):
    """Generation request details, including its generated images."""

    images = GeneratedImageSerializer(
        many=True,
        read_only=True,
    )

    class Meta(ImageGenerationRequestSerializer.Meta):
        fields = ImageGenerationRequestSerializer.Meta.fields + [
            "images",
        ]

        read_only_fields = (
            ImageGenerationRequestSerializer.Meta.read_only_fields
            + ["images"]
        )

