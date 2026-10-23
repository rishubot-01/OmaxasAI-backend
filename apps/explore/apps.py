
"""Application configuration for OmaxasAI Explore."""

from django.apps import AppConfig


class ExploreConfig(AppConfig):
    """Configure the Explore application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.explore"
    verbose_name = "OmaxasAI Explore"
