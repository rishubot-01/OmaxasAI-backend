
"""Business logic for sending messages in OmaxasAI conversations."""

from typing import Any

from django.utils import timezone

from apps.assistant.services.ai_service import generate_reply
from apps.conversations.models import Conversation, Message


class ChatServiceError(Exception):
    """Raised when a chat operation cannot be completed."""


def _extract_reply(result: Any) -> tuple[str, dict]:
    """Extract assistant text and safe metadata from an AI service result."""

    if isinstance(result, str):
        reply_text = result.strip()
        metadata = {}
    elif isinstance(result, dict):
        reply_text = (
            result.get("text")
            or result.get("content")
            or result.get("reply")
            or result.get("answer")
            or ""
        )
        reply_text = str(reply_text).strip()
        metadata = {
            key: result[key]
            for key in (
                "category",
                "fallback_used",
                "response_time_ms",
                "input_tokens",
                "output_tokens",
            )
            if key in result
        }
    else:
        raise ChatServiceError("The AI service returned an unsupported response.")

    if not reply_text:
        raise ChatServiceError("The AI service returned an empty response.")

    return reply_text, metadata


def send_chat_message(
    *,
    user,
    conversation: Conversation,
    content: str,
    mode: str = "auto",
    web_search: bool = False,
) -> tuple[Message, Message]:
    """
    Save a user's message, generate an AI response, and save the response.

    Returns:
        A tuple containing (user_message, assistant_message).

    Note:
        The user's message is saved before calling the AI provider. If the
        provider fails, the original message remains available for retry.
    """

    if not getattr(user, "is_authenticated", False):
        raise ChatServiceError("Authentication is required.")

    if not isinstance(conversation, Conversation):
        raise ChatServiceError("A valid conversation is required.")

    if conversation.user_id != user.pk:
        raise ChatServiceError(
            "You do not have permission to access this conversation."
        )

    clean_content = (content or "").strip()

    if not clean_content:
        raise ChatServiceError("Message content cannot be empty.")

    if len(clean_content) > 50000:
        raise ChatServiceError("Message content cannot exceed 50000 characters.")

    if mode not in {"auto", "think"}:
        raise ChatServiceError("Mode must be either 'auto' or 'think'.")

    if not isinstance(web_search, bool):
        raise ChatServiceError("web_search must be a boolean value.")

    # Save the user's message first.
    user_message = Message.objects.create(
        conversation=conversation,
        role="user",
        content=clean_content,
        mode=mode,
        web_search_used=False,
    )

    # Give a new conversation a useful title based on its first message.
    if conversation.title == "New chat":
        title = clean_content.replace("\n", " ").strip()[:80]
        Conversation.objects.filter(
            pk=conversation.pk,
            user=user,
            title="New chat",
        ).update(title=title)

    Conversation.objects.filter(
        pk=conversation.pk,
        user=user,
    ).update(updated_at=timezone.now())

    # Generate a response through the existing AI service.
    result = generate_reply(
        message=clean_content,
        mode=mode,
        web_search=web_search,
        user=user,
    )

    reply_text, metadata = _extract_reply(result)

    if isinstance(result, dict):
        provider = result.get("provider", "")
        model_name = result.get("model_name") or result.get("model", "")
        web_search_used = bool(result.get("web_search_used", False))
    else:
        provider = ""
        model_name = ""
        web_search_used = False

    # Save the assistant's reply.
    assistant_message = Message.objects.create(
        conversation=conversation,
        role="assistant",
        content=reply_text,
        mode=mode,
        provider=str(provider or "")[:100],
        model_name=str(model_name or "")[:200],
        web_search_used=web_search_used,
        metadata=metadata,
    )

    Conversation.objects.filter(
        pk=conversation.pk,
        user=user,
    ).update(updated_at=timezone.now())

    return user_message, assistant_message

