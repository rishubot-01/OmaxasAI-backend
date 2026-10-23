
"""Image generation service for OmaxasAI."""

import base64
import binascii
import logging
import os
import re
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.images.models import GeneratedImage, ImageGenerationRequest
from apps.images.services.image_storage import (
    ImageStorageError,
    delete_generated_image,
    save_generated_image,
)

logger = logging.getLogger(__name__)

DEFAULT_IMAGE_MODEL = "gpt-image-2"
DEFAULT_IMAGE_QUALITY = "medium"
MAX_PROMPT_LENGTH = 10_000
MAX_IMAGE_BYTES = 30 * 1024 * 1024

ALLOWED_QUALITIES = {"low", "medium", "high"}

CUSTOM_ASPECT_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
    "16:9": "1536x864",
    "9:16": "864x1536",
    "4:3": "1024x768",
    "3:4": "768x1024",
}

STANDARD_ASPECT_SIZES = {
    "1:1": "1024x1024",
    "3:2": "1536x1024",
    "2:3": "1024x1536",
}

STYLE_INSTRUCTIONS = {
    "photorealistic": "Use a photorealistic visual style.",
    "cinematic": "Use a cinematic visual style and composition.",
    "anime": "Use a polished anime illustration style.",
    "illustration": "Create a detailed illustration.",
    "3d": "Use a polished 3D-rendered visual style.",
    "watercolor": "Use a watercolor painting style.",
    "pixel_art": "Use a pixel art visual style.",
}


class ImageGenerationError(Exception):
    """Base exception for image generation failures."""

    error_code = "image_generation_error"


class ImageGenerationConfigurationError(ImageGenerationError):
    """Raised when provider configuration is missing or invalid."""

    error_code = "image_configuration_error"


class ImageGenerationProviderError(ImageGenerationError):
    """Raised when the image provider fails."""

    error_code = "image_provider_error"


class ImageGenerationStateError(ImageGenerationError):
    """Raised when a request is not eligible for processing."""

    error_code = "invalid_generation_state"


class ImageOutputValidationError(ImageGenerationError):
    """Raised when the provider returns invalid image data."""

    error_code = "invalid_image_output"


@dataclass(frozen=True)
class ImageProviderConfig:
    """Provider configuration, including credentials loaded from the environment."""

    provider: str
    model: str
    api_key: str
    api_base: str | None
    quality: str


def _get_field(value, name, default=None):
    """Read a field from a dictionary or SDK object."""

    if isinstance(value, dict):
        return value.get(name, default)

    return getattr(value, name, default)


def _load_provider_config() -> ImageProviderConfig:
    """Load image provider settings from environment variables."""

    provider = os.getenv("OMAXASAI_IMAGE_PROVIDER", "openai").strip().lower()

    if provider != "openai":
        raise ImageGenerationConfigurationError(
            "Only the OpenAI image provider is currently supported."
        )

    key_env_name = os.getenv(
        "OMAXASAI_IMAGE_API_KEY_ENV",
        "OPENAI_API_KEY",
    ).strip()

    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key_env_name):
        raise ImageGenerationConfigurationError(
            "The image API key environment variable name is invalid."
        )

    api_key = os.getenv(key_env_name, "").strip()

    if not api_key:
        raise ImageGenerationConfigurationError(
            f"Configure {key_env_name} in your environment."
        )

    model = os.getenv(
        "OMAXASAI_IMAGE_MODEL",
        DEFAULT_IMAGE_MODEL,
    ).strip()

    if not model:
        raise ImageGenerationConfigurationError(
            "The image model name cannot be empty."
        )

    quality = os.getenv(
        "OMAXASAI_IMAGE_QUALITY",
        DEFAULT_IMAGE_QUALITY,
    ).strip().lower()

    if quality not in ALLOWED_QUALITIES:
        raise ImageGenerationConfigurationError(
            "Image quality must be low, medium, or high."
        )

    api_base = os.getenv("OMAXASAI_IMAGE_API_BASE", "").strip() or None

    return ImageProviderConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        api_base=api_base,
        quality=quality,
    )


def _create_client(config: ImageProviderConfig):
    """Create the OpenAI SDK client."""

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ImageGenerationConfigurationError(
            "The OpenAI package is missing. Install it with "
            "'python -m pip install openai'."
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
    """Validate a saved image-generation request."""

    if not isinstance(generation, ImageGenerationRequest):
        raise ImageGenerationStateError(
            "A valid image-generation request is required."
        )

    if generation.pk is None:
        raise ImageGenerationStateError(
            "Save the generation request before processing it."
        )

    prompt = generation.prompt

    if not isinstance(prompt, str) or not prompt.strip():
        raise ImageGenerationStateError(
            "The image prompt cannot be empty."
        )

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
            "The number of images must be between 1 and 4."
        )

    if generation.style not in ImageGenerationRequest.Style.values:
        raise ImageGenerationStateError("The image style is invalid.")

    if generation.aspect_ratio not in ImageGenerationRequest.AspectRatio.values:
        raise ImageGenerationStateError("The aspect ratio is invalid.")

    if generation.resolution not in ImageGenerationRequest.Resolution.values:
        raise ImageGenerationStateError("The resolution is invalid.")

    if generation.output_format not in {"png", "jpeg", "webp"}:
        raise ImageGenerationStateError("The output format is invalid.")


def _start_generation(
    generation: ImageGenerationRequest,
) -> ImageGenerationRequest:
    """Atomically claim a queued request for processing."""

    with transaction.atomic():
        try:
            current = (
                ImageGenerationRequest.objects.select_for_update()
                .get(pk=generation.pk)
            )
        except ImageGenerationRequest.DoesNotExist as exc:
            raise ImageGenerationStateError(
                "The image-generation request was not found."
            ) from exc

        if current.status != ImageGenerationRequest.Status.QUEUED:
            raise ImageGenerationStateError(
                "Only queued generation requests can be processed."
            )

        if current.images.exists():
            raise ImageGenerationStateError(
                "This request already has generated image records."
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
    """Build a provider prompt from the user's prompt and selected style."""

    parts = []

    instruction = STYLE_INSTRUCTIONS.get(generation.style)

    if instruction:
        parts.append(instruction)

    parts.append(generation.prompt.strip())

    if generation.negative_prompt and generation.negative_prompt.strip():
        parts.append(
            "Avoid the following visual elements where possible: "
            + generation.negative_prompt.strip()
        )

    return "\n\n".join(parts)


def _resolve_provider_size(
    generation: ImageGenerationRequest,
    model: str,
) -> str:
    """Select a supported provider size from the requested aspect ratio."""

    # GPT Image 2 supports custom dimensions within model limits.
    if model.startswith("gpt-image-2"):
        size = CUSTOM_ASPECT_SIZES.get(generation.aspect_ratio)

        if not size:
            raise ImageGenerationConfigurationError(
                "No supported image size exists for this aspect ratio."
            )

        return size

    # Other configured models may only support standard sizes.
    size = STANDARD_ASPECT_SIZES.get(generation.aspect_ratio)

    if not size:
        raise ImageGenerationConfigurationError(
            "This model does not support the selected aspect ratio "
            "through this service."
        )

    return size


def _call_provider(
    *,
    client,
    config: ImageProviderConfig,
    generation: ImageGenerationRequest,
    provider_size: str,
) -> list:
    """Call the image provider and return its generated image entries."""

    try:
        response = client.images.generate(
            model=config.model,
            prompt=_build_prompt(generation),
            size=provider_size,
            n=generation.requested_count,
            quality=config.quality,
            output_format=generation.output_format,
            moderation="auto",
        )
    except Exception as exc:
        logger.warning(
            "Image provider request failed. request_id=%s error_type=%s",
            generation.request_id,
            type(exc).__name__,
        )
        raise ImageGenerationProviderError(
            "The image provider could not generate the requested images. "
            "Check model access, API quota, billing, and network settings."
        ) from None

    entries = _get_field(response, "data")

    if not isinstance(entries, (list, tuple)) or not entries:
        raise ImageGenerationProviderError(
            "The image provider returned no image data."
        )

    if len(entries) != generation.requested_count:
        raise ImageGenerationProviderError(
            "The provider returned an unexpected number of images."
        )

    return list(entries)


def _decode_provider_image(entry) -> bytes:
    """Decode base64 image bytes without fetching arbitrary URLs."""

    encoded = _get_field(entry, "b64_json")

    if not isinstance(encoded, str) or not encoded:
        raise ImageOutputValidationError(
            "The provider returned an unsupported image response."
        )

    # Check encoded length first to avoid decoding an oversized payload.
    max_encoded_length = ((MAX_IMAGE_BYTES + 2) // 3) * 4

    if len(encoded) > max_encoded_length:
        raise ImageOutputValidationError(
            "The generated image exceeds the 30 MB size limit."
        )

    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ImageOutputValidationError(
            "The provider returned invalid base64 image data."
        ) from None

    if not image_bytes:
        raise ImageOutputValidationError(
            "The provider returned an empty image."
        )

    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise ImageOutputValidationError(
            "The generated image exceeds the 30 MB size limit."
        )

    return image_bytes


def _elapsed_ms(generation: ImageGenerationRequest) -> int:
    """Calculate elapsed processing time."""

    if generation.started_at is None:
        return 0

    milliseconds = (
        timezone.now() - generation.started_at
    ).total_seconds() * 1000

    return max(0, int(milliseconds))


def _cleanup_partial_images(
    generation: ImageGenerationRequest,
) -> None:
    """Remove already stored images if a multi-image request fails."""

    images = list(
        GeneratedImage.objects.filter(generation_id=generation.pk)
    )

    for image in images:
        try:
            delete_generated_image(image)
        except ImageStorageError as exc:
            logger.error(
                "Partial image cleanup failed. request_id=%s image_id=%s "
                "error_type=%s",
                generation.request_id,
                image.pk,
                type(exc).__name__,
            )


def _mark_failed(
    generation: ImageGenerationRequest,
    *,
    error_code: str,
    error_message: str,
) -> None:
    """Mark a processing request as failed using safe error details."""

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
            "Failed to update generation status. request_id=%s "
            "error_type=%s",
            generation.request_id,
            type(exc).__name__,
        )


def _complete_generation(
    *,
    generation: ImageGenerationRequest,
    config: ImageProviderConfig,
    provider_size: str,
    generated_count: int,
) -> ImageGenerationRequest:
    """Atomically mark the generation request as successful."""

    with transaction.atomic():
        current = (
            ImageGenerationRequest.objects.select_for_update()
            .get(pk=generation.pk)
        )

        if current.status != ImageGenerationRequest.Status.PROCESSING:
            raise ImageGenerationStateError(
                "The generation request is no longer processing."
            )

        actual_count = current.images.count()

        if (
            actual_count != generated_count
            or generated_count != current.requested_count
        ):
            raise ImageGenerationStateError(
                "Not all requested images were stored successfully."
            )

        now = timezone.now()

        current.provider = config.provider
        current.model_name = config.model
        current.generated_count = generated_count
        current.status = ImageGenerationRequest.Status.SUCCEEDED
        current.completed_at = now
        current.duration_ms = _elapsed_ms(current)
        current.generation_parameters = {
            "requested_resolution": current.resolution,
            "requested_aspect_ratio": current.aspect_ratio,
            "provider_size": provider_size,
            "quality": config.quality,
            "output_format": current.output_format,
            "requested_seed": current.seed,
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


def generate_images(
    generation: ImageGenerationRequest,
) -> ImageGenerationRequest:
    """
    Generate images for a queued request and save them through image_storage.

    The request status becomes SUCCEEDED after all requested images have
    been stored. On failure, partial files are cleaned up when possible
    and the request is marked FAILED.
    """

    _validate_request(generation)
    current = _start_generation(generation)

    try:
        config = _load_provider_config()
        client = _create_client(config)
        provider_size = _resolve_provider_size(current, config.model)

        current.provider = config.provider
        current.model_name = config.model
        current.generation_parameters = {
            "requested_resolution": current.resolution,
            "requested_aspect_ratio": current.aspect_ratio,
            "provider_size": provider_size,
            "quality": config.quality,
            "output_format": current.output_format,
            "requested_seed": current.seed,
        }

        current.save(
            update_fields=[
                "provider",
                "model_name",
                "generation_parameters",
                "updated_at",
            ]
        )

        entries = _call_provider(
            client=client,
            config=config,
            generation=current,
            provider_size=provider_size,
        )

        saved_images = []

        for index, entry in enumerate(entries):
            image_bytes = _decode_provider_image(entry)

            image = save_generated_image(
                generation=current,
                image_bytes=image_bytes,
                image_index=index,
                output_format=current.output_format,
                alt_text=current.prompt[:500],
                metadata={
                    "provider": config.provider,
                    "model": config.model,
                    "output_format": current.output_format,
                    "provider_size": provider_size,
                    "quality": config.quality,
                },
            )

            saved_images.append(image)

        completed = _complete_generation(
            generation=current,
            config=config,
            provider_size=provider_size,
            generated_count=len(saved_images),
        )

        logger.info(
            "Image generation completed. request_id=%s image_count=%s",
            completed.request_id,
            completed.generated_count,
        )

        return completed

    except ImageGenerationError as exc:
        _cleanup_partial_images(current)

        _mark_failed(
            current,
            error_code=exc.error_code,
            error_message=str(exc),
        )

        raise

    except Exception as exc:
        logger.error(
            "Unexpected image generation failure. request_id=%s "
            "error_type=%s",
            current.request_id,
            type(exc).__name__,
        )

        _cleanup_partial_images(current)

        public_message = (
            "Image generation failed unexpectedly. Please try again later."
        )

        _mark_failed(
            current,
            error_code="unexpected_generation_error",
            error_message=public_message,
        )

        raise ImageGenerationProviderError(public_message) from None
