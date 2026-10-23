
"""Application configuration for OmaxasAI Images."""

from django.apps import AppConfig


class ImagesConfig(AppConfig):
    """Configure the image generation and management application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.images"
    verbose_name = "OmaxasAI Images"
