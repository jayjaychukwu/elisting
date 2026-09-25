"""User domain service."""

from typing import Any

from apps.accounts.enums import UserRole
from apps.accounts.models import User
from core.services import BaseService


class UserService(BaseService):
    """Operations on user accounts (agents and administrators).

    Kept free of HTTP concerns: callers (views, management commands, other
    services) handle request/response formatting, this class owns the rules.
    """

    model = User

    @classmethod
    def create(
        cls,
        *,
        username: str,
        email: str,
        password: str,
        role: str = UserRole.AGENT,
        actor: User | None = None,
        **extra_fields: Any,
    ) -> User:
        """Create a user with a hashed password and audit stamps.

        Args:
            username: Unique username.
            email: Unique email address.
            password: Raw password; hashed before storage.
            role: One of :class:`~apps.accounts.enums.UserRole`.
            actor: Optional user recorded in ``created_by``/``updated_by``.
            **extra_fields: Additional user model fields.

        Returns:
            The created user.
        """
        user = User(
            username=username,
            email=email,
            role=role,
            created_by=actor,
            updated_by=actor,
            **extra_fields,
        )
        user.set_password(password)
        user.save()
        return user

    @classmethod
    def get(cls, user_id: Any) -> User:
        """Return a live user by id.

        Args:
            user_id: Primary key of the user.

        Returns:
            The requested user.

        Raises:
            NotFoundException: If the user does not exist or was soft deleted.
        """
        return cls.get_object_or_raise(user_id, message="User not found.")

    @classmethod
    def is_admin(cls, user: Any) -> bool:
        """Check whether a user may act on behalf of the platform.

        Args:
            user: The user to inspect.

        Returns:
            ``True`` for superusers, staff members and users with the admin role.
        """
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_staff", False)
            or getattr(user, "role", None) == UserRole.ADMIN
        )
