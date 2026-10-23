
"""
URL routes for OmaxasAI conversations.
"""

from django.urls import path

from .views import (
    ConversationAttachmentListView,
    ConversationDetailView,
    ConversationListCreateView,
    FeedbackListCreateView,
    MessageListView,
    SendMessageView,
)


app_name = "conversations"

urlpatterns = [
    # New Chat and Recents
    path(
        "",
        ConversationListCreateView.as_view(),
        name="conversation-list-create",
    ),

    # Search recent chats through the ?search= query parameter.
    # Open, rename, archive, or delete a specific conversation.
    path(
        "<int:pk>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),

    # Get messages from one conversation.
    path(
        "<int:conversation_id>/messages/",
        MessageListView.as_view(),
        name="message-list",
    ),

    # Send a prompt and request an AI response.
    path(
        "<int:conversation_id>/messages/send/",
        SendMessageView.as_view(),
        name="send-message",
    ),

    # List attachment metadata for a conversation.
    path(
        "<int:conversation_id>/attachments/",
        ConversationAttachmentListView.as_view(),
        name="conversation-attachments",
    ),

    # List or submit feedback on an assistant response.
    path(
        "feedback/",
        FeedbackListCreateView.as_view(),
        name="feedback-list-create",
    ),
]

