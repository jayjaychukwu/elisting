"""Listing model with PostGIS backed coordinates."""

from django.conf import settings
from django.contrib.gis.db import models
from django.core.validators import MaxValueValidator, MinValueValidator

from apps.listings.enums import ListingType
from core.models import BaseAbstractModel


class Listing(BaseAbstractModel):
    """A property listing advertised by an agent.

    Coordinates are stored in a PostGIS ``PointField`` (``location``) which
    enables indexed radius searches. ``latitude``/``longitude`` properties give
    ergonomic access to the point components.
    """

    title = models.CharField(max_length=200)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    type = models.CharField(
        max_length=10,
        choices=ListingType.choices,
        db_index=True,
    )
    bedrooms = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    location_name = models.CharField(max_length=255)
    location = models.PointField(srid=4326, spatial_index=True)
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="listings",
    )

    class Meta:
        """Indexes and ordering for listing queries."""

        ordering = ("-created_at",)
        verbose_name_plural = "listings"
        indexes = [
            models.Index(fields=["type", "bedrooms"], name="listing_type_bedrooms_idx"),
            models.Index(fields=["price"], name="listing_price_idx"),
        ]

    def __str__(self) -> str:
        """Return the listing title."""
        return self.title

    @property
    def latitude(self) -> float | None:
        """Return the latitude component of ``location``."""
        return self.location.y if self.location else None

    @property
    def longitude(self) -> float | None:
        """Return the longitude component of ``location``."""
        return self.location.x if self.location else None
