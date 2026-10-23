
"""Tests for OmaxasAI image generation, storage, serializers, and APIs."""

import base64
import uuid
import tempfile
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from rest_framework.test import APIRequestFactory, force_authenticate

from .models import GeneratedImage, ImageGenerationRequest
from .serializers import (
    GeneratedImageSerializer,
    ImageGenerationRequestSerializer,
)
from .services.image_generation import (
    ImageGenerationProviderError,
    ImageProviderConfig,
    generate_images,
)
from .views import (
    ImageGenerationDetailView,
    ImageGenerationListCreateView,
)

User = get_user_model()


def make_png_bytes(width=64, height=64):
    """Create a small valid PNG image for tests without a real API call."""

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for image service tests. "
            "Install it using: python -m pip install Pillow"
        ) from exc

    buffer = BytesIO()

    image = Image.new("RGB", (width, height), (40, 120, 200))
    image.save(buffer, format="PNG")

    return buffer.getvalue()


class ImageGenerationRequestModelTests(TestCase):
    """Tests for image generation database models."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="images@example.com",
            password="StrongTestPass!8271",
        )

    def test_create_generation_request(self):
        request = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A futuristic city at sunset",
        )

        self.assertEqual(request.user, self.user)
        self.assertEqual(
            request.status,
            ImageGenerationRequest.Status.QUEUED,
        )
        self.assertEqual(request.requested_count, 1)
        self.assertEqual(request.generated_count, 0)
        self.assertIsNotNone(request.request_id)

    def test_request_id_is_unique(self):
        first = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A mountain landscape",
        )
        second = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A forest landscape",
        )

        self.assertNotEqual(first.request_id, second.request_id)

    def test_default_generation_settings(self):
        request = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A beautiful garden",
        )

        self.assertEqual(request.style, "auto")
        self.assertEqual(request.aspect_ratio, "1:1")
        self.assertEqual(request.resolution, "1024x1024")
        self.assertEqual(request.output_format, "png")

    def test_generated_image_belongs_to_request(self):
        generation = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="An illustrated orange cat",
        )

        image = GeneratedImage.objects.create(
            generation=generation,
            image_index=0,
            image_url="https://images.example.com/cat.png",
            storage_provider=GeneratedImage.StorageProvider.EXTERNAL,
            mime_type="image/png",
            width=1024,
            height=1024,
        )

        self.assertEqual(image.generation, generation)
        self.assertEqual(generation.images.count(), 1)

    def test_duplicate_image_indexes_are_rejected(self):
        """A generation cannot contain duplicate image indexes."""

        generation = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A blue ocean",
        )

        GeneratedImage.objects.create(
            generation=generation,
            image_index=0,
            image_url="https://images.example.com/first.png",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GeneratedImage.objects.create(
                    generation=generation,
                    image_index=0,
                    image_url="https://images.example.com/duplicate.png",
                )

        self.assertEqual(generation.images.count(), 1)


class ImageGenerationRequestSerializerTests(TestCase):
    """Tests for image generation input validation."""

    def test_valid_generation_request(self):
        serializer = ImageGenerationRequestSerializer(
            data={
                "prompt": "A cinematic view of the Himalayas",
                "style": "cinematic",
                "aspect_ratio": "16:9",
                "resolution": "1536x1024",
                "output_format": "png",
                "requested_count": 2,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["prompt"],
            "A cinematic view of the Himalayas",
        )

    def test_empty_prompt_is_rejected(self):
        serializer = ImageGenerationRequestSerializer(
            data={"prompt": "   "}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("prompt", serializer.errors)

    def test_missing_prompt_is_rejected(self):
        serializer = ImageGenerationRequestSerializer(
            data={"style": "anime"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("prompt", serializer.errors)

    def test_invalid_style_is_rejected(self):
        serializer = ImageGenerationRequestSerializer(
            data={
                "prompt": "A beautiful landscape",
                "style": "unknown-style",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("style", serializer.errors)

    def test_requested_count_cannot_exceed_limit(self):
        serializer = ImageGenerationRequestSerializer(
            data={
                "prompt": "A colorful abstract image",
                "requested_count": 5,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("requested_count", serializer.errors)

    def test_requested_count_must_be_positive(self):
        serializer = ImageGenerationRequestSerializer(
            data={
                "prompt": "A colorful abstract image",
                "requested_count": 0,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("requested_count", serializer.errors)

    def test_negative_seed_is_rejected(self):
        serializer = ImageGenerationRequestSerializer(
            data={
                "prompt": "A fantasy castle",
                "seed": -1,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("seed", serializer.errors)

    def test_client_cannot_set_processing_fields(self):
        """Server-controlled fields must retain their model defaults."""

        serializer = ImageGenerationRequestSerializer(
            data={
                "prompt": "A space station",
                "status": "succeeded",
                "provider": "untrusted-provider",
                "model_name": "untrusted-model",
                "generated_count": 4,
                "error_message": "client supplied",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        user = User.objects.create_user(
            email="serializer-images@example.com",
            password="StrongTestPass!8271",
        )

        generation = serializer.save(user=user)

        self.assertEqual(generation.user, user)
        self.assertEqual(
            generation.status,
            ImageGenerationRequest.Status.QUEUED,
        )
        self.assertEqual(generation.generated_count, 0)
        self.assertEqual(generation.provider, "")
        self.assertEqual(generation.model_name, "")
        self.assertEqual(generation.error_message, "")

    def test_generated_image_serializer_does_not_accept_writes(self):
        """
        GeneratedImageSerializer is read-only.

        DRF can consider input valid while ignoring read-only fields.
        The correct assertion is that no writable values are accepted.
        """

        serializer = GeneratedImageSerializer(
            data={
                "image_index": 0,
                "image_url": "https://images.example.com/flower.png",
                "is_public": True,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data, {})


class ImageGenerationAPITests(TestCase):
    """Tests for authentication and per-user image request access."""

    def setUp(self):
        self.factory = APIRequestFactory()

        self.user = User.objects.create_user(
            email="image-owner@example.com",
            password="StrongTestPass!8271",
        )

        self.other_user = User.objects.create_user(
            email="other-image-owner@example.com",
            password="StrongTestPass!8271",
        )

        self.own_request = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="My private image",
        )

        self.other_request = ImageGenerationRequest.objects.create(
            user=self.other_user,
            prompt="Another user's private image",
        )

    def test_list_returns_only_owned_requests(self):
        request = self.factory.get("/images/")
        force_authenticate(request, user=self.user)

        response = ImageGenerationListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        returned_ids = {
            item["id"]
            for item in response.data
        }

        self.assertIn(self.own_request.id, returned_ids)
        self.assertNotIn(self.other_request.id, returned_ids)

    def test_user_can_retrieve_own_request(self):
        request = self.factory.get(
            f"/images/{self.own_request.request_id}/"
        )
        force_authenticate(request, user=self.user)

        response = ImageGenerationDetailView.as_view()(
            request,
            request_id=self.own_request.request_id,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            str(response.data["request_id"]),
            str(self.own_request.request_id),
        )

    def test_user_cannot_retrieve_another_users_request(self):
        request = self.factory.get(
            f"/images/{self.other_request.request_id}/"
        )
        force_authenticate(request, user=self.user)

        response = ImageGenerationDetailView.as_view()(
            request,
            request_id=self.other_request.request_id,
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_cannot_list_requests(self):
        request = self.factory.get("/images/")

        response = ImageGenerationListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 401)

    def test_create_request_assigns_authenticated_user(self):
        request = self.factory.post(
            "/images/",
            {
                "prompt": "A realistic tiger in a jungle",
                "requested_count": 2,
                "user": self.other_user.pk,
                "status": "succeeded",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = ImageGenerationListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 201)

        generation = ImageGenerationRequest.objects.get(
            request_id=uuid.UUID(str(response.data["request_id"]))
        )

        self.assertEqual(generation.user, self.user)
        self.assertEqual(
            generation.status,
            ImageGenerationRequest.Status.QUEUED,
        )
        self.assertEqual(generation.requested_count, 2)
        self.assertEqual(
            generation.prompt,
            "A realistic tiger in a jungle",
        )


class ImageGenerationServiceTests(TestCase):
    """Tests for generation-service integration without real API requests."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="image-service@example.com",
            password="StrongTestPass!8271",
        )

        self.config = ImageProviderConfig(
            provider="openai",
            model="gpt-image-2",
            api_key="test-key-not-a-real-credential",
            api_base=None,
            quality="medium",
        )

    def test_generate_images_saves_image_and_completes_request(self):
        """Mock the external provider but exercise validation and storage."""

        generation = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A blue geometric flower",
            requested_count=1,
            output_format="png",
        )

        png_bytes = make_png_bytes()
        provider_entry = {
            "b64_json": base64.b64encode(png_bytes).decode("ascii"),
        }

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                with (
                    patch(
                        "apps.images.services.image_generation."
                        "_load_provider_config",
                        return_value=self.config,
                    ),
                    patch(
                        "apps.images.services.image_generation."
                        "_create_client",
                    ),
                    patch(
                        "apps.images.services.image_generation."
                        "_call_provider",
                        return_value=[provider_entry],
                    ),
                ):
                    completed = generate_images(generation)

                completed.refresh_from_db()

                self.assertEqual(
                    completed.status,
                    ImageGenerationRequest.Status.SUCCEEDED,
                )
                self.assertEqual(completed.generated_count, 1)
                self.assertEqual(completed.provider, "openai")
                self.assertEqual(completed.model_name, "gpt-image-2")
                self.assertIsNotNone(completed.completed_at)

                image = completed.images.get(image_index=0)

                self.assertEqual(image.mime_type, "image/png")
                self.assertEqual(image.width, 64)
                self.assertEqual(image.height, 64)
                self.assertEqual(image.file_size_bytes, len(png_bytes))
                self.assertTrue(image.image_file.name)
                self.assertTrue(image.image_file.storage.exists(
                    image.image_file.name
                ))

                # Remove the actual test file before the temporary directory
                # is deleted. Model/database cleanup alone does not remove it.
                image.image_file.delete(save=False)

    def test_provider_failure_marks_request_failed(self):
        generation = ImageGenerationRequest.objects.create(
            user=self.user,
            prompt="A quiet forest",
        )

        with (
            patch(
                "apps.images.services.image_generation."
                "_load_provider_config",
                return_value=self.config,
            ),
            patch(
                "apps.images.services.image_generation."
                "_create_client",
            ),
            patch(
                "apps.images.services.image_generation."
                "_call_provider",
                side_effect=ImageGenerationProviderError(
                    "Simulated provider failure."
                ),
            ),
        ):
            with self.assertRaises(ImageGenerationProviderError):
                generate_images(generation)

        generation.refresh_from_db()

        self.assertEqual(
            generation.status,
            ImageGenerationRequest.Status.FAILED,
        )
        self.assertEqual(
            generation.error_code,
            ImageGenerationProviderError.error_code,
        )
        self.assertIsNotNone(generation.completed_at)
        self.assertEqual(generation.images.count(), 0)
