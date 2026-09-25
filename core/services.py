"""Base class shared by the domain services."""

from typing import Any

from django.db import models

from core.exceptions import NotFoundException


class BaseService:
    """Common building blocks for domain services.

    Subclasses declare the model they operate on and expose their operations as
    classmethods, e.g. ``ListingService.create(...)``.
    """

    model: type[models.Model]

    @classmethod
    def get_object_or_raise(
        cls,
        pk: Any,
        *,
        message: str | None = None,
        queryset: models.QuerySet | None = None,
    ) -> models.Model:
        """Fetch a live object by primary key or raise a 404.

        Uses the model's default (soft delete aware) manager unless an explicit
        queryset is supplied, so soft deleted rows are never returned.

        Args:
            pk: Primary key of the object to fetch.
            message: Optional message for the raised ``NotFoundException``.
            queryset: Optional queryset to scope the lookup.

        Returns:
            The fetched object.

        Raises:
            NotFoundException: If the object does not exist or was soft deleted.
        """
        source = queryset if queryset is not None else cls.model.objects.all()
        try:
            return source.get(pk=pk)
        except (cls.model.DoesNotExist, ValueError, TypeError) as exc:
            detail = message or f"{cls.model._meta.verbose_name.title()} not found."
            raise NotFoundException(detail) from exc
