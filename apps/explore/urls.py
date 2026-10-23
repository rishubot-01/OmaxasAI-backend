
"""URL routes for OmaxasAI Explore APIs."""

from django.urls import path

from .views import (
    ExploreFeaturesView,
    ExploreModelsView,
    ExploreProvidersView,
)

app_name = "explore"

urlpatterns = [
    # Discover and filter active AI models.
    path(
        "models/",
        ExploreModelsView.as_view(),
        name="models",
    ),

    # Discover providers and their model capabilities.
    path(
        "providers/",
        ExploreProvidersView.as_view(),
        name="providers",
    ),

    # List Explore features and their integration status.
    path(
        "features/",
        ExploreFeaturesView.as_view(),
        name="features",
    ),
]

