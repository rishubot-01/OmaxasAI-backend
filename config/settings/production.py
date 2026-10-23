"""
Production settings for OmaxasAI.
Used when deploying the backend to a production server.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *


# ==================================================
# 1. DEBUG MODE
# ==================================================

DEBUG = False


# ==================================================
# 2. SECRET KEY
# ==================================================

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

if not SECRET_KEY:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be configured in production."
    )


# ==================================================
# 3. ALLOWED HOSTS
# ==================================================

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "",
    ).split(",")
    if host.strip()
]

if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Set DJANGO_ALLOWED_HOSTS in the production environment."
    )


# ==================================================
# 4. CORS AND CSRF
# ==================================================

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "",
    ).split(",")
    if origin.strip()
]

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "",
    ).split(",")
    if origin.strip()
]


# ==================================================
# 5. HTTPS SECURITY
# ==================================================

SECURE_SSL_REDIRECT = (
    os.getenv("DJANGO_SECURE_SSL_REDIRECT", "True").lower()
    in {"true", "1", "yes", "on"}
)

# Use this only when a trusted reverse proxy sets and
# sanitizes the X-Forwarded-Proto header correctly.
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"


# Enable HSTS only after HTTPS is correctly configured
# for the production domain.
SECURE_HSTS_SECONDS = int(
    os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0")
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False


# ==================================================
# 6. EMAIL
# ==================================================

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)