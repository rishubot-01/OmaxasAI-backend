
"""Application configuration for OmaxasAI Knowledge."""

from django.apps import AppConfig


class KnowledgeConfig(AppConfig):
    """Configure the document knowledge and retrieval application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.knowledge"
    verbose_name = "OmaxasAI Knowledge"
