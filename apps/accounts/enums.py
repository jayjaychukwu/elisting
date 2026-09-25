"""Enumerations for the accounts app."""

from django.db import models


class UserRole(models.TextChoices):
    """Roles a user can hold in the platform."""

    ADMIN = "admin", "Admin"
    AGENT = "agent", "Agent"
