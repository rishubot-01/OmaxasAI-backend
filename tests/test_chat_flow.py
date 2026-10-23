
"""Tests for OmaxasAI conversation and chat flows."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.conversations.models import Conversation, Message
from apps.conversations.services.chat_service import (
    ChatServiceError,
    send_chat_message,
)
from apps.conversations.views import ConversationListCreateView

User = get_user_model()


class ConversationModelTests(TestCase):
    """Test conversation and message database behavior."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="chatuser@example.com",
            password="ChatStrongPass!8271",
        )

    def test_create_conversation(self):
        conversation = Conversation.objects.create(
            user=self.user,
            title="Python Help",
        )

        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.title, "Python Help")
        self.assertFalse(conversation.is_archived)

    def test_conversation_default_title(self):
        conversation = Conversation.objects.create(
            user=self.user,
        )

        self.assertEqual(conversation.title, "New chat")

    def test_users_have_separate_conversations(self):
        another_user = User.objects.create_user(
            email="anotherchat@example.com",
            password="ChatStrongPass!8271",
        )

        own_conversation = Conversation.objects.create(
            user=self.user,
            title="My Conversation",
        )

        another_conversation = Conversation.objects.create(
            user=another_user,
            title="Another Conversation",
        )

        self.assertNotEqual(
            own_conversation.user_id,
            another_conversation.user_id,
        )

        self.assertEqual(
            Conversation.objects.filter(user=self.user).count(),
            1,
        )

    def test_create_user_message(self):
        conversation = Conversation.objects.create(user=self.user)

        message = Message.objects.create(
            conversation=conversation,
            role="user",
            content="Explain Python classes.",
        )

        self.assertEqual(message.role, "user")
        self.assertEqual(
            message.content,
            "Explain Python classes.",
        )
        self.assertEqual(message.mode, "auto")

    def test_create_assistant_message(self):
        conversation = Conversation.objects.create(user=self.user)

        message = Message.objects.create(
            conversation=conversation,
            role="assistant",
            content="A class is a blueprint for objects.",
            mode="think",
            provider="openai",
            model_name="test-model",
        )

        self.assertEqual(message.role, "assistant")
        self.assertEqual(message.mode, "think")
        self.assertEqual(message.provider, "openai")
        self.assertEqual(message.model_name, "test-model")

    def test_deleting_conversation_deletes_its_messages(self):
        conversation = Conversation.objects.create(user=self.user)

        Message.objects.create(
            conversation=conversation,
            role="user",
            content="Hello",
        )

        self.assertEqual(conversation.messages.count(), 1)

        conversation.delete()

        self.assertEqual(Message.objects.count(), 0)


class ConversationAPITests(TestCase):
    """Test conversation listing and creation API access."""

    def setUp(self):
        self.factory = APIRequestFactory()

        self.user = User.objects.create_user(
            email="api-chat@example.com",
            password="ChatStrongPass!8271",
        )

        self.other_user = User.objects.create_user(
            email="other-api-chat@example.com",
            password="ChatStrongPass!8271",
        )

        self.own_conversation = Conversation.objects.create(
            user=self.user,
            title="My Private Chat",
        )

        self.other_conversation = Conversation.objects.create(
            user=self.other_user,
            title="Another User's Chat",
        )

    def test_list_returns_only_current_users_conversations(self):
        request = self.factory.get("/api/conversations/")
        force_authenticate(request, user=self.user)

        response = ConversationListCreateView.as_view()(request)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        returned_ids = {
            item["id"]
            for item in response.data
        }

        self.assertIn(self.own_conversation.id, returned_ids)
        self.assertNotIn(self.other_conversation.id, returned_ids)

    def test_unauthenticated_user_cannot_list_conversations(self):
        request = self.factory.get("/api/conversations/")

        response = ConversationListCreateView.as_view()(request)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_create_conversation_assigns_authenticated_user(self):
        request = self.factory.post(
            "/api/conversations/",
            {"title": "New Coding Chat"},
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = ConversationListCreateView.as_view()(request)

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            getattr(response, "data", None),
        )

        conversation = Conversation.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.title, "New Coding Chat")


