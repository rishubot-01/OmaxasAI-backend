
"""API views for OmaxasAI Knowledge documents."""

import logging

from rest_framework import generics
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from .models import KnowledgeDocument
from .serializers import KnowledgeDocumentSerializer

logger = logging.getLogger(__name__)


class KnowledgeDocumentListCreateView(generics.ListCreateAPIView):
    """
    GET  /knowledge/          - List the current user's documents.
    POST /knowledge/          - Create a document from a file, URL, or text.
    """

    serializer_class = KnowledgeDocumentSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        """Return only documents owned by the authenticated user."""

        return KnowledgeDocument.objects.filter(
            owner=self.request.user
        ).order_by("-updated_at", "-id")

    def perform_create(self, serializer):
        """Assign ownership on the server, never from client input."""

        serializer.save(owner=self.request.user)


class KnowledgeDocumentDetailView(generics.RetrieveDestroyAPIView):
    """
    GET    /knowledge/<pk>/   - Retrieve a document's details.
    DELETE /knowledge/<pk>/   - Delete an owned document.
    """

    serializer_class = KnowledgeDocumentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        """Prevent users from accessing another user's documents."""

        return KnowledgeDocument.objects.filter(
            owner=self.request.user
        )

    def perform_destroy(self, instance):
        """
        Delete the stored file, if present, and then delete the database row.

        Related document chunks are removed through the model's cascade rule.
        """

        document_id = instance.pk

        try:
            if instance.file:
                instance.file.delete(save=False)

            instance.delete()

            logger.info(
                "Knowledge document deleted",
                extra={
                    "document_id": document_id,
                    "user_id": self.request.user.pk,
                },
            )
        except Exception:
            logger.exception(
                "Failed to delete knowledge document",
                extra={
                    "document_id": document_id,
                    "user_id": self.request.user.pk,
                },
            )
            raise

