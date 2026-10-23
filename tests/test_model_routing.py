
"""Integration tests for OmaxasAI model classification and routing."""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.assistant.models import ModelRegistry
from apps.assistant.services.model_router import (
    NoSuitableModelError,
    choose_model,
)
from apps.assistant.services.task_classifier import classify_task

User = get_user_model()


class TaskClassificationTests(TestCase):
    """Test classification of common assistant prompts."""

    def test_coding_prompt_is_classified(self):
        category = classify_task("Write a Python function to sort a list.")

        self.assertEqual(category, "coding")

    def test_research_prompt_is_classified(self):
        category = classify_task(
            "Research the latest technology news and cite sources."
        )

        self.assertEqual(category, "research")

    def test_writing_prompt_is_classified(self):
        category = classify_task(
            "Write a professional email to my manager."
        )

        self.assertEqual(category, "writing")

    def test_reasoning_prompt_is_classified(self):
        category = classify_task(
            "Solve this equation step by step."
        )

        self.assertEqual(category, "reasoning")

    def test_image_input_is_classified_as_vision(self):
        category = classify_task(
            "Describe this picture.",
            has_images=True,
        )

        self.assertEqual(category, "vision")

    def test_web_search_request_is_classified_as_research(self):
        category = classify_task(
            "Find reliable information about climate research.",
            web_search=True,
        )

        self.assertEqual(category, "research")


class ModelRoutingTests(TestCase):
    """Test model selection against the registered model catalogue."""

    def setUp(self):
        self.environment_patcher = patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key-not-a-real-credential"},
        )
        self.environment_patcher.start()
        self.addCleanup(self.environment_patcher.stop)

    def create_model(
        self,
        *,
        model_id,
        name=None,
        provider="openai",
        capabilities=None,
        active=True,
        supports_streaming=True,
        supports_vision=False,
        supports_tools=False,
        priority=10,
        credential_env_var="OPENAI_API_KEY",
        backend_type="external_api",
    ):
        """Create a registered model with explicit routing capabilities."""

        return ModelRegistry.objects.create(
            name=name or model_id,
            provider=provider,
            model_id=model_id,
            backend_type=backend_type,
            credential_env_var=credential_env_var,
            capabilities=(
                capabilities if capabilities is not None else ["chat"]
            ),
            context_window=128000,
            supports_streaming=supports_streaming,
            supports_vision=supports_vision,
            supports_tools=supports_tools,
            priority=priority,
            active=active,
        )

    @staticmethod
    def resolve_selected_model(route):
        """
        Resolve the model object from the router result.

        This accepts a direct model result or a route wrapper that exposes
        the selected registry model through a common model attribute.
        """

        for attribute in ("model", "registry", "model_registry"):
            value = getattr(route, attribute, None)

            if isinstance(value, ModelRegistry):
                return value

        if isinstance(route, ModelRegistry):
            return route

        raise AssertionError(
            "The model router did not expose a selected ModelRegistry model."
        )

    def select_model(
        self,
        message,
        *,
        mode="auto",
        web_search=False,
        has_images=False,
        stream=False,
    ):
        """Call the model router with the standard assistant request."""

        return choose_model(
            message=message,
            mode=mode,
            web_search=web_search,
            has_images=has_images,
            stream=stream,
        )

    def test_router_selects_coding_capable_model(self):
        expected = self.create_model(
            model_id="test-coder",
            capabilities=["chat", "coding"],
            priority=1,
        )

        self.create_model(
            model_id="test-general",
            capabilities=["chat", "general"],
            priority=20,
        )

        route = self.select_model("Write a Python function.")

        selected = self.resolve_selected_model(route)

        self.assertEqual(selected.pk, expected.pk)

    def test_router_selects_reasoning_model_for_think_mode(self):
        expected = self.create_model(
            model_id="test-reasoner",
            capabilities=["chat", "reasoning", "think"],
            priority=1,
        )

        self.create_model(
            model_id="test-basic-chat",
            capabilities=["chat", "coding"],
            priority=2,
        )

        route = self.select_model(
            "Solve this equation step by step.",
            mode="think",
        )

        selected = self.resolve_selected_model(route)

        self.assertEqual(selected.pk, expected.pk)

    def test_router_does_not_select_inactive_model(self):
        self.create_model(
            model_id="inactive-coder",
            capabilities=["chat", "coding"],
            active=False,
        )

        with self.assertRaises(NoSuitableModelError):
            self.select_model("Write a Python function.")

    def test_router_selects_vision_capable_model(self):
        expected = self.create_model(
            model_id="test-vision",
            capabilities=["chat", "vision"],
            supports_vision=True,
        )

        self.create_model(
            model_id="test-text-only",
            capabilities=["chat", "coding"],
            supports_vision=False,
        )

        route = self.select_model(
            "Describe the contents of this picture.",
            has_images=True,
        )

        selected = self.resolve_selected_model(route)

        self.assertEqual(selected.pk, expected.pk)

    def test_router_requires_streaming_support_when_stream_enabled(self):
        expected = self.create_model(
            model_id="test-streaming",
            capabilities=["chat", "coding"],
            supports_streaming=True,
        )

        self.create_model(
            model_id="test-non-streaming",
            capabilities=["chat", "coding"],
            supports_streaming=False,
            priority=1,
        )

        route = self.select_model(
            "Write a function.",
            stream=True,
        )

        selected = self.resolve_selected_model(route)

        self.assertEqual(selected.pk, expected.pk)

    def test_router_rejects_models_without_available_credentials(self):
        self.create_model(
            model_id="test-missing-key",
            capabilities=["chat", "coding"],
            credential_env_var="OMAXASAI_TEST_MISSING_KEY",
        )

        with patch.dict(os.environ, {"OMAXASAI_TEST_MISSING_KEY": ""}):
            with self.assertRaises(NoSuitableModelError):
                self.select_model("Write a Python function.")

    def test_router_rejects_when_no_model_is_registered(self):
        with self.assertRaises(NoSuitableModelError):
            self.select_model("Explain a concept.")

    def test_router_skips_models_that_do_not_support_vision(self):
        self.create_model(
            model_id="text-only-model",
            capabilities=["chat", "coding"],
            supports_vision=False,
        )

        with self.assertRaises(NoSuitableModelError):
            self.select_model(
                "What is shown in this image?",
                has_images=True,
            )

    def test_router_skips_non_streaming_models_for_stream_requests(self):
        self.create_model(
            model_id="non-streaming-only",
            capabilities=["chat", "coding"],
            supports_streaming=False,
        )

        with self.assertRaises(NoSuitableModelError):
            self.select_model(
                "Write some code.",
                stream=True,
            )

