"""
Views for OmaxasAI conversations.

Provides user-owned chat sessions, message history,
AI response generation, and message feedback.
"""

import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assistant.models import ModelRegistry
from apps.assistant.serializers import AssistantPromptSerializer
from apps.assistant.services.ai_service import (
    AIServiceConfigurationError,
    AIServiceError,
    generate_reply,
)

from .models import Conversation, Feedback, FileAttachment, Message
from .serializers import (
    ConversationSerializer,
    FeedbackSerializer,
    FileAttachmentSerializer,
    MessageSerializer,
)


logger = logging.getLogger(__name__)


def _normalize_registry_id(value):
    """
    Normalize a registry ID to a positive integer.

    Returns None for missing or invalid IDs.
    Boolean values are rejected because bool is a subclass of int.
    """

    if value is None or isinstance(value, bool):
        return None

    try:
        registry_id = int(value)
    except (TypeError, ValueError, OverflowError):
        return None

    return registry_id if registry_id > 0 else None


class ConversationListCreateView(generics.ListCreateAPIView):
    """
    List the authenticated user's recent conversations
    or create a new conversation.

    GET  /api/conversations/
    POST /api/conversations/
    """

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = (
            Conversation.objects.filter(user=self.request.user)
            .order_by("-updated_at")
        )

        search_query = self.request.query_params.get(
            "search",
            "",
        ).strip()

        if search_query:
            queryset = queryset.filter(
                title__icontains=search_query
            )

        return queryset

    def perform_create(self, serializer):
        # Conversation ownership is always assigned by the backend.
        serializer.save(user=self.request.user)


class ConversationDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, rename, or delete a user's conversation.

    GET    /api/conversations/<pk>/
    PATCH  /api/conversations/<pk>/
    DELETE /api/conversations/<pk>/
    """

    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Conversation.objects.filter(
            user=self.request.user
        )


class MessageListView(generics.ListAPIView):
    """
    List messages from a conversation owned by the current user.

    GET /api/conversations/<conversation_id>/messages/
    """

    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs["conversation_id"]

        conversation = get_object_or_404(
            Conversation,
            pk=conversation_id,
            user=self.request.user,
        )

        return (
            Message.objects.filter(conversation=conversation)
            .order_by("created_at", "pk")
        )


class SendMessageView(APIView):
    """
    Save a user message and request an AI response.

    POST /api/conversations/<conversation_id>/messages/send/

    Uses the AI service's timeout and model-fallback logic.
    The response is non-streaming.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        conversation = get_object_or_404(
            Conversation,
            pk=conversation_id,
            user=request.user,
        )

        # Streaming is not implemented on this endpoint.
        requested_stream = request.data.get(
            "stream",
            False,
        )

        if str(requested_stream).strip().lower() in {
            "true",
            "1",
            "yes",
            "on",
        }:
            return Response(
                {
                    "detail": (
                        "Streaming is not available yet. "
                        "Send the request with stream=false."
                    )
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        incoming_data = request.data.copy()
        incoming_data["stream"] = False

        prompt_serializer = AssistantPromptSerializer(
            data=incoming_data
        )
        prompt_serializer.is_valid(raise_exception=True)

        prompt = prompt_serializer.validated_data

        message_text = prompt["message"]
        mode = prompt["mode"]
        web_search = prompt["web_search"]
        selected_model_id = prompt.get("selected_model_id")

        # Persist the user's message before generating an AI response.
        user_message = Message.objects.create(
            conversation=conversation,
            role=Message.RoleChoices.USER,
            content=message_text,
            mode=mode,
            web_search_used=web_search,
        )

        # Give a new conversation a useful title.
        if conversation.title == "New chat":
            conversation.title = message_text[:80]

        conversation.updated_at = timezone.now()
        conversation.save(
            update_fields=["title", "updated_at"]
        )

        try:
            result = generate_reply(
                message=message_text,
                mode=mode,
                web_search=web_search,
                user=request.user,
                selected_model_id=selected_model_id,
            )

        except AIServiceConfigurationError:
            logger.warning(
                "AI service configuration unavailable. "
                "user_id=%s conversation_id=%s selected_model_id=%s",
                request.user.pk,
                conversation.pk,
                selected_model_id,
            )

            return Response(
                {
                    "detail": (
                        "The selected AI model is not configured "
                        "correctly or its provider credentials are missing. "
                        "Your message has been saved."
                    ),
                    "conversation_id": conversation.pk,
                    "user_message_id": user_message.pk,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        except AIServiceError:
            logger.warning(
                "AI generation failed. user_id=%s "
                "conversation_id=%s selected_model_id=%s",
                request.user.pk,
                conversation.pk,
                selected_model_id,
                exc_info=True,
            )

            return Response(
                {
                    "detail": (
                        "OmaxasAI could not generate a response right now. "
                        "Your message has been saved."
                    ),
                    "conversation_id": conversation.pk,
                    "user_message_id": user_message.pk,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        except Exception:
            logger.exception(
                "Unexpected AI generation error. "
                "user_id=%s conversation_id=%s",
                request.user.pk,
                conversation.pk,
            )

            return Response(
                {
                    "detail": (
                        "An unexpected error occurred while generating "
                        "the response. Your message has been saved."
                    ),
                    "conversation_id": conversation.pk,
                    "user_message_id": user_message.pk,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Normalize supported AI service response types.
        if isinstance(result, str):
            answer = result.strip()
            metadata = {}

        elif isinstance(result, dict):
            answer = result.get("reply", "")
            metadata = result

        else:
            answer = ""
            metadata = {}

        if not isinstance(answer, str) or not answer.strip():
            logger.error(
                "AI service returned an empty or invalid response. "
                "conversation_id=%s",
                conversation.pk,
            )

            return Response(
                {
                    "detail": (
                        "OmaxasAI returned an invalid response. "
                        "Your message has been saved."
                    ),
                    "conversation_id": conversation.pk,
                    "user_message_id": user_message.pk,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        answer = answer.strip()

        actual_provider = str(
            metadata.get("provider", "")
        ).strip()[:50]

        actual_model = str(
            metadata.get("model", "")
        ).strip()[:255]

        actual_registry_id = metadata.get("model_registry_id")

        fallback_used = metadata.get("fallback_used") is True

        requested_registry_id = _normalize_registry_id(
            selected_model_id
        )

        actual_registry_id_int = _normalize_registry_id(
            actual_registry_id
        )

        # Verify selected-model requests against the model actually used.
        #
        # A different model is allowed only when generate_reply()
        # explicitly reports that a fallback succeeded.
        if selected_model_id is not None:
            if requested_registry_id is None:
                logger.error(
                    "Invalid selected model ID. conversation_id=%s",
                    conversation.pk,
                )

                return Response(
                    {
                        "detail": (
                            "The selected model ID is invalid. "
                            "Your message has been saved."
                        ),
                        "conversation_id": conversation.pk,
                        "user_message_id": user_message.pk,
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            # Verify that the reported actual registry ID exists.
            actual_model_exists = (
                actual_registry_id_int is not None
                and ModelRegistry.objects.filter(
                    pk=actual_registry_id_int
                ).exists()
            )

            if not actual_model_exists:
                logger.error(
                    "AI service returned an invalid registry ID. "
                    "conversation_id=%s selected_model_id=%s "
                    "actual_registry_id=%s fallback_used=%s",
                    conversation.pk,
                    requested_registry_id,
                    actual_registry_id,
                    fallback_used,
                )

                return Response(
                    {
                        "detail": (
                            "The AI model could not be verified. "
                            "Your message has been saved."
                        ),
                        "conversation_id": conversation.pk,
                        "user_message_id": user_message.pk,
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            selected_model_matches = (
                actual_registry_id_int == requested_registry_id
            )

            if not selected_model_matches and not fallback_used:
                logger.error(
                    "Selected model verification failed. "
                    "conversation_id=%s selected_model_id=%s "
                    "actual_registry_id=%s fallback_used=%s",
                    conversation.pk,
                    requested_registry_id,
                    actual_registry_id_int,
                    fallback_used,
                )

                return Response(
                    {
                        "detail": (
                            "The selected model could not be verified. "
                            "Your message has been saved."
                        ),
                        "conversation_id": conversation.pk,
                        "user_message_id": user_message.pk,
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

            if fallback_used and not selected_model_matches:
                logger.info(
                    "Selected model failed; fallback model succeeded. "
                    "conversation_id=%s requested_model_id=%s "
                    "actual_model_id=%s",
                    conversation.pk,
                    requested_registry_id,
                    actual_registry_id_int,
                )

        # Save the assistant response and the actual model metadata.
        assistant_message = Message.objects.create(
            conversation=conversation,
            role=Message.RoleChoices.ASSISTANT,
            content=answer,
            mode=mode,
            provider=actual_provider,
            model_name=actual_model,
            web_search_used=bool(
                metadata.get("web_search_used", False)
            ),
            metadata={
                "task_category": metadata.get(
                    "category",
                    "general",
                ),
                "fallback_used": fallback_used,
                "requested_model_registry_id": metadata.get(
                    "requested_model_registry_id",
                    requested_registry_id,
                ),
                "fallback_from_registry_id": metadata.get(
                    "fallback_from_registry_id"
                ),
                "input_tokens": metadata.get("input_tokens"),
                "output_tokens": metadata.get("output_tokens"),
                "response_time_ms": metadata.get(
                    "response_time_ms"
                ),
                "model_registry_id": actual_registry_id,
            },
        )

        conversation.updated_at = timezone.now()
        conversation.save(
            update_fields=["updated_at"]
        )

        return Response(
            {
                "conversation_id": conversation.pk,
                "user_message": MessageSerializer(
                    user_message
                ).data,
                "assistant_message": MessageSerializer(
                    assistant_message
                ).data,
            },
            status=status.HTTP_200_OK,
        )


class ConversationAttachmentListView(generics.ListAPIView):
    """
    List attachment metadata for a conversation owned by the user.

    File uploading and secure cloud-storage integration are
    separate tasks; this endpoint does not upload files.
    """

    serializer_class = FileAttachmentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation = get_object_or_404(
            Conversation,
            pk=self.kwargs["conversation_id"],
            user=self.request.user,
        )

        return FileAttachment.objects.filter(
            conversation=conversation
        ).order_by("-created_at")


class FeedbackListCreateView(generics.ListCreateAPIView):
    """
    List the user's feedback or submit feedback for an assistant
    message belonging to one of their conversations.
    """

    serializer_class = FeedbackSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            Feedback.objects.filter(user=self.request.user)
            .select_related("message", "message__conversation")
            .order_by("-created_at")
        )

    def perform_create(self, serializer):
        message = serializer.validated_data["message"]

        if message.role != Message.RoleChoices.ASSISTANT:
            raise ValidationError(
                {
                    "message": (
                        "Feedback can only be left on an AI response."
                    )
                }
            )

        already_exists = Feedback.objects.filter(
            user=self.request.user,
            message=message,
        ).exists()

        if already_exists:
            raise ValidationError(
                {
                    "message": (
                        "You have already submitted feedback "
                        "for this answer."
                    )
                }
            )

        serializer.save(user=self.request.user)