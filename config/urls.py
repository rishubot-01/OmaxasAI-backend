
"""URL configuration for the OmaxasAI backend."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def api_root(request):
    """Return basic API information and available endpoint groups."""

    return JsonResponse(
        {
            "name": "OmaxasAI API",
            "status": "running",
            "version": "1.0.0",
            "endpoints": {
                "admin": "/admin/",
                "authentication": "/api/auth/",
                "accounts": "/api/accounts/",
                "assistant": "/api/assistant/",
                "conversations": "/api/conversations/",
                "knowledge": "/api/knowledge/",
                "images": "/api/images/",
                "explore": "/api/explore/",
            },
        }
    )


urlpatterns = [
    # API overview
    path("", api_root, name="api-root"),

    # Django administration
    path("admin/", admin.site.urls),

    # Authentication and user accounts
    # Includes the existing auth/register/, auth/token/,
    # auth token refresh/verify, accounts/me/, and preferences routes.
    path(
        "api/",
        include("apps.accounts.urls"),
    ),

    # AI assistant: chat, available models, and request history
    path(
        "api/assistant/",
        include("apps.assistant.urls"),
    ),

    # Conversations: chat history, messages, attachments, and feedback
    path(
        "api/conversations/",
        include("apps.conversations.urls"),
    ),

    # Knowledge documents: upload, list, retrieve, and delete
    path(
        "api/knowledge/",
        include("apps.knowledge.urls"),
    ),

    # Image generation requests and image history
    path(
        "api/images/",
        include("apps.images.urls"),
    ),

    # Explore AI models, providers, and features
    path(
        "api/explore/",
        include("apps.explore.urls"),
    ),
]


# Serve media files through Django only during local development.
# Production deployments should use the configured storage service.
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
