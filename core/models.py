"""Abstract base model providing auditing and soft deletion for every model."""

import uuid
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.managers import AllObjectsManager, DeletedObjectsManager, SoftDeleteManager


class BaseAbstractModel(models.Model):
    """Base model with UUID primary key, audit timestamps and soft deletion.

    Concrete models inherit three managers:

    * ``objects`` - live rows only (the default used by the API),
    * ``all_objects`` - live and soft deleted rows (admin, audit, tests),
    * ``deleted_objects`` - soft deleted rows only (restore flows).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_updated",
    )
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_deleted",
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()
    deleted_objects = DeletedObjectsManager()

    class Meta:
        """Meta options for the abstract base model."""

        abstract = True

    def soft_delete(self, user: Any = None) -> "BaseAbstractModel":
        """Mark the instance as deleted without removing the row.

        Args:
            user: Optional actor stored in ``deleted_by``.

        Returns:
            The soft deleted instance.
        """
        if self.deleted_at is None:
            self.deleted_at = timezone.now()
            self.deleted_by = user if getattr(user, "is_authenticated", False) else None
            self.save(update_fields=["deleted_at", "deleted_by", "updated_at"])
        return self

    def restore(self, user: Any = None) -> "BaseAbstractModel":
        """Undo a soft delete and return the instance to the live table view.

        Args:
            user: Optional actor stored in ``updated_by``.

        Returns:
            The restored instance.
        """
        if self.deleted_at is not None:
            self.deleted_at = None
            self.deleted_by = None
            if getattr(user, "is_authenticated", False):
                self.updated_by = user
            self.save(update_fields=["deleted_at", "deleted_by", "updated_at", "updated_by"])
        return self

    def delete(
        self,
        using: str | None = None,
        keep_parents: bool = False,
        user: Any = None,
        hard: bool = False,
    ) -> tuple[int, dict[str, int]]:
        """Soft delete the instance by default; permanently delete on request.

        Args:
            using: Database alias, kept for Django compatibility.
            keep_parents: Kept for Django compatibility.
            user: Optional actor stored in ``deleted_by``.
            hard: When ``True`` the row is physically removed.

        Returns:
            A ``(number_deleted, per_object_dict)`` tuple like Django's API.
        """
        if hard:
            return super().delete(using=using, keep_parents=keep_parents)
        self.soft_delete(user=user)
        return 1, {self._meta.label: 1}

    def __str__(self) -> str:
        """Return a readable representation of the instance."""
        return f"{self._meta.verbose_name} {self.pk}"
