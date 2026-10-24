
"""
Base settings for OmaxasAI.
Shared configuration for development, testing and production.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


# ==================================================
# 1. PROJECT PATHS AND ENVIRONMENT VARIABLES
# ==================================================

BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")


# ==================================================
# 2. SECURITY SETTINGS
# ==================================================

SECRET_KEY = os.getenv(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-development-only-change-before-deployment",
)

DEBUG = os.getenv("DJANGO_DEBUG", "False").strip().lower() in {
    "true",
    "1",
    "yes",
    "on",
}

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv(
        "DJANGO_ALLOWED_HOSTS",
        "127.0.0.1,localhost,testserver",
    ).split(",")
    if host.strip()
]

# Google OAuth Client ID.
# Use the same Web application Client ID in the frontend
# and when verifying Google ID tokens.
GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "",
).strip()


# ==================================================
# 3. DJANGO APPLICATIONS
# ==================================================

INSTALLED_APPS = [
    # Django built-in apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party apps
    "rest_framework",
    "corsheaders",

    # OmaxasAI apps
    "apps.accounts.apps.AccountsConfig",
    "apps.conversations.apps.ConversationsConfig",
    "apps.assistant.apps.AssistantConfig",
    "apps.knowledge.apps.KnowledgeConfig",
    "apps.images.apps.ImagesConfig",
    "apps.explore.apps.ExploreConfig",
]


# ==================================================
# 4. CUSTOM USER MODEL
# ==================================================

AUTH_USER_MODEL = "accounts.User"


# ==================================================
# 5. MIDDLEWARE
# ==================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ==================================================
# 6. URL AND SERVER CONFIGURATION
# ==================================================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# ==================================================
# 7. TEMPLATE CONFIGURATION
# ==================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ==================================================
# 8. DATABASE CONFIGURATION
# Supports Neon Cloud PostgreSQL and local SQLite.
# ==================================================

DB_ENGINE = os.getenv(
    "DB_ENGINE",
    "sqlite",
).strip().lower()

if DB_ENGINE in {"postgres", "postgresql"}:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "").strip(),
            "USER": os.getenv("DB_USER", "").strip(),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "").strip(),
            "PORT": os.getenv("DB_PORT", "5432").strip(),
            "OPTIONS": {
                "sslmode": os.getenv(
                    "DB_SSLMODE",
                    "require",
                ).strip(),
            },
            "CONN_MAX_AGE": 60,
            "CONN_HEALTH_CHECKS": True,
        }
    }

elif DB_ENGINE == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

else:
    raise ValueError(
        "Unsupported DB_ENGINE. Use 'sqlite' or 'postgres'."
    )


# ==================================================
# 9. PASSWORD VALIDATION
# ==================================================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
        "OPTIONS": {
            "min_length": 8,
        },
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# ==================================================
# 10. LANGUAGE AND TIME ZONE
# ==================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True
USE_TZ = True


# ==================================================
# 11. STATIC FILES AND USER UPLOADS
# ==================================================

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# ==================================================
# 12. EMAIL CONFIGURATION
# ==================================================

EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    os.getenv(
        "EMAIL_BACKEND",
        "django.core.mail.backends.console.EmailBackend",
    ),
)


# ==================================================
# 13. DJANGO REST FRAMEWORK
# ==================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],

    # Rate limits used by individual API throttles.
    "DEFAULT_THROTTLE_RATES": {
        # Anonymous AI chat: 10 requests per hour.
        "assistant_guest": "10/hour",
    },
}


# ==================================================
# 14. CORS CONFIGURATION
# ==================================================

CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        (
            "https://omaxas-ai-frontend.vercel.app,"
            "http://localhost:5173,"
            "http://127.0.0.1:5173"
        ),
    ).split(",")
    if origin.strip()
]


# ==================================================
# 15. DEFAULT DATABASE MODEL FIELD
# ==================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
