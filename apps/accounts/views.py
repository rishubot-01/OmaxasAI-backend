import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.tokens import RefreshToken

from .models import UserPreference
from .serializers import (
    GoogleAuthSerializer,
    UserPreferenceSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
)


logger = logging.getLogger(__name__)

User = get_user_model()


class UserRegistrationView(generics.CreateAPIView):
    """
    Register a new OmaxasAI user.

    Public endpoint:
        POST /api/auth/register/
    """

    serializer_class = UserRegistrationSerializer
    permission_classes = [AllowAny]

    @transaction.atomic
    def perform_create(self, serializer):
        # Create the user and default preferences together.
        user = serializer.save()

        UserPreference.objects.get_or_create(
            user=user,
        )


class GoogleAuthView(APIView):
    """
    Verify a Google ID token and authenticate an OmaxasAI user.

    Public endpoint:
        POST /api/auth/google/

    Request:
        {
            "credential": "<Google ID token>"
        }

    Success response:
        {
            "access": "<OmaxasAI access token>",
            "refresh": "<OmaxasAI refresh token>",
            "user": {
                "id": 1,
                "email": "user@example.com",
                "display_name": "Example User"
            }
        }
    """

    permission_classes = [AllowAny]

    # Do not let an expired or stale OMAXAS Authorization header
    # block this public sign-in endpoint.
    authentication_classes = []

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        credential = serializer.validated_data["credential"]

        # Read the Web application Client ID from server settings.
        client_id = getattr(
            settings,
            "GOOGLE_CLIENT_ID",
            "",
        ).strip()

        if not client_id:
            logger.error(
                "Google authentication attempted without "
                "GOOGLE_CLIENT_ID configuration."
            )

            return Response(
                {
                    "detail": (
                        "Google Sign in is not configured on the server."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Import lazily so missing Google dependencies do not prevent
        # Django from importing the accounts app.
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token

        except ImportError:
            logger.error(
                "Google authentication dependency is not installed."
            )

            return Response(
                {
                    "detail": (
                        "Google Sign in is unavailable because a "
                        "server dependency is missing."
                    )
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Verify the token signature, issuer, expiry and audience.
        # Never trust profile details supplied separately by the client.
        try:
            google_info = id_token.verify_oauth2_token(
                credential,
                google_requests.Request(),
                client_id,
            )

        except ValueError:
            return Response(
                {
                    "detail": (
                        "Invalid or expired Google credential. "
                        "Please try signing in again."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                "Google ID-token verification failed."
            )

            return Response(
                {
                    "detail": (
                        "Google verification is temporarily unavailable. "
                        "Please try again."
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Take identity details only from the verified Google token.
        google_sub = str(
            google_info.get("sub") or ""
        ).strip()

        email = str(
            google_info.get("email") or ""
        ).strip().lower()

        display_name = str(
            google_info.get("name") or ""
        ).strip()[:80]

        email_verified = (
            google_info.get("email_verified") is True
        )

        if not google_sub or not email or "@" not in email:
            return Response(
                {
                    "detail": (
                        "Google did not return a valid account identity."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not email_verified:
            return Response(
                {
                    "detail": (
                        "Your Google email must be verified "
                        "before signing in."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not display_name:
            display_name = email.split("@", 1)[0][:80]

        # Google is authoritative for Gmail addresses and for verified
        # Google Workspace accounts containing the "hd" claim.
        hosted_domain = google_info.get("hd")

        google_authoritative_email = (
            email.endswith("@gmail.com")
            or (
                email_verified
                and isinstance(hosted_domain, str)
                and bool(hosted_domain.strip())
            )
        )

        try:
            with transaction.atomic():
                # The stable Google subject is the primary way to find
                # an existing Google-linked account.
                user = User.objects.filter(
                    google_sub=google_sub
                ).first()

                if user is None:
                    # Look for an existing OMAXAS AI account with
                    # the same email address.
                    existing_user = User.objects.filter(
                        email__iexact=email
                    ).first()

                    if existing_user is not None:
                        existing_sub = getattr(
                            existing_user,
                            "google_sub",
                            None,
                        )

                        # Do not silently link a Google identity that
                        # conflicts with another existing Google link.
                        if (
                            existing_sub
                            and existing_sub != google_sub
                        ):
                            return Response(
                                {
                                    "detail": (
                                        "This email is already linked to "
                                        "a different Google account."
                                    )
                                },
                                status=status.HTTP_409_CONFLICT,
                            )

                        # For non-authoritative email domains, require
                        # the user to sign in to the existing account
                        # before linking Google in a separate flow.
                        if (
                            not existing_sub
                            and not google_authoritative_email
                        ):
                            return Response(
                                {
                                    "detail": (
                                        "An account with this email "
                                        "already exists. Sign in using "
                                        "your password before linking "
                                        "Google."
                                    )
                                },
                                status=status.HTTP_409_CONFLICT,
                            )

                        # A verified, authoritative Google email may
                        # be linked to the matching existing account.
                        user = existing_user

                    else:
                        # Create a Google-only account with an unusable
                        # password. A password can be set separately
                        # through a secure account recovery flow.
                        user = User.objects.create_user(
                            email=email,
                            display_name=display_name,
                            password=None,
                        )

                # Never issue tokens for disabled user accounts.
                if not user.is_active:
                    return Response(
                        {
                            "detail": (
                                "This OMAXAS AI account is disabled. "
                                "Please contact support."
                            )
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                fields_to_update = []

                # Link the stable Google subject to this user.
                current_google_sub = getattr(
                    user,
                    "google_sub",
                    None,
                )

                if current_google_sub != google_sub:
                    user.google_sub = google_sub
                    fields_to_update.append("google_sub")

                # This value comes from the verified Google token.
                if (
                    hasattr(user, "is_email_verified")
                    and not user.is_email_verified
                ):
                    user.is_email_verified = True
                    fields_to_update.append("is_email_verified")

                # Populate an empty display name without overwriting
                # a name the existing user has already chosen.
                if (
                    hasattr(user, "display_name")
                    and not user.display_name
                    and display_name
                ):
                    user.display_name = display_name
                    fields_to_update.append("display_name")

                if fields_to_update:
                    user.save(
                        update_fields=list(set(fields_to_update))
                    )

                # Create default preferences for newly created users
                # and repair missing preferences for existing users.
                UserPreference.objects.get_or_create(
                    user=user,
                )

        except IntegrityError:
            # Handle races where another request creates or links
            # the same email address or Google subject.
            logger.warning(
                "Google account creation/linking conflict."
            )

            return Response(
                {
                    "detail": (
                        "The account could not be created or linked "
                        "because it already exists. Please try signing "
                        "in again."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Issue OMAXAS AI JWTs, not Google's ID token.
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.pk,
                    "email": user.email,
                    "display_name": user.display_name,
                },
            },
            status=status.HTTP_200_OK,
        )


class UserProfileView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the authenticated user's profile.

    Protected endpoints:
        GET   /api/accounts/me/
        PATCH /api/accounts/me/
    """

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        # A user can access only their own profile.
        return self.request.user


class UserPreferenceView(generics.RetrieveUpdateAPIView):
    """
    Retrieve or update the authenticated user's preferences.

    Protected endpoints:
        GET   /api/accounts/preferences/
        PATCH /api/accounts/preferences/
    """

    serializer_class = UserPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        preferences, _ = UserPreference.objects.get_or_create(
            user=self.request.user,
        )

        return preferences