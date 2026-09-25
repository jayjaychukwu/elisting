"""Custom user model used for both agents and administrators."""

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models

from apps.accounts.enums import UserRole
from core.models import BaseAbstractModel


class UserManager(DjangoUserManager):
    """User manager that hides soft deleted users from the default queryset."""

    def get_queryset(self):
        """Return live users only.

        Returns:
            A queryset filtered to ``deleted_at IS NULL``.
        """
        return super().get_queryset().filter(deleted_at__isnull=True)


class User(BaseAbstractModel, AbstractUser):
    """Application user.

    Extends ``AbstractUser`` so username/password/admin integration keep working
    out of the box, while adding a role, a unique email address and the audit /
    soft delete fields inherited from :class:`core.models.BaseAbstractModel`.
    """

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.AGENT,
        db_index=True,
    )
    phone_number = models.CharField(max_length=32, blank=True)

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        """Meta options inherited from ``AbstractUser``."""

        db_table = "users"

    def __str__(self) -> str:
        """Return a readable representation of the user."""
        return self.get_full_name() or self.username
