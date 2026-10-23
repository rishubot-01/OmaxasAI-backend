
"""Tests for OmaxasAI Explore API views and filters."""

from django.test import TestCase

from rest_framework.test import APIRequestFactory

from apps.assistant.models import ModelRegistry

from .views import (
    ExploreFeaturesView,
    ExploreModelsView,
    ExploreProvidersView,
)


class ExploreAPITests(TestCase):
    """Test model discovery, filtering, providers, and features."""

    def setUp(self):
        self.factory = APIRequestFactory()

        self.coding_model = ModelRegistry.objects.create(
            name="Test Coding Model",
            provider="openai",
            model_id="test-coding-model",
            backend_type="external_api",
            credential_env_var="OPENAI_API_KEY",
            capabilities=["chat", "coding", "reasoning"],
            context_window=128000,
            supports_streaming=True,
            supports_vision=False,
            supports_tools=True,
            priority=1,
            active=True,
        )

        self.vision_model = ModelRegistry.objects.create(
            name="Test Vision Model",
            provider="gemini",
            model_id="test-vision-model",
            backend_type="external_api",
            credential_env_var="GEMINI_API_KEY",
            capabilities=["chat", "vision", "research"],
            context_window=100000,
            supports_streaming=True,
            supports_vision=True,
            supports_tools=False,
            priority=2,
            active=True,
        )

        self.inactive_model = ModelRegistry.objects.create(
            name="Inactive Test Model",
            provider="openai",
            model_id="inactive-test-model",
            backend_type="external_api",
            credential_env_var="OPENAI_API_KEY",
            capabilities=["chat", "coding"],
            context_window=32000,
            supports_streaming=False,
            supports_vision=False,
            supports_tools=False,
            priority=3,
            active=False,
        )

    def get_models_response(self, query_params=None):
        """Call the model listing view with query parameters."""

        request = self.factory.get(
            "/explore/models/",
            data=query_params or {},
        )

        return ExploreModelsView.as_view()(request)

    def test_models_endpoint_returns_active_models(self):
        response = self.get_models_response()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

        model_ids = {
            item["model_id"]
            for item in response.data["results"]
        }

        self.assertIn("test-coding-model", model_ids)
        self.assertIn("test-vision-model", model_ids)
        self.assertNotIn("inactive-test-model", model_ids)

    def test_model_search_by_name(self):
        response = self.get_models_response({
            "query": "Vision",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["model_id"],
            "test-vision-model",
        )

    def test_model_search_is_case_insensitive(self):
        response = self.get_models_response({
            "query": "OPENAI",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["provider"],
            "openai",
        )

    def test_filter_models_by_coding_category(self):
        response = self.get_models_response({
            "category": "coding",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["model_id"],
            "test-coding-model",
        )

    def test_filter_models_by_vision_capability(self):
        response = self.get_models_response({
            "capability": "vision",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["model_id"],
            "test-vision-model",
        )

    def test_filter_models_by_streaming(self):
        response = self.get_models_response({
            "capability": "streaming",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_filter_models_by_tool_support(self):
        response = self.get_models_response({
            "supports_tools": "true",
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["model_id"],
            "test-coding-model",
        )

    def test_invalid_category_is_rejected(self):
        response = self.get_models_response({
            "category": "not-a-valid-category",
        })

        self.assertEqual(response.status_code, 400)

    def test_invalid_capability_is_rejected(self):
        response = self.get_models_response({
            "capability": "unknown-capability",
        })

        self.assertEqual(response.status_code, 400)

    def test_query_length_is_validated(self):
        response = self.get_models_response({
            "query": "x" * 201,
        })

        self.assertEqual(response.status_code, 400)

    def test_models_endpoint_does_not_expose_secrets(self):
        response = self.get_models_response()

        self.assertEqual(response.status_code, 200)

        for item in response.data["results"]:
            self.assertNotIn("credential_env_var", item)
            self.assertNotIn("endpoint_url", item)
            self.assertNotIn("config", item)

    def test_providers_endpoint_aggregates_active_models(self):
        request = self.factory.get("/explore/providers/")

        response = ExploreProvidersView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

        providers = {
            item["provider"]: item
            for item in response.data["results"]
        }

        self.assertIn("openai", providers)
        self.assertIn("gemini", providers)

        # The inactive OpenAI model should not be counted.
        self.assertEqual(providers["openai"]["model_count"], 1)
        self.assertEqual(providers["gemini"]["model_count"], 1)

        self.assertIn(
            "coding",
            providers["openai"]["capabilities"],
        )
        self.assertIn(
            "vision",
            providers["gemini"]["capabilities"],
        )

    def test_features_endpoint_returns_feature_status(self):
        request = self.factory.get("/explore/features/")

        response = ExploreFeaturesView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data["count"], 0)

        features = {
            item["slug"]: item
            for item in response.data["results"]
        }

        self.assertIn("model-explorer", features)
        self.assertTrue(features["model-explorer"]["available"])

        self.assertIn("ai-chat", features)
        self.assertTrue(features["ai-chat"]["available"])

        # These integrations are currently declared unavailable by the view.
        self.assertFalse(features["knowledge-search"]["available"])
        self.assertFalse(features["image-generation"]["available"])
        self.assertFalse(features["web-search"]["available"])

    def test_feature_status_when_no_active_models_exist(self):
        ModelRegistry.objects.filter(active=True).update(active=False)

        request = self.factory.get("/explore/features/")
        response = ExploreFeaturesView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        features = {
            item["slug"]: item
            for item in response.data["results"]
        }

        self.assertFalse(features["ai-chat"]["available"])

