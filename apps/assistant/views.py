import logging
from time import perf_counter

from django.utils import timezone

from rest_framework import generics, status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from .models import AIRequest, ModelRegistry
from .serializers import (
    AIRequestSerializer,
    AssistantPromptSerializer,
    ModelRegistrySerializer,
)
from .services.ai_service import (
    AIServiceConfigurationError,
    AIServiceError,
    generate_reply,
)
from .throttles import GuestAIThrottle


logger = logging.getLogger(__name__)


class AvailableModelsView(generics.ListAPIView):
    """
    List active registered models for authenticated users.

    Provider credentials and private configuration are not exposed.
    """

    serializer_class = ModelRegistrySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ModelRegistry.objects.filter(
            active=True,
        ).order_by("priority", "name")


class AIRequestHistoryView(generics.ListAPIView):
    """Return only the authenticated user's AI request history."""

    serializer_class = AIRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            AIRequest.objects.filter(user=self.request.user)
            .select_related("selected_model")
            .order_by("-created_at")
        )


def _safe_token_count(value):
    """Return a non-negative token count, or None if unavailable."""

    if value is None:
        return None

    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return count if count >= 0 else None


def _get_used_model(metadata, requested_model_id=None):
    """
    Resolve the registry record for the model that generated the reply.

    Prefer the service's exact registry ID, then match provider/model.
    """

    registry_id = metadata.get("model_registry_id")

    if registry_id is not None:
        model = ModelRegistry.objects.filter(
            pk=registry_id,
            active=True,
        ).first()

        if model:
            return model

    provider = str(metadata.get("provider", "")).strip().lower()
    model_name = str(metadata.get("model", "")).strip()

    if provider and model_name:
        model = ModelRegistry.objects.filter(
            provider__iexact=provider,
            model_id=model_name,
            active=True,
        ).first()

        if model:
            return model

    # Do not claim the requested model was used merely because it
    # was selected. The provider returned by the service must match.
    if requested_model_id is not None and provider:
        requested_model = ModelRegistry.objects.filter(
            pk=requested_model_id,
            active=True,
        ).first()

        if (
            requested_model
            and requested_model.provider.strip().lower() == provider
        ):
            return requested_model

    return None


