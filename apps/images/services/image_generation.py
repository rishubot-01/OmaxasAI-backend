
"""Image generation service for OmaxasAI.

This implementation currently supports OpenAI's GPT Image API.
Provider credentials are read from environment variables, never from
database records or user-submitted API parameters.
"""

import base64
import binascii
import logging
import os
import re
from dataclasses import dataclass
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.images.models import GeneratedImage, ImageGenerationRequest

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_IMAGE_QUALITY = "medium"

MAX_PROMPT_LENGTH = 10_000
MAX_IMAGE_BYTES = 30 * 1024 * 1024
MAX_IMAGE_DIMENSION = 3840

ALLOWED_QUALITIES = {"low", "medium", "high"}

FORMAT_DETAILS = {
    "png": {
        "extension": "png",
        "mime_type": "image/png",
        "pillow_format": "PNG",
    },
    "jpeg": {
        "extension": "jpg",
        "mime_type": "image/jpeg",
        "pillow_format": "JPEG",
    },
    "webp": {
        "extension": "webp",
        "mime_type": "image/webp",
        "pillow_format": "WEBP",
    },
}

# Custom dimensions are supported by current GPT Image 2 models.
# They are all multiples of 16 and meet the provider's documented
# minimum pixel count.
CUSTOM_ASPECT_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "16:9": "1536x864",
    "9:16": "864x1536",
    "4:3": "1024x768",
    "3:4": "768x1024",
}

# Use standard dimensions with older GPT Image models that do not
# support arbitrary width-by-height sizes.
STANDARD_ASPECT_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "16:9": "1536x1024",
    "9:16": "1024x1536",
    "4:3": "1536x1024",
    "3:4": "1024x1536",
}

STYLE_INSTRUCTIONS = {
    "photorealistic": "Use a photorealistic visual style.",
    "cinematic": "Use a cinematic visual style and composition.",
    "anime": "Use a polished anime illustration style.",
    "illustration": "Create a detailed illustration.",
    "3d": "Use a polished three-dimensional 3D-rendered style.",
    "watercolor": "Use a watercolor painting style.",
    "pixel_art": "Use a pixel art visual style.",
}


class ImageGenerationError(Exception):
    """Base exception for image generation failures."""

    error_code = "image_generation_error"


class ImageGenerationConfigurationError(ImageGenerationError):
    """Raised when required provider configuration is missing."""

    error_code = "image_configuration_error"


class ImageGenerationProviderError(ImageGenerationError):
    """Raised when the external provider cannot generate an image."""

    error_code = "image_provider_error"


class ImageGenerationStateError(ImageGenerationError):
    """Raised when a request is not eligible for generation."""

    error_code = "invalid_generation_state"


class ImageOutputValidationError(ImageGenerationError):
    """Raised when a provider returns invalid image data."""

    error_code = "invalid_image_output"


@dataclass(frozen=True)
class ImageProviderConfig:
    """Non-secret image provider configuration."""

    provider: str
    model: str
    api_key: str
    api_base: str | None
    quality: str


@dataclass(frozen=True)
class DecodedImage:
    """Validated image bytes and actual image dimensions."""

    data: bytes
    width: int
    height: int
    mime_type: str
    extension: str


def _get_field(value, field_name, default=None):
    """Read a field from either a dictionary or an SDK response object."""

    if isinstance(value, dict):
        return value.get(field_name, default)

    return getattr(value, field_name, default)


def _load_provider_config() -> ImageProviderConfig:
    """Load provider configuration without logging any credentials."""

    provider = os.getenv(
        "OMAXASAI_IMAGE_PROVIDER",
        "openai",
    ).strip().lower()

    if provider != "openai":
        raise ImageGenerationConfigurationError(
            "The configured image provider is not supported yet. "
            "Currently supported provider: openai."
        )

    key_env_name = os.getenv(
        "OMAXASAI_IMAGE_API_KEY_ENV",
        "OPENAI_API_KEY",
    ).strip()

    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key_env_name):
        raise ImageGenerationConfigurationError(
            "OMAXASAI_IMAGE_API_KEY_ENV must contain a valid "
            "environment variable name."
        )

    api_key = os.getenv(key_env_name, "").strip()

    if not api_key:
        raise ImageGenerationConfigurationError(
            f"Image API credentials are missing. Configure {key_env_name} "
            "in the environment."
        )

    model = os.getenv(
        "OMAXASAI_IMAGE_MODEL",
        DEFAULT_IMAGE_MODEL,
    ).strip()

    if not model:
        raise ImageGenerationConfigurationError(
            "OMAXASAI_IMAGE_MODEL cannot be empty."
        )

    quality = os.getenv(
        "OMAXASAI_IMAGE_QUALITY",
        DEFAULT_IMAGE_QUALITY,
    ).strip().lower()

    if quality not in ALLOWED_QUALITIES:
        raise ImageGenerationConfigurationError(
            "OMAXASAI_IMAGE_QUALITY must be low, medium, or high."
        )

    api_base = os.getenv("OMAXASAI_IMAGE_API_BASE", "").strip() or None

    return ImageProviderConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
        quality=quality,
    )


