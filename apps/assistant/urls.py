"""
URL routes for the OmaxasAI Assistant API.
"""

from django.urls import path

from .views import (
    AIRequestHistoryView,
    AvailableModelsView,
    generate_response,
)


app_name = "assistant"

urlpatterns = [
    # Generate an AI response.
    path(
        "chat/",
        generate_response,
        name="generate-response",
    ),

    # List available AI models.
    path(
        "models/",
        AvailableModelsView.as_view(),
        name="available-models",
    ),

    # Get the authenticated user's AI request history.
    path(
        "requests/",
        AIRequestHistoryView.as_view(),
        name="request-history",
    ),
]
