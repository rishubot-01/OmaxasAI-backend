"""Search services for OmaxasAI conversations and messages."""

from django.db.models import Q

from apps.conversations.models import Conversation, Message


class ConversationSearchError(Exception):
    """Raised when a conversation search request is invalid."""


def _validate_search(
    *,
    user,
    query: str,
    limit: int,
) -> str:
    """Validate authentication, search text, and result limit."""

    if not getattr(user, "is_authenticated", False):
        raise ConversationSearchError("Authentication is required.")

    if not isinstance(query, str):
        raise ConversationSearchError("Search query must be text.")

    query = query.strip()

    if not query:
        raise ConversationSearchError("Search query cannot be empty.")

    if len(query) > 200:
        raise ConversationSearchError(
            "Search query cannot exceed 200 characters."
        )

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ConversationSearchError("Limit must be an integer.")

    if not 1 <= limit <= 100:
        raise ConversationSearchError("Limit must be between 1 and 100.")

    return query


def search_conversations(
    *,
    user,
    query: str,
    limit: int = 20,
) -> list[Conversation]:
    """
    Search the current user's conversations by title or message content.

    Only conversations belonging to the authenticated user are returned.
    Results are ordered by most recently updated.
    """

    query = _validate_search(
        user=user,
        query=query,
        limit=limit,
    )

    matching_message_conversations = (
        Message.objects.filter(
            conversation__user=user,
            content__icontains=query,
        )
        .values("conversation_id")
    )

    conversations = (
        Conversation.objects.filter(user=user)
        .filter(
            Q(title__icontains=query)
            | Q(pk__in=matching_message_conversations)
        )
        .distinct()
        .order_by("-updated_at", "-id")
    )

    return list(conversations[:limit])


def search_messages(
    *,
    user,
    query: str,
    limit: int = 20,
) -> list[Message]:
    """
    Search messages across the current user's conversations.

    The result includes the related conversation for convenient display.
    Messages from other users' conversations are never returned.
    """

    query = _validate_search(
        user=user,
        query=query,
        limit=limit,
    )

    messages = (
        Message.objects.filter(
            conversation__user=user,
            content__icontains=query,
        )
        .select_related("conversation")
        .order_by("-created_at", "-id")
    )

    return list(messages[:limit])
