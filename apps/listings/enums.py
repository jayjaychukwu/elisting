"""Enumerations for the listings app."""

from django.db import models


class ListingType(models.TextChoices):
    """The kind of listing offered to the market."""

    RENT = "rent", "Rent"
    SALE = "sale", "Sale"
    SHORTLET = "shortlet", "Shortlet"
