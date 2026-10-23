
"""Tests for OmaxasAI Knowledge documents and APIs."""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase

from rest_framework.test import APIRequestFactory, force_authenticate

from .models import DocumentChunk, KnowledgeDocument
from .serializers import KnowledgeDocumentSerializer
from .views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentListCreateView,
)

User = get_user_model()


class KnowledgeDocumentModelTests(TestCase):
    """Tests for KnowledgeDocument and DocumentChunk models."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="knowledge@example.com",
            password="StrongTestPass!8271",
        )

    def test_create_text_document(self):
        document = KnowledgeDocument.objects.create(
            owner=self.user,
            title="Python Notes",
            source_type=KnowledgeDocument.SourceType.TEXT,
            source_text="Python is a programming language.",
        )

        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.status, "uploaded")
        self.assertEqual(document.chunk_count, 0)

    def test_create_url_document(self):
        document = KnowledgeDocument.objects.create(
            owner=self.user,
            title="Python Documentation",
            source_type=KnowledgeDocument.SourceType.URL,
            source_url="https://docs.python.org/",
        )

        self.assertEqual(
            document.source_type,
            KnowledgeDocument.SourceType.URL,
        )

    def test_text_document_requires_source_text(self):
        document = KnowledgeDocument(
            owner=self.user,
            title="Empty Document",
            source_type=KnowledgeDocument.SourceType.TEXT,
            source_text="",
        )

        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_url_document_requires_source_url(self):
        document = KnowledgeDocument(
            owner=self.user,
            title="Missing URL",
            source_type=KnowledgeDocument.SourceType.URL,
            source_url="",
        )

        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_upload_document_requires_file(self):
        document = KnowledgeDocument(
            owner=self.user,
            title="Missing File",
            source_type=KnowledgeDocument.SourceType.UPLOAD,
        )

        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_document_chunk_creation(self):
        document = KnowledgeDocument.objects.create(
            owner=self.user,
            title="Chunk Source",
            source_type=KnowledgeDocument.SourceType.TEXT,
            source_text="Some source content.",
        )

        chunk = DocumentChunk.objects.create(
            document=document,
            chunk_index=0,
            content="Some source content.",
            token_count=4,
            embedding=[0.1, 0.2, 0.3],
            embedding_model="test-embedding-model",
        )

        self.assertEqual(chunk.document, document)
        self.assertEqual(chunk.chunk_index, 0)
        self.assertEqual(document.chunks.count(), 1)

    def test_duplicate_chunk_indexes_are_rejected(self):
        """A document cannot contain duplicate chunk indexes."""

        document = KnowledgeDocument.objects.create(
            owner=self.user,
            title="Duplicate Chunks",
            source_type=KnowledgeDocument.SourceType.TEXT,
            source_text="Example content.",
        )

        DocumentChunk.objects.create(
            document=document,
            chunk_index=0,
            content="First chunk.",
        )

        # Use a savepoint so the expected database error does not leave
        # the surrounding Django TestCase transaction in a broken state.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentChunk.objects.create(
                    document=document,
                    chunk_index=0,
                    content="Duplicate index.",
                )

        self.assertEqual(document.chunks.count(), 1)


class KnowledgeDocumentSerializerTests(TestCase):
    """Tests for document input validation."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="serializer@example.com",
            password="StrongTestPass!8271",
        )

    def test_valid_text_document(self):
        serializer = KnowledgeDocumentSerializer(
            data={
                "title": "My Notes",
                "source_type": "text",
                "source_text": "This is a knowledge document.",
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        document = serializer.save(owner=self.user)

        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.title, "My Notes")

    def test_empty_text_document_is_rejected(self):
        serializer = KnowledgeDocumentSerializer(
            data={
                "title": "Empty Notes",
                "source_type": "text",
                "source_text": "   ",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("source_text", serializer.errors)

    def test_missing_title_is_rejected(self):
        serializer = KnowledgeDocumentSerializer(
            data={
                "source_type": "text",
                "source_text": "Some text.",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("title", serializer.errors)

    def test_unsupported_file_extension_is_rejected(self):
        uploaded_file = SimpleUploadedFile(
            "program.exe",
            b"example content",
            content_type="application/octet-stream",
        )

        serializer = KnowledgeDocumentSerializer(
            data={
                "title": "Unsupported File",
                "source_type": "upload",
                "file": uploaded_file,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_supported_pdf_passes_basic_file_validation(self):
        """Check basic filename, size, and reported MIME validation."""

        uploaded_file = SimpleUploadedFile(
            "guide.pdf",
            b"%PDF-1.4 test content",
            content_type="application/pdf",
        )

        serializer = KnowledgeDocumentSerializer(
            data={
                "title": "PDF Guide",
                "source_type": "upload",
                "file": uploaded_file,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_url_document_requires_url(self):
        serializer = KnowledgeDocumentSerializer(
            data={
                "title": "Website Notes",
                "source_type": "url",
                "source_url": "",
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("source_url", serializer.errors)

    def test_client_cannot_set_owner_or_processing_status(self):
        serializer = KnowledgeDocumentSerializer(
            data={
                "title": "My Notes",
                "source_type": "text",
                "source_text": "Knowledge content.",
                "owner": 9999,
                "status": "ready",
                "chunk_count": 500,
            }
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)

        document = serializer.save(owner=self.user)

        self.assertEqual(document.owner, self.user)
        self.assertEqual(document.status, "uploaded")
        self.assertEqual(document.chunk_count, 0)


class KnowledgeDocumentAPITests(TestCase):
    """Tests for authenticated document API access and ownership."""

    def setUp(self):
        self.factory = APIRequestFactory()

        self.user = User.objects.create_user(
            email="owner@example.com",
            password="StrongTestPass!8271",
        )

        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="StrongTestPass!8271",
        )

        self.own_document = KnowledgeDocument.objects.create(
            owner=self.user,
            title="My Private Notes",
            source_type=KnowledgeDocument.SourceType.TEXT,
            source_text="Private information.",
        )

        self.other_document = KnowledgeDocument.objects.create(
            owner=self.other_user,
            title="Other User Notes",
            source_type=KnowledgeDocument.SourceType.TEXT,
            source_text="Another user's information.",
        )

    def test_list_shows_only_owned_documents(self):
        request = self.factory.get("/knowledge/")
        force_authenticate(request, user=self.user)

        response = KnowledgeDocumentListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 200)

        returned_ids = {
            item["id"]
            for item in response.data
        }

        self.assertIn(self.own_document.id, returned_ids)
        self.assertNotIn(self.other_document.id, returned_ids)

    def test_user_can_retrieve_own_document(self):
        request = self.factory.get(
            f"/knowledge/{self.own_document.pk}/"
        )
        force_authenticate(request, user=self.user)

        response = KnowledgeDocumentDetailView.as_view()(
            request,
            pk=self.own_document.pk,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.own_document.pk)

    def test_user_cannot_retrieve_another_users_document(self):
        request = self.factory.get(
            f"/knowledge/{self.other_document.pk}/"
        )
        force_authenticate(request, user=self.user)

        response = KnowledgeDocumentDetailView.as_view()(
            request,
            pk=self.other_document.pk,
        )

        self.assertEqual(response.status_code, 404)

    def test_unauthenticated_user_cannot_list_documents(self):
        request = self.factory.get("/knowledge/")

        response = KnowledgeDocumentListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 401)

    def test_create_document_assigns_authenticated_owner(self):
        request = self.factory.post(
            "/knowledge/",
            {
                "title": "New Knowledge",
                "source_type": "text",
                "source_text": "A new knowledge entry.",
            },
            format="json",
        )
        force_authenticate(request, user=self.user)

        response = KnowledgeDocumentListCreateView.as_view()(request)

        self.assertEqual(response.status_code, 201)

        document = KnowledgeDocument.objects.get(
            pk=response.data["id"]
        )

        self.assertEqual(document.owner, self.user)
        self.assertEqual(
            document.source_text,
            "A new knowledge entry.",
        )

    def test_user_can_delete_own_document(self):
        request = self.factory.delete(
            f"/knowledge/{self.own_document.pk}/"
        )
        force_authenticate(request, user=self.user)

        response = KnowledgeDocumentDetailView.as_view()(
            request,
            pk=self.own_document.pk,
        )

        self.assertEqual(response.status_code, 204)

        self.assertFalse(
            KnowledgeDocument.objects.filter(
                pk=self.own_document.pk
            ).exists()
        )