def _create_openai_client(config: ImageProviderConfig):
    """Create the provider SDK client lazily."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImageGenerationConfigurationError(
            "The OpenAI Python SDK is not installed. "
            "Install it with: python -m pip install openai"
        ) from exc

    options = {
        "api_key": config.api_key,
        "timeout": 180.0,
        "max_retries": 1,
    }

    if config.api_base:
        options["base_url"] = config.api_base

    return OpenAI(**options)


def _validate_request(generation: ImageGenerationRequest) -> None:
    """Validate generation data before calling the external provider."""

    if not isinstance(generation, ImageGenerationRequest):
        raise ImageGenerationStateError(
            "A valid image generation request is required."
        )

    if generation.pk is None:
        raise ImageGenerationStateError(
            "Save the generation request before generating an image."
        )

    if not isinstance(generation.prompt, str):
        raise ImageGenerationStateError("The image prompt must be text.")

    prompt = generation.prompt.strip()

    if not prompt:
        raise ImageGenerationStateError("The image prompt cannot be empty.")

    if len(prompt) > MAX_PROMPT_LENGTH:
        raise ImageGenerationStateError(
            f"The image prompt cannot exceed {MAX_PROMPT_LENGTH} characters."
        )

    if (
        isinstance(generation.requested_count, bool)
        or not isinstance(generation.requested_count, int)
        or not 1 <= generation.requested_count <= 4
    ):
        raise ImageGenerationStateError(
            "The number of generated images must be between 1 and 4."
        )

    if generation.style not in ImageGenerationRequest.Style.values:
        raise ImageGenerationStateError("The selected image style is invalid.")

    if (
        generation.aspect_ratio
        not in ImageGenerationRequest.AspectRatio.values
    ):
        raise ImageGenerationStateError("The selected aspect ratio is invalid.")

    if generation.output_format not in FORMAT_DETAILS:
        raise ImageGenerationStateError(
            "The requested output format is not supported."
        )


def _start_generation(
    generation: ImageGenerationRequest,
) -> ImageGenerationRequest:
    """Lock a queued request and change its status to processing."""

    with transaction.atomic():
        try:
            current = (
                ImageGenerationRequest.objects.select_for_update()
                .get(pk=generation.pk)
            )
        except ImageGenerationRequest.DoesNotExist as exc:
            raise ImageGenerationStateError(
                "The image generation request no longer exists."
            ) from exc

        if current.status != ImageGenerationRequest.Status.QUEUED:
            raise ImageGenerationStateError(
                "Only queued image generation requests can be processed."
            )

        current.status = ImageGenerationRequest.Status.PROCESSING
        current.started_at = timezone.now()
        current.completed_at = None
        current.duration_ms = None
        current.generated_count = 0
        current.error_code = ""
        current.error_message = ""
        current.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "duration_ms",
                "generated_count",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )

        return current


def _build_prompt(generation: ImageGenerationRequest) -> str:
    """Add optional style and negative-prompt instructions."""

    parts = []

    style_instruction = STYLE_INSTRUCTIONS.get(generation.style)

    if style_instruction:
        parts.append(style_instruction)

    parts.append(generation.prompt.strip())

    if generation.negative_prompt and generation.negative_prompt.strip():
        parts.append(
            "Avoid depicting the following elements where possible: "
            + generation.negative_prompt.strip()
        )

    # The image endpoint does not expose a universal negative_prompt field.
    # These are natural-language instructions included in the prompt instead.
    return "\n\n".join(parts)


def _resolve_provider_size(
    generation: ImageGenerationRequest,
    model: str,
) -> str:
    """Choose a provider-compatible size for the requested aspect ratio."""

    if model.startswith("gpt-image-2"):
        size = CUSTOM_ASPECT_SIZES.get(generation.aspect_ratio)
    else:
        size = STANDARD_ASPECT_SIZES.get(generation.aspect_ratio)

    if not size:
        raise ImageGenerationConfigurationError(
            "No compatible image size exists for the selected aspect ratio."
        )

    return size


def _call_provider(
    *,
    client,
    config: ImageProviderConfig,
    generation: ImageGenerationRequest,
) -> list:
    """Call the OpenAI Image API and return the generated image entries."""

    provider_prompt = _build_prompt(generation)
    size = _resolve_provider_size(generation, config.model)

    try:
        response = client.images.generate(
            model=config.model,
            prompt=provider_prompt,
            size=size,
            n=generation.requested_count,
            quality=config.quality,
            output_format=generation.output_format,
            moderation="auto",
        )
    except Exception as exc:
        # Do not log prompts, API keys, raw provider responses, or URLs.
        logger.warning(
            "Image provider request failed. request_id=%s error_type=%s",
            generation.request_id,
            type(exc).__name__,
        )
        raise ImageGenerationProviderError(
            "The image provider could not generate the requested image. "
            "Check model access, API quota, billing, and network availability."
        ) from None

    entries = _get_field(response, "data")

    if not isinstance(entries, (list, tuple)) or not entries:
        raise ImageGenerationProviderError(
            "The image provider returned no image data."
        )

    if len(entries) != generation.requested_count:
        raise ImageGenerationProviderError(
            "The image provider returned an unexpected number of images."
        )

    return list(entries)


def _decode_and_validate_image(
    entry,
    *,
    output_format: str,
) -> DecodedImage:
    """Decode base64 image data and verify the actual image file."""

    encoded = _get_field(entry, "b64_json")

    if not isinstance(encoded, str) or not encoded:
        # GPT Image API results are expected to contain base64 image data.
        # This service intentionally does not fetch arbitrary provider URLs.
        raise ImageOutputValidationError(
            "The image provider returned an unsupported image response."
        )

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ImageOutputValidationError(
            "The provider returned invalid encoded image data."
        ) from None

    if not image_bytes:
        raise ImageOutputValidationError(
            "The provider returned an empty image."
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageOutputValidationError(
            "The generated image exceeds the 30 MB size limit."
        )

    try:
        from PIL import Image
    except ImportError as exc:
        raise ImageGenerationConfigurationError(
            "Pillow is required to validate generated image files. "
            "Install it with: python -m pip install Pillow"
        ) from exc

    try:
        with Image.open(BytesIO(image_bytes)) as image:
            actual_format = image.format
            image.verify()

        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size

    except Exception:
        raise ImageOutputValidationError(
            "The provider returned an invalid or unreadable image."
        ) from None

    expected = FORMAT_DETAILS[output_format]

    if actual_format != expected["pillow_format"]:
        raise ImageOutputValidationError(
            "The image format returned by the provider does not match "
            "the requested output format."
        )

    if (
        width <= 0
        or height <= 0
        or width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
    ):
        raise ImageOutputValidationError(
            "The generated image dimensions are outside the supported limits."
        )

    return DecodedImage(
        data=image_bytes,
        width=width,
        height=height,
        mime_type=expected["mime_type"],
        extension=expected["extension"],
    )


def _elapsed_ms(generation: ImageGenerationRequest) -> int:
    """Calculate elapsed processing time in milliseconds."""

    if generation.started_at is None:
        return 0

    elapsed = (timezone.now() - generation.started_at).total_seconds()

    return max(0, int(elapsed * 1000))


def _mark_failed(
    generation: ImageGenerationRequest,
    *,
    error_code: str,
    error_message: str,
) -> None:
    """Mark a processing request as failed with a safe error message."""

    now = timezone.now()

    try:
        ImageGenerationRequest.objects.filter(
            pk=generation.pk,
            status=ImageGenerationRequest.Status.PROCESSING,
        ).update(
            status=ImageGenerationRequest.Status.FAILED,
            error_code=error_code[:100],
            error_message=error_message[:500],
            completed_at=now,
            duration_ms=_elapsed_ms(generation),
            updated_at=now,
        )
    except Exception as exc:
        logger.error(
            "Could not update failed image request status. "
            "request_id=%s error_type=%s",
            generation.request_id,
            type(exc).__name__,
        )


def _save_generated_images(
    *,
    generation: ImageGenerationRequest,
    decoded_images: list[DecodedImage],
    config: ImageProviderConfig,
    requested_size: str,
) -> ImageGenerationRequest:
    """Persist validated images and complete the generation request."""

    stored_files = []

    try:
        with transaction.atomic():
            current = (
                ImageGenerationRequest.objects.select_for_update()
                .get(pk=generation.pk)
            )

            if current.status != ImageGenerationRequest.Status.PROCESSING:
                raise ImageGenerationStateError(
                    "The generation request is no longer being processed."
                )

            for index, decoded in enumerate(decoded_images):
                image_record = GeneratedImage(
                    generation=current,
                    image_index=index,
                    storage_provider=GeneratedImage.StorageProvider.DEFAULT,
                    mime_type=decoded.mime_type,
                    file_size_bytes=len(decoded.data),
                    width=decoded.width,
                    height=decoded.height,
                    alt_text=current.prompt[:500],
                    metadata={
                        "provider": config.provider,
                        "model": config.model,
                        "output_format": current.output_format,
                    },
                )

                filename = (
                    f"omaxasai-{current.request_id}-"
                    f"{index + 1}.{decoded.extension}"
                )

                image_record.image_file.save(
                    filename,
                    ContentFile(decoded.data),
                    save=False,
                )

                # Track the stored file before saving the database record,
                # so it can be cleaned up if the database transaction fails.
                stored_files.append(
                    (
                        image_record.image_file.storage,
                        image_record.image_file.name,
                    )
                )

                image_record.save()

            now = timezone.now()

            current.provider = config.provider
            current.model_name = config.model
            current.generated_count = len(decoded_images)
            current.status = ImageGenerationRequest.Status.SUCCEEDED
            current.completed_at = now
            current.duration_ms = _elapsed_ms(current)
            current.generation_parameters = {
                "requested_resolution": current.resolution,
                "requested_aspect_ratio": current.aspect_ratio,
                "provider_size": requested_size,
                "quality": config.quality,
                "output_format": current.output_format,
            }

            current.save(
                update_fields=[
                    "provider",
                    "model_name",
                    "generated_count",
                    "status",
                    "completed_at",
                    "duration_ms",
                    "generation_parameters",
                    "updated_at",
                ]
            )

        return current

    except Exception:
        # Database rollback does not automatically remove media files.
        for storage, stored_name in stored_files:
            try:
                storage.delete(stored_name)
            except Exception as cleanup_error:
                logger.error(
                    "Could not clean up an image file after failure. "
                    "error_type=%s",
                    type(cleanup_error).__name__,
                )

        raise


def generate_images(
    generation: ImageGenerationRequest,
) -> ImageGenerationRequest:
    """
    Generate and persist all images for a queued request.

    The returned request has a final status of succeeded when processing
    finishes successfully. Failures update its status to failed and raise
    an ImageGenerationError for the calling service or view to handle.
    """

    _validate_request(generation)
    current = _start_generation(generation)

    try:
        config = _load_provider_config()
        client = _create_openai_client(config)
        provider_size = _resolve_provider_size(current, config.model)

        current.provider = config.provider
        current.model_name = config.model
        current.generation_parameters = {
            "requested_resolution": current.resolution,
            "requested_aspect_ratio": current.aspect_ratio,
            "provider_size": provider_size,
            "quality": config.quality,
            "output_format": current.output_format,
        }

        current.save(
            update_fields=[
                "provider",
                "model_name",
                "generation_parameters",
                "updated_at",
            ]
        )

        provider_entries = _call_provider(
            client=client,
            config=config,
            generation=current,
        )

        # Validate all outputs before persisting any of them.
        decoded_images = [
            _decode_and_validate_image(
                entry,
                output_format=current.output_format,
            )
            for entry in provider_entries
        ]

        completed = _save_generated_images(
            generation=current,
            decoded_images=decoded_images,
            config=config,
            requested_size=provider_size,
        )

        logger.info(
            "Image generation completed. request_id=%s image_count=%s",
            completed.request_id,
            completed.generated_count,
        )

        return completed

    except ImageGenerationError as exc:
        _mark_failed(
            current,
            error_code=exc.error_code,
            error_message=str(exc),
        )
        raise

    except Exception as exc:
        logger.warning(
            "Unexpected image generation failure. request_id=%s error_type=%s",
            current.request_id,
            type(exc).__name__,
        )

        public_message = (
            "Image generation failed unexpectedly. Please try again later."
        )

        _mark_failed(
            current,
            error_code="unexpected_generation_error",
            error_message=public_message,
        )

        raise ImageGenerationProviderError(public_message) from None

