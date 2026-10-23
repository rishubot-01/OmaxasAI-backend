
"""Reusable permission classes for the OmaxasAI REST API."""

from rest_framework.permissions import BasePermission, SAFE_METHODS


def _get_owner_id(obj):
    """Resolve an object's owner ID using common model conventions."""

    # Support either a related user object or a direct owner/user ID.
    for attribute in ("owner_id", "user_id"):
        owner_id = getattr(obj, attribute, None)
        if owner_id is not None:
            return owner_id

    for attribute in ("owner", "user"):
        owner = getattr(obj, attribute, None)
        if owner is not None:
            return getattr(owner, "pk", None)

    return None


class IsOwner(BasePermission):
    """
    Allow access only to the authenticated owner of an object.

    The object may use `owner`, `owner_id`, `user`, or `user_id`
    to represent ownership.
    """

    message = "You do not have permission to access this resource."

    def has_permission(self, request, view):
        """Require authentication before checking object ownership."""

        return bool(
            request.user
            and request.user.is_authenticated
        )

    def has_object_permission(self, request, view, obj):
        """Check whether the authenticated user owns the object."""

        if not request.user or not request.user.is_authenticated:
            return False

        owner_id = _get_owner_id(obj)

        return (
            owner_id is not None
            and owner_id == request.user.pk
        )


class IsOwnerOrReadOnly(BasePermission):
    """
    Allow safe read operations, but restrict writes to the owner.

    Use this only when the endpoint is intended to allow authenticated
    or public reads. The view's other permission classes should establish
    whether anonymous reads are allowed.
    """

    message = "Only the owner can modify this resource."

    def has_object_permission(self, request, view, obj):
        """Allow reads and restrict modifications to the owner."""

        if request.method in SAFE_METHODS:
            return True

        if not request.user or not request.user.is_authenticated:
            return False

        owner_id = _get_owner_id(obj)

        return (
            owner_id is not None
            and owner_id == request.user.pk
        )


class IsCurrentUser(BasePermission):
    """
    Allow access only when the requested object is the current user.

    Useful for endpoints that retrieve or update a user object directly,
    rather than an object containing an owner/user relationship.
    """

    message = "You can only access your own user profile."

    def has_permission(self, request, view):
        """Require an authenticated user."""

        return bool(
            request.user
            and request.user.is_authenticated
        )

    def has_object_permission(self, request, view, obj):
        """Require the object to represent the authenticated user."""

        if not request.user or not request.user.is_authenticated:
            return False

        return getattr(obj, "pk", None) == request.user.pk


class IsStaffOrReadOnly(BasePermission):
    """
    Allow safe reads according to the view's other permissions.

    Restrict unsafe methods to authenticated staff users.
    """

    message = "Staff permission is required to modify this resource."

    def has_permission(self, request, view):
        """Require staff status for write methods."""

        if request.method in SAFE_METHODS:
            return True

        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )

    def has_object_permission(self, request, view, obj):
        """Apply the same write rule at object level."""

        if request.method in SAFE_METHODS:
            return True

        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )

