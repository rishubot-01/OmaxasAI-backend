
"""ASGI configuration for the OmaxasAI project."""

import os

from django.core.asgi import get_asgi_application


# Use development settings locally unless another settings module
# has already been specified through the environment.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

application = get_asgi_application()
