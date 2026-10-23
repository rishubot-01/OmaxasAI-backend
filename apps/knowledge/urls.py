
"""URL routes for OmaxasAI Knowledge APIs."""

from django.urls import path

from .views import (
    KnowledgeDocumentDetailView,
    KnowledgeDocumentListCreateView,
)

app_name = "knowledge"

urlpatterns = [
    # List documents or upload a new document.
    path(
        "",
        KnowledgeDocumentListCreateView.as_view(),
        name="document-list-create",
    ),

    # Retrieve or delete a specific document.
    path(
        "<int:pk>/",
        KnowledgeDocumentDetailView.as_view(),
        name="document-detail",
    ),
]

