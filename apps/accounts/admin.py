
from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField

from .models import User, UserPreference


class OmaxasAIUserCreationForm(forms.ModelForm):
    """Admin form for creating users with hashed passwords."""

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        strip=False,
    )

    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput,
        strip=False,
    )

    class Meta:
        model = User
        fields = ("email", "display_name")

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")

        return password2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()

        return user


class OmaxasAIUserChangeForm(forms.ModelForm):
    """Admin form for editing existing users safely."""

    password = ReadOnlyPasswordHashField(
        label="Password hash",
        help_text="Passwords cannot be viewed or edited directly.",
    )

    class Meta:
        model = User
        fields = (
            "email",
            "password",
            "display_name",
            "first_name",
            "last_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "is_email_verified",
            "groups",
            "user_permissions",
        )

    def clean_password(self):
        return self.initial["password"]


@admin.register(User)
class OmaxasAIUserAdmin(UserAdmin):
    """Admin configuration for OmaxasAI user accounts."""

    model = User
    form = OmaxasAIUserChangeForm
    add_form = OmaxasAIUserCreationForm

    list_display = (
        "email",
        "display_name",
        "is_email_verified",
        "is_active",
        "is_staff",
        "date_joined",
    )

    list_filter = (
        "is_active",
        "is_staff",
        "is_superuser",
        "is_email_verified",
    )

    search_fields = (
        "email",
        "display_name",
        "first_name",
        "last_name",
    )

    ordering = ("email",)
    filter_horizontal = ("groups", "user_permissions")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal information",
            {"fields": ("display_name", "first_name", "last_name")},
        ),
        ("Email verification", {"fields": ("is_email_verified",)}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "display_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    readonly_fields = (
        "last_login",
        "date_joined",
        "created_at",
        "updated_at",
    )


@admin.register(UserPreference)
class UserPreferenceAdmin(admin.ModelAdmin):
    """Admin configuration for user preferences."""

    list_display = (
        "user",
        "theme",
        "language",
        "default_mode",
        "web_search_enabled",
        "updated_at",
    )

    list_filter = (
        "theme",
        "default_mode",
        "web_search_enabled",
    )

    search_fields = ("user__email", "user__display_name")
    list_select_related = ("user",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

