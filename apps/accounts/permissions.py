
from rest_framework.permissions import BasePermission


class IsCurrentUser(BasePermission):
    """
    Allow access only when the requested object is the
    currently authenticated user.
    """

    message = "You can access only your own user account."

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        return obj.pk == request.user.pk


class IsOwner(BasePermission):
    """
    Allow access only to objects belonging to the
    currently authenticated user.

    Supported ownership fields:
    - user
    - owner
    """

    message = "You can access only your own data."

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        user_id = getattr(obj, "user_id", None)
        owner_id = getattr(obj, "owner_id", None)

        return (
            user_id == request.user.pk
            or owner_id == request.user.pk
        )

