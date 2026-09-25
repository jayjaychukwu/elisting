"""Queryset and manager implementations used by soft deletable models."""

from django.db import models
from django.utils import timezone


class AllObjectsQuerySet(models.QuerySet):
    """Queryset that includes soft deleted rows."""

    def hard_delete(self) -> int:
        """Permanently delete every row in the queryset.

        Returns:
            Number of rows physically deleted.
        """
        return super().delete()[0]

    def restore(self) -> int:
        """Clear the soft delete markers for every row in the queryset.

        Returns:
            Number of restored rows.
        """
        return self.update(deleted_at=None, deleted_by=None)


class SoftDeleteQuerySet(AllObjectsQuerySet):
    """Queryset for models that are soft deleted."""

    def delete(self, user: models.Model | None = None) -> int:
        """Soft delete every row in the queryset instead of removing rows.

        Args:
            user: Optional actor recorded in ``deleted_by``.

        Returns:
            Number of rows soft deleted.
        """
        deleted_by = user if getattr(user, "is_authenticated", False) else None
        return self.update(deleted_at=timezone.now(), deleted_by=deleted_by)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager exposing only rows that have not been deleted."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        """Return a queryset filtered to live rows.

        Returns:
            A ``SoftDeleteQuerySet`` limited to ``deleted_at IS NULL``.
        """
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager.from_queryset(AllObjectsQuerySet)):
    """Manager exposing live and soft deleted rows (used by admin and tests)."""


class DeletedObjectsManager(models.Manager.from_queryset(AllObjectsQuerySet)):
    """Manager exposing only soft deleted rows."""

    def get_queryset(self) -> AllObjectsQuerySet:
        """Return a queryset limited to soft deleted rows.

        Returns:
            An ``AllObjectsQuerySet`` filtered to deleted rows.
        """
        return super().get_queryset().filter(deleted_at__isnull=False)
