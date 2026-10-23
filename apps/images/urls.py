
"""URL routes for OmaxasAI Images APIs."""

from django.urls import path

from .views import (
    ImageGenerationDetailView,
    ImageGenerationListCreateView,
)

app_name = "images"

urlpatterns = [
    # List the current user's generation history or create a request.
    path(
        "",
        ImageGenerationListCreateView.as_view(),
        name="generation-list-create",
    ),

    # Retrieve a specific generation request using its UUID.
    path(
        "<uuid:request_id>/",
        ImageGenerationDetailView.as_view(),
        name="generation-detail",
    ),
]

