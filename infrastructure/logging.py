
"""Centralized logging configuration for the OmaxasAI backend."""

import os


VALID_LOG_LEVELS = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


def _get_log_level() -> str:
    """Return a valid logging level from the environment."""

    configured_level = os.getenv(
        "OMAXASAI_LOG_LEVEL",
        "INFO",
    ).strip().upper()

    if configured_level not in VALID_LOG_LEVELS:
        return "INFO"

    return configured_level


LOG_LEVEL = _get_log_level()


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "{asctime} | {levelname:8} | {name} | "
                "process={process} | {message}"
            ),
            "style": "{",
        },
        "simple": {
            "format": "{levelname}: {message}",
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": LOG_LEVEL,
            "formatter": "verbose",
            "stream": "ext://sys.stdout",
        },
    },

    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },

    "loggers": {
        # Application code under apps/.
        "apps": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },

        # Shared infrastructure code.
        "infrastructure": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },

        # Django application logs.
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },

        # HTTP request errors and server-side request failures.
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },

        # Django security-related warnings.
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },

        # Avoid verbose SQL logs during normal development.
        "django.db.backends": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}

