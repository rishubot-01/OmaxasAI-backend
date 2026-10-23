
"""Serializers for the OmaxasAI Explore application."""

from rest_framework import serializers

from apps.assistant.models import ModelRegistry


class ExploreSearchSerializer(serializers.Serializer):
    """Validate search and capability filters for Explore."""

    query = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
        trim_whitespace=True,
    )

    category = serializers.ChoiceField(
        required=False,
        choices=[
            ("general", "General"),
            ("coding", "Coding"),
            ("research", "Research"),
            ("reasoning", "Reasoning"),
            ("writing", "Writing"),
            ("vision", "Vision"),
            ("other", "Other"),
        ],
    )

    capability = serializers.ChoiceField(
        required=False,
        choices=[
            ("chat", "Chat"),
            ("coding", "Coding"),
            ("reasoning", "Reasoning"),
            ("research", "Research"),
            ("vision", "Vision"),
            ("tools", "Tool use"),
            ("streaming", "Streaming"),
        ],
    )

    supports_vision = serializers.BooleanField(required=False)
    supports_streaming = serializers.BooleanField(required=False)
    supports_tools = serializers.BooleanField(required=False)

    def validate_query(self, value):
        """Normalize the optional search phrase."""

        return value.strip()


class ExploreModelSerializer(serializers.ModelSerializer):
    """Expose safe, public information about an available AI model."""

    class Meta:
        model = ModelRegistry
        fields = [
            "id",
            "name",
            "provider",
            "model_id",
            "backend_type",
            "capabilities",
            "context_window",
            "supports_streaming",
            "supports_vision",
            "supports_tools",
        ]
        read_only_fields = fields


class ExploreProviderSerializer(serializers.Serializer):
    """Represent a provider and its available model count."""

    provider = serializers.CharField(read_only=True)
    model_count = serializers.IntegerField(read_only=True)
    capabilities = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
    )


class ExploreFeatureSerializer(serializers.Serializer):
    """Represent a static Explore feature card."""

    slug = serializers.SlugField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    category = serializers.CharField(read_only=True)
    available = serializers.BooleanField(read_only=True)