def _mark_request_failed(ai_request, start_time, error_code):
    """Store failure status and response time."""

    ai_request.status = AIRequest.StatusChoices.FAILED
    ai_request.error_code = error_code
    ai_request.response_time_ms = max(
        0,
        int((perf_counter() - start_time) * 1000),
    )
    ai_request.completed_at = timezone.now()

    ai_request.save(
        update_fields=[
            "status",
            "error_code",
            "response_time_ms",
            "completed_at",
        ]
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([GuestAIThrottle])
def generate_response(request):
    """
    Generate an AI response and record safe operational metadata.

    Guest requests:
    - Do not require authentication.
    - Are recorded with user=None.
    - Use automatic model routing.

    Authenticated requests:
    - May select an active registered model using selected_model_id.
    - Are associated with the authenticated user.

    Web Search still requires a configured, real integration.
    """

    serializer = AssistantPromptSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    # An anonymous request must never be associated with an account.
    authenticated_user = (
        request.user
        if request.user.is_authenticated
        else None
    )

    requested_model_id = data.get("selected_model_id")

    # Guests use automatic routing. They cannot force a model by
    # submitting a registry database ID.
    if authenticated_user is None:
        requested_model_id = None

    # Validate an explicitly selected model for authenticated users.
    requested_model = None

    if requested_model_id is not None:
        requested_model = ModelRegistry.objects.filter(
            pk=requested_model_id,
            active=True,
        ).first()

        if requested_model is None:
            raise ValidationError({
                "selected_model_id": (
                    "The selected model does not exist or is inactive."
                )
            })

    # AIRequest.user permits NULL, so a guest request can be recorded
    # without creating a user account.
    ai_request = AIRequest.objects.create(
        user=authenticated_user,
        requested_mode=data["mode"],
        status=AIRequest.StatusChoices.PROCESSING,
    )

    start_time = perf_counter()

    try:
        result = generate_reply(
            message=data["message"],
            mode=data["mode"],
            web_search=data["web_search"],
            user=authenticated_user,
            selected_model_id=requested_model_id,
        )

        if isinstance(result, str):
            answer = result.strip()
            metadata = {}

        elif isinstance(result, dict):
            answer = result.get("reply", "")
            metadata = result

        else:
            raise AIServiceError(
                "AI service returned an invalid response."
            )

        if not isinstance(answer, str) or not answer.strip():
            raise AIServiceError(
                "AI service returned an empty response."
            )

        provider = str(
            metadata.get("provider", "")
        ).strip()[:50]

        model_name = str(
            metadata.get("model", "")
        ).strip()[:255]

        # A manually selected model must not silently be reported as
        # successful if the service returns a different provider.
        if requested_model_id is not None:
            if not provider:
                raise AIServiceError(
                    "The AI service did not report the actual provider."
                )

            if provider.lower() != requested_model.provider.lower():
                raise AIServiceError(
                    "The AI service used a different provider "
                    "than requested."
                )

            if metadata.get("fallback_used", False):
                raise AIServiceError(
                    "Fallback occurred for an explicitly selected model."
                )

        category = metadata.get(
            "category",
            AIRequest.TaskCategory.GENERAL,
        )

        valid_categories = {
            choice.value for choice in AIRequest.TaskCategory
        }

        if category not in valid_categories:
            category = AIRequest.TaskCategory.OTHER

        selected_model = _get_used_model(
            metadata,
            requested_model_id=requested_model_id,
        )

        # Verify the model used for authenticated explicit selections.
        if requested_model_id is not None and selected_model is None:
            raise AIServiceError(
                "Could not verify the model used for this response."
            )

        elapsed_ms = max(
            0,
            int((perf_counter() - start_time) * 1000),
        )

        ai_request.selected_model = selected_model
        ai_request.provider = provider
        ai_request.model_name = model_name
        ai_request.task_category = category
        ai_request.web_search_used = bool(
            metadata.get("web_search_used", False)
        )
        ai_request.fallback_used = bool(
            metadata.get("fallback_used", False)
        )
        ai_request.input_tokens = _safe_token_count(
            metadata.get("input_tokens")
        )
        ai_request.output_tokens = _safe_token_count(
            metadata.get("output_tokens")
        )
        ai_request.response_time_ms = elapsed_ms
        ai_request.status = AIRequest.StatusChoices.SUCCEEDED
        ai_request.completed_at = timezone.now()
        ai_request.save()

        return Response(
            {
                "request_id": str(ai_request.request_id),
                "reply": answer,
                "mode": ai_request.requested_mode,
                "task_category": ai_request.task_category,
                "provider": ai_request.provider,
                "model": ai_request.model_name,
                "selected_model_id": (
                    selected_model.pk
                    if selected_model is not None
                    else None
                ),
                "web_search_used": ai_request.web_search_used,
                "fallback_used": ai_request.fallback_used,
                "usage": {
                    "input_tokens": ai_request.input_tokens,
                    "output_tokens": ai_request.output_tokens,
                },
                "response_time_ms": ai_request.response_time_ms,
            },
            status=status.HTTP_200_OK,
        )

    except AIServiceConfigurationError:
        logger.warning(
            "AI provider configuration unavailable. request_id=%s",
            ai_request.request_id,
        )

        _mark_request_failed(
            ai_request,
            start_time,
            "AI_CONFIGURATION_UNAVAILABLE",
        )

        return Response(
            {
                "detail": (
                    "The selected AI model is not configured correctly "
                    "or its provider credentials are missing. "
                    "Check that an available model is configured."
                ),
                "request_id": str(ai_request.request_id),
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    except AIServiceError as exc:
        logger.warning(
            "AI generation failed. request_id=%s error_type=%s",
            ai_request.request_id,
            type(exc).__name__,
        )

        _mark_request_failed(
            ai_request,
            start_time,
            "AI_GENERATION_FAILED",
        )

        return Response(
            {
                "detail": "OmaxasAI could not generate a response.",
                "request_id": str(ai_request.request_id),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    except Exception:
        logger.exception(
            "Unexpected AI generation error. request_id=%s",
            ai_request.request_id,
        )

        _mark_request_failed(
            ai_request,
            start_time,
            "AI_GENERATION_FAILED",
        )

        return Response(
            {
                "detail": (
                    "An unexpected error occurred during AI generation."
                ),
                "request_id": str(ai_request.request_id),
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )