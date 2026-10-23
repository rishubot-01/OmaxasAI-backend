
"""Conversation history retrieval and formatting services."""

from typing import Any

from apps.conversations.models import Conversation, Message


class ConversationHistoryError(Exception):
    """Raised when conversation history cannot be retrieved."""


def _get_owned_conversation(*, user: Any, conversation_id: int) -> Conversation:
    """Return a conversation only when it belongs to the requesting user."""

    if not getattr(user, "is_authenticated", False):
        raise ConversationHistoryError("Authentication is required.")

    try:
        conversation = Conversation.objects.get(
            pk=conversation_id,
            user=user,
        )
    except (Conversation.DoesNotExist, TypeError, ValueError):
        raise ConversationHistoryError(
            "Conversation not found or access denied."
        ) from None

    return conversation


def get_recent_messages(
    *,
    user: Any,
    conversation_id: int,
    limit: int = 20,
) -> list[Message]:
    """
    Retrieve recent messages in chronological order.

    The conversation must belong to the requesting user.
    The limit is restricted to 1–100 messages.
    """

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError("limit must be an integer.")

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100.")

    conversation = _get_owned_conversation(
        user=user,
        conversation_id=conversation_id,
    )

    # Fetch newest messages first to apply the limit efficiently.
    recent_messages = list(
        Message.objects.filter(conversation=conversation)
        .order_by("-created_at", "-id")[:limit]
    )

    # Restore chronological order for the AI prompt and chat interface.
    recent_messages.reverse()

    return recent_messages


def format_history_for_prompt(
    *,
    user: Any,
    conversation_id: int,
    limit: int = 20,
    exclude_message_id: int | None = None,
) -> list[dict[str, str]]:
    """
    Format conversation history for an AI provider.

    Only user and assistant message content is included.
    Database IDs, internal metadata, and provider details are excluded.
    """

    messages = get_recent_messages(
        user=user,
        conversation_id=conversation_id,
        limit=limit,
    )

    history: list[dict[str, str]] = []

    for message in messages:
        if exclude_message_id is not None and message.pk == exclude_message_id:
            continue

        if message.role not in {"user", "assistant"}:
            continue

        content = (message.content or "").strip()

        if not content:
            continue

        history.append(
            {
                "role": message.role,
                "content": content,
            }
        )

    return history


def get_conversation_history(
    *,
    user: Any,
    conversation_id: int,
    limit: int = 20,
) -> dict:
    """
    Return conversation details and recent messages for the chat interface.
    """

    conversation = _get_owned_conversation(
        user=user,
        conversation_id=conversation_id,
    )

    messages = get_recent_messages(
        user=user,
        conversation_id=conversation_id,
        limit=limit,
    )

    return {
        "conversation": {
            "id": conversation.pk,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "is_archived": conversation.is_archived,
        },
        "messages": [
            {
                "id": message.pk,
                "role": message.role,
                "content": message.content,
                "mode": message.mode,
                "provider": message.provider,
                "model_name": message.model_name,
                "web_search_used": message.web_search_used,
                "created_at": message.created_at,
            }
            for message in messages
        ],
    }

