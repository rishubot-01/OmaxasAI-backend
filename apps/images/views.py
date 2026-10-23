
"""API views for OmaxasAI image generation requests."""

import logging

from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from .models import ImageGenerationRequest
from .serializers import (
    ImageGenerationDetailSerializer,
    ImageGenerationRequestSerializer,
)

logger = logging.getLogger(__name__)


class ImageGenerationListCreateView(generics.ListCreateAPIView):
    """
    GET  /images/  - List the authenticated user's generation requests.
    POST /images/  - Create a new generation request.
    """

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Return only the current user's requests."""

        return (
            ImageGenerationRequest.objects.filter(user=self.request.user)
            .order_by("-created_at", "-id")
        )

    def get_serializer_class(self):
        """Use a request serializer for creation and a detail serializer
        for listing existing requests."""

        if self.request.method == "GET":
            return ImageGenerationDetailSerializer

        return ImageGenerationRequestSerializer

    def perform_create(self, serializer):
        """Assign ownership using the authenticated session or token."""

        serializer.save(user=self.request.user)


class ImageGenerationDetailView(generics.RetrieveAPIView):
    """
    GET /images/<uuid>/ - Retrieve an owned generation request and its images.

    The request UUID is used instead of exposing a sequential ID in the URL.
    """

    serializer_class = ImageGenerationDetailSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "request_id"
    lookup_url_kwarg = "request_id"

    def get_queryset(self):
        """Prevent users from viewing another user's generation requests."""

        return (
            ImageGenerationRequest.objects.filter(user=self.request.user)
            .prefetch_related("images")
        )

