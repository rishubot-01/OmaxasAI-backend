from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    """
    Main OmaxasAI user account.

    Users can sign in using:
    - Email and password
    - Google authentication
    """

    username = None

    email = models.EmailField(
        unique=True,
        db_index=True,
    )

    display_name = models.CharField(
        max_length=80,
        blank=True,
    )

    is_email_verified = models.BooleanField(default=False)

    # Stable Google account identifier from the verified ID token.
    # NULL for users who have not linked a Google account.
    # A unique constraint prevents the same Google account from
    # being linked to multiple OMAXAS AI user accounts.
    google_sub = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email


class UserPreference(models.Model):
    """
    Stores an individual user's OmaxasAI preferences.
    """

    class Theme(models.TextChoices):
        SYSTEM = "system", "System"
        LIGHT = "light", "Light"
        DARK = "dark", "Dark"

    # Backward compatibility for code using ThemeChoices.
    ThemeChoices = Theme

    class ModeChoices(models.TextChoices):
        AUTO = "auto", "Auto"
        THINK = "think", "Think"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="preferences",
    )

    theme = models.CharField(
        max_length=10,
        choices=Theme.choices,
        default=Theme.SYSTEM,
    )

    language = models.CharField(
        max_length=10,
        default="en",
    )

    default_mode = models.CharField(
        max_length=10,
        choices=ModeChoices.choices,
        default=ModeChoices.AUTO,
    )

    web_search_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Preference"
        verbose_name_plural = "User Preferences"

    def __str__(self):
        return f"Preferences for {self.user.email}"