
"""
Testing settings for OmaxasAI.
Used only for automated tests.
"""

from .base import *


# Disable debug mode during tests.
DEBUG = False

ALLOWED_HOSTS = [
    "testserver",
    "localhost",
    "127.0.0.1",
]


# Use a temporary in-memory SQLite database.
# Django's test runner manages its test database lifecycle.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


# Store outgoing emails in memory instead of sending them.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"


# Speed up password hashing during automated tests only.
# Never use this password hasher in development or production.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]


# Keep automated tests independent from password validators.
PASSWORD_VALIDATORS = []


# Use a separate local cache for tests.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "omaxasai-test-cache",
    }
}
