
"""Integration smoke tests for the OmaxasAI API."""

from django.urls import reverse

from rest_framework import status
from rest_framework.test import APITestCase


class APIRootTests(APITestCase):
    """Tests for the API overview endpoint."""

    def test_api_root_returns_service_information(self):
        response = self.client.get(reverse("api-root"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()

        self.assertEqual(data["name"], "OmaxasAI API")
        self.assertEqual(data["status"], "running")
        self.assertIn("endpoints", data)

    def test_api_root_lists_main_endpoint_groups(self):
        response = self.client.get(reverse("api-root"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        endpoints = response.json()["endpoints"]

        expected_endpoints = {
            "admin",
            "authentication",
            "accounts",
            "assistant",
            "conversations",
            "knowledge",
            "images",
            "explore",
        }

        self.assertTrue(expected_endpoints.issubset(endpoints.keys()))


class ExploreAPIRouteTests(APITestCase):
    """Tests for public Explore routes and query validation."""

    def test_models_endpoint_is_accessible(self):
        response = self.client.get("/api/explore/models/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()

        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

    def test_providers_endpoint_is_accessible(self):
        response = self.client.get("/api/explore/providers/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()

        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)

    def test_features_endpoint_is_accessible(self):
        response = self.client.get("/api/explore/features/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()

        self.assertIn("count", data)
        self.assertIn("results", data)

        feature_slugs = {
            feature["slug"]
            for feature in data["results"]
        }

        self.assertIn("model-explorer", feature_slugs)
        self.assertIn("knowledge-search", feature_slugs)
        self.assertIn("image-generation", feature_slugs)

    def test_invalid_explore_category_returns_bad_request(self):
        response = self.client.get(
            "/api/explore/models/",
            {"category": "invalid-category"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_invalid_explore_capability_returns_bad_request(self):
        response = self.client.get(
            "/api/explore/models/",
            {"capability": "invalid-capability"},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_explore_search_accepts_valid_query(self):
        response = self.client.get(
            "/api/explore/models/",
            {"query": "openai"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.json())


class AuthenticationRouteTests(APITestCase):
    """Basic smoke tests for authentication endpoints."""

    def test_token_endpoint_rejects_missing_credentials(self):
        response = self.client.post(
            "/api/auth/token/",
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_registration_route_exists(self):
        response = self.client.post(
            "/api/auth/register/",
            {},
            format="json",
        )

        # An invalid registration payload should produce validation errors,
        # rather than a missing-route 404.
        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class ProtectedAPIRouteTests(APITestCase):
    """Ensure protected APIs reject unauthenticated requests."""

    def test_knowledge_documents_require_authentication(self):
        response = self.client.get("/api/knowledge/")

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_image_generation_requires_authentication(self):
        response = self.client.get("/api/images/")

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_assistant_chat_requires_authentication(self):
        response = self.client.post(
            "/api/assistant/chat/",
            {
                "message": "Hello",
                "mode": "auto",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_conversation_list_requires_authentication(self):
        response = self.client.get("/api/conversations/")

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class InvalidRouteTests(APITestCase):
    """Ensure unknown API paths do not accidentally resolve."""

    def test_unknown_api_route_returns_not_found(self):
        response = self.client.get("/api/this-route-does-not-exist/")

        self.assertEqual(
            response.status_code,
            status.HTTP_404_NOT_FOUND,
        )

