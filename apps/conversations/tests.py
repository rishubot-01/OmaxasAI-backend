
"""
Tests for OmaxasAI conversations.

Tests chat models, message creation, attachment validation,
feedback validation, and user ownership restrictions.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import serializers

from .models import Conversation, Feedback, FileAttachment, Message
from .serializers import (
    ConversationSerializer,
    FeedbackSerializer,
    FileAttachmentSerializer,
    MessageSerializer,
    UserMessageCreateSerializer,
)


User = get_user_model()


class ConversationModelTests(TestCase):
    """Tests for conversation creation and ownership."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="user1@example.com",
            password="StrongPass!8271",
        )

        self.other_user = User.objects.create_user(
            email="user2@example.com",
            password="StrongPass!8271",
        )

    def test_create_conversation(self):
        conversation = Conversation.objects.create(
            user=self.user,
            title="Python interview prep",
        )

        self.assertEqual(
            conversation.title,
            "Python interview prep",
        )
        self.assertFalse(conversation.is_archived)
        self.assertEqual(conversation.user, self.user)

    def test_conversation_has_new_chat_default_title(self):
        conversation = Conversation.objects.create(
            user=self.user,
        )

        self.assertEqual(conversation.title, "New chat")

    def test_users_have_separate_conversations(self):
        Conversation.objects.create(
            user=self.user,
            title="My private chat",
        )

        Conversation.objects.create(
            user=self.other_user,
            title="Another user's chat",
        )

        self.assertEqual(
            Conversation.objects.filter(user=self.user).count(),
            1,
        )

        self.assertEqual(
            Conversation.objects.filter(user=self.other_user).count(),
            1,
        )

    def test_conversation_serializer_rejects_empty_title(self):
        serializer = ConversationSerializer(
            data={"title": "   "},
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("title", serializer.errors)


class MessageModelTests(TestCase):
    """Tests for chat message creation and relationships."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="messages@example.com",
            password="StrongPass!8271",
        )

        self.conversation = Conversation.objects.create(
            user=self.user,
            title="Django API setup",
        )

    def test_create_user_message(self):
        message = Message.objects.create(
            conversation=self.conversation,
            role=Message.RoleChoices.USER,
            content="Create a Django REST API.",
        )

        self.assertEqual(message.role, "user")
        self.assertEqual(
            message.content,
            "Create a Django REST API.",
        )
        self.assertEqual(message.conversation, self.conversation)

    def test_message_defaults_to_auto_mode(self):
        message = Message.objects.create(
            conversation=self.conversation,
            role=Message.RoleChoices.USER,
            content="What is Python?",
        )

        self.assertEqual(message.mode, "auto")
        self.assertFalse(message.web_search_used)

    def test_create_assistant_message(self):
        message = Message.objects.create(
            conversation=self.conversation,
            role=Message.RoleChoices.ASSISTANT,
            content="Here is the solution.",
            mode=Message.ModeChoices.THINK,
            provider="openai",
            model_name="example-model",
        )

        self.assertEqual(message.role, "assistant")
        self.assertEqual(message.mode, "think")
        self.assertEqual(message.provider, "openai")


class UserMessageSerializerTests(TestCase):
    """Tests for validating messages from authenticated users."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="sender@example.com",
            password="StrongPass!8271",
        )

        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="StrongPass!8271",
        )

        self.conversation = Conversation.objects.create(
            user=self.user,
            title="My conversation",
        )

        self.other_conversation = Conversation.objects.create(
            user=self.other_user,
            title="Private conversation",
        )

        self.request_context = {
            "request": SimpleNamespace(user=self.user),
        }

    def test_valid_user_message(self):
        serializer = UserMessageCreateSerializer(
            data={
                "conversation": self.conversation.pk,
                "content": "Hello OmaxasAI!",
                "mode": "auto",
            },
            context=self.request_context,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        message = serializer.save()

        self.assertEqual(message.role, Message.RoleChoices.USER)
        self.assertEqual(message.conversation, self.conversation)

    def test_empty_message_is_rejected(self):
        serializer = UserMessageCreateSerializer(
            data={
                "conversation": self.conversation.pk,
                "content": "   ",
                "mode": "auto",
            },
            context=self.request_context,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_user_cannot_select_another_users_conversation(self):
        serializer = UserMessageCreateSerializer(
            data={
                "conversation": self.other_conversation.pk,
                "content": "Trying to access another chat.",
                "mode": "auto",
            },
            context=self.request_context,
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("conversation", serializer.errors)

    def test_user_cannot_create_assistant_message_through_input_serializer(self):
        serializer = UserMessageCreateSerializer(
            data={
                "conversation": self.conversation.pk,
                "content": "Fake AI answer",
                "role": "assistant",
            },
            context=self.request_context,
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        message = serializer.save()

        # The server must assign the user role.
        self.assertEqual(message.role, Message.RoleChoices.USER)


class FileAttachmentTests(TestCase):
    """Tests for attachment metadata and ownership validation."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="files@example.com",
            password="StrongPass!8271",
        )

        self.other_user = User.objects.create_user(
            email="otherfiles@example.com",
            password="StrongPass!8271",
        )

        self.conversation = Conversation.objects.create(
            user=self.user,
            title="Document analysis",
        )

        self.other_conversation = Conversation.objects.create(
            user=self.other_user,
            title="Another user's documents",
        )

    def test_create_attachment_metadata(self):
        attachment = FileAttachment.objects.create(
            conversation=self.conversation,
            original_filename="report.pdf",
            file_type=FileAttachment.FileTypeChoices.DOCUMENT,
            mime_type="application/pdf",
            size_bytes=1024,
            status=FileAttachment.StatusChoices.PENDING,
        )

        self.assertEqual(attachment.original_filename, "report.pdf")
        self.assertEqual(attachment.size_bytes, 1024)
        self.assertEqual(attachment.status, "pending")

    def test_attachment_serializer_rejects_path_in_filename(self):
        serializer = FileAttachmentSerializer(
            data={
                "conversation": self.conversation.pk,
                "original_filename": "../private/report.pdf",
                "file_type": "document",
                "mime_type": "application/pdf",
            },
            context={
                "request": SimpleNamespace(user=self.user),
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("original_filename", serializer.errors)

    def test_user_cannot_attach_to_another_users_conversation(self):
        serializer = FileAttachmentSerializer(
            data={
                "conversation": self.other_conversation.pk,
                "original_filename": "report.pdf",
                "file_type": "document",
                "mime_type": "application/pdf",
            },
            context={
                "request": SimpleNamespace(user=self.user),
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("conversation", serializer.errors)


class FeedbackTests(TestCase):
    """Tests for feedback on assistant responses."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="feedback@example.com",
            password="StrongPass!8271",
        )

        self.conversation = Conversation.objects.create(
            user=self.user,
            title="AI response feedback",
        )

        self.assistant_message = Message.objects.create(
            conversation=self.conversation,
            role=Message.RoleChoices.ASSISTANT,
            content="Python is a programming language.",
        )

        self.user_message = Message.objects.create(
            conversation=self.conversation,
            role=Message.RoleChoices.USER,
            content="What is Python?",
        )

    def test_create_feedback_for_assistant_message(self):
        feedback = Feedback.objects.create(
            user=self.user,
            message=self.assistant_message,
            rating=Feedback.RatingChoices.HELPFUL,
            comment="Clear and useful.",
        )

        self.assertEqual(feedback.rating, "helpful")
        self.assertEqual(feedback.user, self.user)

    def test_feedback_serializer_rejects_user_message(self):
        serializer = FeedbackSerializer(
            data={
                "message": self.user_message.pk,
                "rating": "helpful",
                "comment": "This is not an AI response.",
            },
            context={
                "request": SimpleNamespace(user=self.user),
            },
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("message", serializer.errors)

    def test_feedback_serializer_accepts_assistant_message(self):
        serializer = FeedbackSerializer(
            data={
                "message": self.assistant_message.pk,
                "rating": "helpful",
                "comment": "Useful answer.",
            },
            context={
                "request": SimpleNamespace(user=self.user),
            },
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        feedback = serializer.save()

        self.assertEqual(feedback.user, self.user)
        self.assertEqual(
            feedback.message,
            self.assistant_message,
        )

