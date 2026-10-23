
from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """
    Custom user manager for OmaxasAI.
    Users authenticate using their email address.
    """

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email address is required.")

        email = self.normalize_email(email.strip()).lower()

        user = self.model(
            email=email,
            **extra_fields,
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create a regular OmaxasAI user."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        if extra_fields.get("is_staff"):
            raise ValueError("Regular users cannot be staff.")

        if extra_fields.get("is_superuser"):
            raise ValueError("Regular users cannot be superusers.")

        return self._create_user(
            email,
            password,
            **extra_fields,
        )

    def create_superuser(self, email, password=None, **extra_fields):
        """Create an OmaxasAI administrator."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError(
                "A superuser must have is_superuser=True."
            )

        if not password:
            raise ValueError("A superuser password is required.")

        return self._create_user(
            email,
            password,
            **extra_fields,
        )
