
from rest_framework import serializers

from .models import AIRequest, EvaluationResult, ModelRegistry


COMING_SOON_STATUSES = {
    "coming soon",
    "coming_soon",
    "not_available",
}


def get_model_availability_status(model):
    """
    Determine availability for an individual registered model.

    Provider names alone never make a model Coming Soon.
    Availability is controlled by the model's configuration.
    """

    if not model.active:
        return "disabled"

    config = (
        model.config
        if isinstance(model.config, dict)
        else {}
    )

    configured_status = str(
        config.get("status", "")
    ).strip().lower()

    is_coming_soon = (
        config.get("coming_soon") is True
        or configured_status in COMING_SOON_STATUSES
    )

    if is_coming_soon:
        return "coming_soon"

    return "available"


class AssistantPromptSerializer(serializers.Serializer):
    """
    Validates prompts sent to OmaxasAI.

    selected_model_id is optional. When provided, it must refer
    to an active model that is not marked Coming Soon.
    """

    message = serializers.CharField(
        max_length=50000,
        trim_whitespace=True,
    )

    mode = serializers.ChoiceField(
        choices=AIRequest.ModeChoices.choices,
        default=AIRequest.ModeChoices.AUTO,
    )

    web_search = serializers.BooleanField(
        default=False,
    )

    stream = serializers.BooleanField(
        default=True,
    )

    conversation_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )

    selected_model_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
    )

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "Message cannot be empty."
            )

        return value.strip()

    def validate_selected_model_id(self, value):
        """
        Validate the selected model's database ID.

        Any provider can be selected when its model is active
        and is not marked Coming Soon in its configuration.
        """

        if value is None:
            return value

        model = ModelRegistry.objects.filter(
            pk=value,
            active=True,
        ).first()

        if model is None:
            raise serializers.ValidationError(
                "The selected model does not exist or is not active."
            )

        availability = get_model_availability_status(model)

        if availability == "coming_soon":
            raise serializers.ValidationError(
                f"{model.name} is marked as Coming Soon."
            )

        return value


class ModelRegistrySerializer(serializers.ModelSerializer):
    """
    Exposes safe model information to the application.

    Provider credentials, credential variable names and private
    endpoint configuration are never exposed.
    """

    availability_status = serializers.SerializerMethodField()

    is_available_for_inference = serializers.SerializerMethodField()

    class Meta:
        model = ModelRegistry

        fields = (
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
            "active",
            "availability_status",
            "is_available_for_inference",
        )

        read_only_fields = fields

    def get_availability_status(self, obj):
        return get_model_availability_status(obj)

    def get_is_available_for_inference(self, obj):
        return (
            get_model_availability_status(obj) == "available"
        )


class AIRequestSerializer(serializers.ModelSerializer):
    """
    Read-only representation of AI request usage and status.
    Monetary cost is deliberately not tracked.
    """

    class Meta:
        model = AIRequest

        fields = (
            "request_id",
            "user",
            "selected_model",
            "provider",
            "model_name",
            "task_category",
            "requested_mode",
            "web_search_used",
            "fallback_used",
            "status",
            "input_tokens",
            "output_tokens",
            "response_time_ms",
            "error_code",
            "created_at",
            "completed_at",
        )

        read_only_fields = fields


class EvaluationResultSerializer(serializers.ModelSerializer):
    """
    Read-only representation of AI model evaluation results.
    """

    model_name = serializers.CharField(
        source="model.name",
        read_only=True,
    )

    class Meta:
        model = EvaluationResult

        fields = (
            "id",
            "model",
            "model_name",
            "benchmark_name",
            "task_category",
            "score",
            "passed",
            "latency_ms",
            "input_tokens",
            "output_tokens",
            "result_summary",
            "evaluated_at",
        )

        read_only_fields = fields

    def validate_score(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError(
                "Score must be between 0 and 100."
            )

        return value
