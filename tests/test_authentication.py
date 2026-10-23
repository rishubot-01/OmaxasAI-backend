
"""Authentication and account integration tests for OmaxasAI."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserPreference

User = get_user_model()


class UserRegistrationTests(APITestCase):
    """Test registration, password validation, and duplicate accounts."""

    register_url = "/api/auth/register/"

    def valid_registration_data(self, **overrides):
        """Return valid registration input with optional overrides."""

        data = {
            "email": "newuser@example.com",
            "password": "VeryStrongPass!9275",
            "password_confirm": "VeryStrongPass!9275",
            "display_name": "Test User",
        }
        data.update(overrides)
        return data

    def test_registration_creates_user(self):
        response = self.client.post(
            self.register_url,
            self.valid_registration_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        user = User.objects.get(email="newuser@example.com")

        self.assertEqual(user.display_name, "Test User")
        self.assertTrue(user.check_password("VeryStrongPass!9275"))
        self.assertNotEqual(user.password, "VeryStrongPass!9275")

    def test_registration_creates_default_preferences(self):
        response = self.client.post(
            self.register_url,
            self.valid_registration_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        user = User.objects.get(email="newuser@example.com")

        self.assertTrue(
            UserPreference.objects.filter(user=user).exists()
        )

    def test_registration_normalizes_email(self):
        response = self.client.post(
            self.register_url,
            self.valid_registration_data(
                email="NewUser@Example.COM",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_201_CREATED,
            response.data,
        )

        self.assertTrue(
            User.objects.filter(email="newuser@example.com").exists()
        )

    def test_registration_rejects_mismatched_passwords(self):
        response = self.client.post(
            self.register_url,
            self.valid_registration_data(
                password_confirm="DifferentStrongPass!8275",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            User.objects.filter(email="newuser@example.com").exists()
        )

    def test_registration_rejects_duplicate_email(self):
        User.objects.create_user(
            email="newuser@example.com",
            password="ExistingStrongPass!9275",
        )

        response = self.client.post(
            self.register_url,
            self.valid_registration_data(),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertEqual(
            User.objects.filter(email="newuser@example.com").count(),
            1,
        )

    def test_registration_rejects_missing_required_fields(self):
        response = self.client.post(
            self.register_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_registration_rejects_weak_password(self):
        response = self.client.post(
            self.register_url,
            self.valid_registration_data(
                password="123",
                password_confirm="123",
            ),
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

        self.assertFalse(
            User.objects.filter(email="newuser@example.com").exists()
        )


class JWTAuthenticationTests(APITestCase):
    """Test JWT login, refresh, token verification, and bad credentials."""

    token_url = "/api/auth/token/"
    refresh_url = "/api/auth/token/refresh/"
    verify_url = "/api/auth/token/verify/"

    def setUp(self):
        self.password = "LoginStrongPass!9275"

        self.user = User.objects.create_user(
            email="login@example.com",
            password=self.password,
        )

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            self.token_url,
            {
                "email": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        self.assertTrue(response.data["access"])
        self.assertTrue(response.data["refresh"])

    def test_login_rejects_incorrect_password(self):
        response = self.client.post(
            self.token_url,
            {
                "email": self.user.email,
                "password": "IncorrectPassword!9275",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_login_rejects_unknown_email(self):
        response = self.client.post(
            self.token_url,
            {
                "email": "unknown@example.com",
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_refresh_endpoint_returns_new_access_token(self):
        login_response = self.client.post(
            self.token_url,
            {
                "email": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            login_response.status_code,
            status.HTTP_200_OK,
            login_response.data,
        )

        refresh_token = login_response.data["refresh"]

        response = self.client.post(
            self.refresh_url,
            {"refresh": refresh_token},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.assertIn("access", response.data)

    def test_verify_endpoint_accepts_valid_access_token(self):
        login_response = self.client.post(
            self.token_url,
            {
                "email": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            login_response.status_code,
            status.HTTP_200_OK,
            login_response.data,
        )

        response = self.client.post(
            self.verify_url,
            {"token": login_response.data["access"]},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

    def test_verify_endpoint_rejects_invalid_token(self):
        response = self.client.post(
            self.verify_url,
            {"token": "not-a-valid-jwt"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )


class ProtectedAccountAPITests(APITestCase):
    """Test authentication and access to the current user's account."""

    profile_url = "/api/accounts/me/"
    preferences_url = "/api/accounts/preferences/"
    token_url = "/api/auth/token/"

    def setUp(self):
        self.password = "AccountStrongPass!9275"

        self.user = User.objects.create_user(
            email="account@example.com",
            password=self.password,
            display_name="Account User",
        )

        UserPreference.objects.get_or_create(user=self.user)

    def authenticate_client(self):
        """Log in and attach a JWT access token to the test client."""

        response = self.client.post(
            self.token_url,
            {
                "email": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {response.data['access']}"
        )

    def test_profile_rejects_unauthenticated_request(self):
        response = self.client.get(self.profile_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_authenticated_user_can_get_profile(self):
        self.authenticate_client()

        response = self.client.get(self.profile_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.assertEqual(response.data["email"], self.user.email)

    def test_authenticated_user_can_update_display_name(self):
        self.authenticate_client()

        response = self.client.patch(
            self.profile_url,
            {"display_name": "Updated Display Name"},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.user.refresh_from_db()

        self.assertEqual(
            self.user.display_name,
            "Updated Display Name",
        )

    def test_preferences_reject_unauthenticated_request(self):
        response = self.client.get(self.preferences_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_authenticated_user_can_get_preferences(self):
        self.authenticate_client()

        response = self.client.get(self.preferences_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        self.assertEqual(
            response.data["theme"],
            UserPreference.Theme.SYSTEM,
        )

    def test_authenticated_user_can_update_theme(self):
        self.authenticate_client()

        response = self.client.patch(
            self.preferences_url,
            {"theme": UserPreference.Theme.DARK},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            response.data,
        )

        preference = UserPreference.objects.get(user=self.user)

        self.assertEqual(
            preference.theme,
            UserPreference.Theme.DARK,
        )


class PasswordSecurityTests(TestCase):
    """Test password storage properties."""

    def test_password_is_not_stored_as_plain_text(self):
        password = "StorageStrongPass!9275"

        user = User.objects.create_user(
            email="password-storage@example.com",
            password=password,
        )

        user.refresh_from_db()

        self.assertNotEqual(user.password, password)
        self.assertTrue(user.check_password(password))

    def test_wrong_password_does_not_authenticate_user(self):
        user = User.objects.create_user(
            email="wrong-password@example.com",
            password="CorrectStrongPass!9275",
        )

        self.assertFalse(
            user.check_password("WrongStrongPass!9275")
        )