class ChatServiceFlowTests(TestCase):
    """Test end-to-end message handling at the chat-service layer."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="service-chat@example.com",
            password="ChatStrongPass!8271",
        )

        self.conversation = Conversation.objects.create(
            user=self.user,
            title="New chat",
        )

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_send_message_saves_user_and_assistant_messages(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.return_value = {
            "text": "A Python class defines a type of object.",
            "provider": "openai",
            "model_name": "test-chat-model",
            "category": "coding",
            "fallback_used": False,
            "response_time_ms": 250,
            "input_tokens": 12,
            "output_tokens": 10,
            "web_search_used": False,
        }

        user_message, assistant_message = send_chat_message(
            user=self.user,
            conversation=self.conversation,
            content="What is a Python class?",
            mode="auto",
            web_search=False,
        )

        self.assertEqual(user_message.role, "user")
        self.assertEqual(
            user_message.content,
            "What is a Python class?",
        )

        self.assertEqual(assistant_message.role, "assistant")
        self.assertEqual(
            assistant_message.content,
            "A Python class defines a type of object.",
        )

        self.assertEqual(assistant_message.provider, "openai")
        self.assertEqual(
            assistant_message.model_name,
            "test-chat-model",
        )

        self.assertEqual(
            assistant_message.metadata["category"],
            "coding",
        )

        self.assertEqual(
            self.conversation.messages.count(),
            2,
        )

        mock_generate_reply.assert_called_once_with(
            message="What is a Python class?",
            mode="auto",
            web_search=False,
            user=self.user,
        )

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_send_message_accepts_string_ai_response(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.return_value = "Hello! How can I help?"

        user_message, assistant_message = send_chat_message(
            user=self.user,
            conversation=self.conversation,
            content="Hello",
        )

        self.assertEqual(user_message.content, "Hello")
        self.assertEqual(
            assistant_message.content,
            "Hello! How can I help?",
        )
        self.assertEqual(assistant_message.role, "assistant")
        self.assertEqual(assistant_message.provider, "")

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_first_message_updates_default_conversation_title(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.return_value = "Here is your answer."

        send_chat_message(
            user=self.user,
            conversation=self.conversation,
            content="Help me learn Python",
        )

        self.conversation.refresh_from_db()

        self.assertEqual(
            self.conversation.title,
            "Help me learn Python",
        )

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_think_mode_is_saved(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.return_value = "Let's reason through it."

        user_message, assistant_message = send_chat_message(
            user=self.user,
            conversation=self.conversation,
            content="Solve this step by step.",
            mode="think",
        )

        self.assertEqual(user_message.mode, "think")
        self.assertEqual(assistant_message.mode, "think")

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_web_search_flag_is_forwarded_to_ai_service(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.return_value = {
            "text": "Search-based answer.",
            "web_search_used": True,
            "provider": "openai",
            "model_name": "test-model",
        }

        _, assistant_message = send_chat_message(
            user=self.user,
            conversation=self.conversation,
            content="Find recent information.",
            web_search=True,
        )

        mock_generate_reply.assert_called_once_with(
            message="Find recent information.",
            mode="auto",
            web_search=True,
            user=self.user,
        )

        self.assertTrue(assistant_message.web_search_used)

    def test_empty_message_is_rejected(self):
        with self.assertRaises(ChatServiceError):
            send_chat_message(
                user=self.user,
                conversation=self.conversation,
                content="   ",
            )

        self.assertEqual(self.conversation.messages.count(), 0)

    def test_message_over_length_limit_is_rejected(self):
        with self.assertRaises(ChatServiceError):
            send_chat_message(
                user=self.user,
                conversation=self.conversation,
                content="x" * 50001,
            )

        self.assertEqual(self.conversation.messages.count(), 0)

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_user_cannot_send_message_to_another_users_conversation(
        self,
        mock_generate_reply,
    ):
        another_user = User.objects.create_user(
            email="private-chat@example.com",
            password="ChatStrongPass!8271",
        )

        another_conversation = Conversation.objects.create(
            user=another_user,
            title="Private Conversation",
        )

        with self.assertRaises(ChatServiceError):
            send_chat_message(
                user=self.user,
                conversation=another_conversation,
                content="Attempt to access another chat",
            )

        mock_generate_reply.assert_not_called()
        self.assertEqual(another_conversation.messages.count(), 0)

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_ai_failure_does_not_create_assistant_message(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.side_effect = RuntimeError(
            "Simulated AI provider failure"
        )

        with self.assertRaises(RuntimeError):
            send_chat_message(
                user=self.user,
                conversation=self.conversation,
                content="Please answer this question.",
            )

        messages = list(
            self.conversation.messages.order_by("created_at", "id")
        )

        # The user message is preserved so the frontend can retry.
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")

    @patch("apps.conversations.services.chat_service.generate_reply")
    def test_empty_ai_response_is_rejected(
        self,
        mock_generate_reply,
    ):
        mock_generate_reply.return_value = {"text": "   "}

        with self.assertRaises(ChatServiceError):
            send_chat_message(
                user=self.user,
                conversation=self.conversation,
                content="Give me an answer.",
            )

        roles = list(
            self.conversation.messages.values_list(
                "role",
                flat=True,
            )
        )

        self.assertEqual(roles, ["user"])

