
"""
Development settings for OmaxasAI.
Used when running Django locally.
"""

from .base import *


# Development mode
DEBUG = True

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "testserver",
]


# Local frontend development server (Vite / React)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


# Display emails in the development terminal
# instead of sending real emails.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
