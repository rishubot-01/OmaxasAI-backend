
from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework.exceptions import ValidationError

from .models import UserPreference
from .serializers import UserRegistrationSerializer


User = get_user_model()


class UserManagerTests(TestCase):
    """Tests for creating regular and administrator accounts."""

    def test_create_user_normalizes_email(self):
        user = User.objects.create_user(
            email="Rishu@Example.com",
            password="StrongPass!8271",
        )

        self.assertEqual(user.email, "rishu@example.com")
        self.assertTrue(user.check_password("StrongPass!8271"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_password_is_not_stored_as_plain_text(self):
        password = "StrongPass!8271"

        user = User.objects.create_user(
            email="user@example.com",
            password=password,
        )

        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))

    def test_create_user_requires_email(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(
                email="",
                password="StrongPass!8271",
            )

    def test_create_superuser(self):
        admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="StrongPass!8271",
        )

        self.assertTrue(admin_user.is_staff)
        self.assertTrue(admin_user.is_superuser)


class UserPreferenceTests(TestCase):
    """Tests for default and custom user preferences."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="preferences@example.com",
            password="StrongPass!8271",
        )

    def test_create_default_preferences(self):
        preferences = UserPreference.objects.create(
            user=self.user,
        )

        self.assertEqual(preferences.theme, "system")
        self.assertEqual(preferences.language, "en")
        self.assertEqual(preferences.default_mode, "auto")
        self.assertFalse(preferences.web_search_enabled)

    def test_user_has_one_preferences_record(self):
        UserPreference.objects.create(user=self.user)

        with self.assertRaises(Exception):
            UserPreference.objects.create(user=self.user)


class UserRegistrationSerializerTests(TestCase):
    """Tests for signup data validation."""

    def test_valid_registration_creates_user(self):
        data = {
            "email": "newuser@example.com",
            "display_name": "Omaxas User",
            "password": "StrongPass!8271",
            "password_confirm": "StrongPass!8271",
        }

        serializer = UserRegistrationSerializer(data=data)

        self.assertTrue(serializer.is_valid(), serializer.errors)

        user = serializer.save()

        self.assertEqual(user.email, "newuser@example.com")
        self.assertTrue(user.check_password("StrongPass!8271"))
        self.assertNotIn("password", serializer.data)
        self.assertNotIn("password_confirm", serializer.data)

    def test_registration_rejects_mismatched_passwords(self):
        data = {
            "email": "newuser@example.com",
            "display_name": "Omaxas User",
            "password": "StrongPass!8271",
            "password_confirm": "DifferentPass!9271",
        }

        serializer = UserRegistrationSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("password_confirm", serializer.errors)

    def test_registration_rejects_duplicate_email(self):
        User.objects.create_user(
            email="existing@example.com",
            password="StrongPass!8271",
        )

        data = {
            "email": "EXISTING@example.com",
            "display_name": "Another User",
            "password": "StrongPass!8271",
            "password_confirm": "StrongPass!8271",
        }

        serializer = UserRegistrationSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("email", serializer.errors)

