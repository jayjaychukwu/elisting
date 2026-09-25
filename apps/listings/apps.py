"""App configuration for the listings app."""

from django.apps import AppConfig


class ListingsConfig(AppConfig):
    """Configuration for property listings."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.listings"
    label = "listings"
    verbose_name = "Listings"
