
"""API views for discovering AI models and features in OmaxasAI Explore."""

from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assistant.models import ModelRegistry

from .serializers import (
    ExploreFeatureSerializer,
    ExploreModelSerializer,
    ExploreProviderSerializer,
    ExploreSearchSerializer,
)


class ExploreModelsView(APIView):
    """List and filter active AI models using public-safe metadata."""

    permission_classes = [AllowAny]

    def get(self, request):
        """Return active models filtered by search and capabilities."""

        search_serializer = ExploreSearchSerializer(
            data=request.query_params
        )
        search_serializer.is_valid(raise_exception=True)
        filters = search_serializer.validated_data

        models = list(
            ModelRegistry.objects.filter(active=True).order_by(
                "priority",
                "name",
                "id",
            )
        )

        query = filters.get("query", "").casefold()
        category = filters.get("category")
        capability = filters.get("capability")

        supports_vision = filters.get("supports_vision")
        supports_streaming = filters.get("supports_streaming")
        supports_tools = filters.get("supports_tools")

        results = []

        for model in models:
            capabilities = model.capabilities or []

            # Ignore malformed capability metadata rather than exposing
            # unexpected values or crashing the listing.
            if not isinstance(capabilities, list):
                capabilities = []

            normalized_capabilities = {
                item.casefold()
                for item in capabilities
                if isinstance(item, str)
            }

            # Search only public model information.
            if query:
                searchable_text = " ".join(
                    [
                        model.name or "",
                        model.provider or "",
                        model.model_id or "",
                        " ".join(sorted(normalized_capabilities)),
                    ]
                ).casefold()

                if query not in searchable_text:
                    continue

            # Filter by model task category.
            if category:
                if category == "general":
                    matches_category = bool(
                        {"general", "chat"} & normalized_capabilities
                    )
                elif category == "other":
                    known_categories = {
                        "general",
                        "chat",
                        "coding",
                        "research",
                        "reasoning",
                        "writing",
                        "vision",
                    }
                    matches_category = not bool(
                        known_categories & normalized_capabilities
                    )
                else:
                    matches_category = category in normalized_capabilities

                if not matches_category:
                    continue

            # Capability filters map to explicit model fields where possible.
            if capability == "chat":
                if not (
                    {"chat", "general"} & normalized_capabilities
                ):
                    continue

            elif capability == "coding":
                if "coding" not in normalized_capabilities:
                    continue

            elif capability == "reasoning":
                if "reasoning" not in normalized_capabilities:
                    continue

            elif capability == "research":
                if "research" not in normalized_capabilities:
                    continue

            elif capability == "vision":
                if not (
                    model.supports_vision
                    or "vision" in normalized_capabilities
                ):
                    continue

            elif capability == "tools":
                if not (
                    model.supports_tools
                    or "tools" in normalized_capabilities
                ):
                    continue

            elif capability == "streaming":
                if not model.supports_streaming:
                    continue

            if (
                supports_vision is not None
                and model.supports_vision != supports_vision
            ):
                continue

            if (
                supports_streaming is not None
                and model.supports_streaming != supports_streaming
            ):
                continue

            if (
                supports_tools is not None
                and model.supports_tools != supports_tools
            ):
                continue

            results.append(model)

        response_serializer = ExploreModelSerializer(
            results,
            many=True,
        )

        return Response({
            "count": len(results),
            "results": response_serializer.data,
        })


class ExploreProvidersView(APIView):
    """List providers represented by active model registry entries."""

    permission_classes = [AllowAny]

    def get(self, request):
        """Aggregate model counts and capabilities per provider."""

        models = ModelRegistry.objects.filter(active=True).order_by(
            "provider",
            "name",
        )

        provider_data = {}

        for model in models:
            provider_name = model.provider

            if provider_name not in provider_data:
                provider_data[provider_name] = {
                    "provider": provider_name,
                    "model_count": 0,
                    "capabilities": set(),
                }

            provider_data[provider_name]["model_count"] += 1

            capabilities = model.capabilities or []

            if isinstance(capabilities, list):
                provider_data[provider_name]["capabilities"].update(
                    capability
                    for capability in capabilities
                    if isinstance(capability, str)
                )

            if model.supports_vision:
                provider_data[provider_name]["capabilities"].add("vision")

            if model.supports_streaming:
                provider_data[provider_name]["capabilities"].add("streaming")

            if model.supports_tools:
                provider_data[provider_name]["capabilities"].add("tools")

        results = [
            {
                "provider": item["provider"],
                "model_count": item["model_count"],
                "capabilities": sorted(item["capabilities"]),
            }
            for item in provider_data.values()
        ]

        response_serializer = ExploreProviderSerializer(
            results,
            many=True,
        )

        return Response({
            "count": len(results),
            "results": response_serializer.data,
        })


class ExploreFeaturesView(APIView):
    """Return Explore feature cards and their current integration status."""

    permission_classes = [AllowAny]

    def get(self, request):
        """Describe features without claiming unfinished integrations work."""

        active_models_exist = ModelRegistry.objects.filter(
            active=True
        ).exists()

        features = [
            {
                "slug": "model-explorer",
                "title": "Explore AI Models",
                "description": (
                    "Discover active models and filter them by capabilities."
                ),
                "category": "discovery",
                "available": True,
            },
            {
                "slug": "ai-chat",
                "title": "AI Chat",
                "description": (
                    "Chat integration availability depends on configured "
                    "models and provider credentials."
                ),
                "category": "assistant",
                "available": active_models_exist,
            },
            {
                "slug": "knowledge-search",
                "title": "Knowledge Search",
                "description": (
                    "Search uploaded documents using semantic retrieval."
                ),
                "category": "knowledge",
                "available": False,
            },
            {
                "slug": "image-generation",
                "title": "Image Generation",
                "description": (
                    "Generate and store images using a configured provider."
                ),
                "category": "images",
                "available": False,
            },
            {
                "slug": "web-search",
                "title": "Web Search",
                "description": (
                    "Search the web as part of an assistant response."
                ),
                "category": "research",
                "available": False,
            },
        ]

        serializer = ExploreFeatureSerializer(
            features,
            many=True,
        )

        return Response({
            "count": len(features),
            "results": serializer.data,
        })

