"""Permission classes for the listings API."""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAuthenticatedOrReadOnly(BasePermission):
    """Allow anonymous read access, require a JWT for any write."""

    def has_permission(self, request, view) -> bool:
        """Check whether the caller may perform the request.

        Args:
            request: Incoming request.
            view: The view being accessed.

        Returns:
            ``True`` for safe methods, otherwise whether the request is
            authenticated.
        """
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)
