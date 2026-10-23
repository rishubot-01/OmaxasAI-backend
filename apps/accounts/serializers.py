from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import serializers

from .models import UserPreference


User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Validates normal email/password registration.
    Passwords are never returned in API responses.
    """

    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
        style={"input_type": "password"},
    )

    password_confirm = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
        min_length=8,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "password",
            "password_confirm",
        )
        read_only_fields = ("id",)

    def validate_email(self, value):
        email = value.strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )

        return email

    def validate(self, attrs):
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        if password != password_confirm:
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )

        candidate_user = User(
            email=attrs.get("email"),
            display_name=attrs.get("display_name", ""),
        )

        try:
            validate_password(password, user=candidate_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(
                {"password": list(exc.messages)}
            ) from exc

        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")

        return User.objects.create_user(
            password=password,
            **validated_data,
        )


class GoogleAuthSerializer(serializers.Serializer):
    """
    Validates the credential field received from Google Sign-In.

    The credential must be verified server-side before using
    any Google account information to create or authenticate a user.
    """

    credential = serializers.CharField(
        write_only=True,
        trim_whitespace=True,
        allow_blank=False,
    )


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Returns the current user's profile.
    Sensitive account fields cannot be modified here.
    """

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "display_name",
            "is_email_verified",
            "date_joined",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "email",
            "is_email_verified",
            "date_joined",
            "created_at",
            "updated_at",
        )


class UserPreferenceSerializer(serializers.ModelSerializer):
    """
    Validates user interface and assistant preferences.
    """

    class Meta:
        model = UserPreference
        fields = (
            "theme",
            "language",
            "default_mode",
            "web_search_enabled",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "created_at",
            "updated_at",
        )