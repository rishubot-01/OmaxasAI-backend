"""
URL routes for OmaxasAI accounts and authentication.
"""

from django.urls import path

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)

from .views import (
    GoogleAuthView,
    UserPreferenceView,
    UserProfileView,
    UserRegistrationView,
)


app_name = "accounts"

urlpatterns = [
    # Normal email/password registration
    # POST /api/auth/register/
    path(
        "auth/register/",
        UserRegistrationView.as_view(),
        name="register",
    ),

    # Google Login / Sign up
    # POST /api/auth/google/
    path(
        "auth/google/",
        GoogleAuthView.as_view(),
        name="google-auth",
    ),

    # Normal email/password login.
    # Returns OMAXAS AI access and refresh tokens.
    # POST /api/auth/token/
    path(
        "auth/token/",
        TokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),

    # Refresh an access token.
    # POST /api/auth/token/refresh/
    path(
        "auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),

    # Verify a JWT token.
    # POST /api/auth/token/verify/
    path(
        "auth/token/verify/",
        TokenVerifyView.as_view(),
        name="token_verify",
    ),

    # Current user's profile.
    # GET/PATCH /api/accounts/me/
    path(
        "accounts/me/",
        UserProfileView.as_view(),
        name="current_user",
    ),

    # Current user's preferences.
    # GET/PATCH /api/accounts/preferences/
    path(
        "accounts/preferences/",
        UserPreferenceView.as_view(),
        name="user_preferences",
    ),
]