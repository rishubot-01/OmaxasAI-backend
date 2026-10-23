
"""WSGI configuration for the OmaxasAI project.

This module exposes the WSGI application callable used by compatible
application servers such as Gunicorn.
"""

import os

from django.core.wsgi import get_wsgi_application


# Use development settings locally by default.
# Production deployments can override this through the
# DJANGO_SETTINGS_MODULE environment variable.
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "config.settings.development",
)

# WSGI application entry point.
application = get_wsgi_application()
