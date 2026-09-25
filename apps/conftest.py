"""Shared pytest fixtures for the whole project."""

from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.enums import UserRole
from apps.accounts.models import User
from apps.listings.enums import ListingType
from apps.listings.models import Listing

PASSWORD = "TestPass123!"


@pytest.fixture(autouse=True)
def clear_test_cache():
    """Keep cached search results from leaking between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def agent(db) -> User:
    """Return the primary agent used as the acting user."""
    return User.objects.create_user(
        username="agent1",
        email="agent1@example.com",
        password=PASSWORD,
        role=UserRole.AGENT,
    )


@pytest.fixture
def other_agent(db) -> User:
    """Return a second agent used to test ownership rules."""
    return User.objects.create_user(
        username="agent2",
        email="agent2@example.com",
        password=PASSWORD,
        role=UserRole.AGENT,
    )


@pytest.fixture
def admin_user(db) -> User:
    """Return an administrator with full permissions."""
    return User.objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password=PASSWORD,
        role=UserRole.ADMIN,
    )


@pytest.fixture
def api_client() -> APIClient:
    """Return an anonymous API client."""
    return APIClient()


@pytest.fixture
def auth_client(agent) -> APIClient:
    """Return an API client authenticated as the primary agent."""
    client = APIClient()
    client.force_authenticate(user=agent)
    return client


@pytest.fixture
def listing_payload() -> dict:
    """Return a valid create payload for a listing."""
    return {
        "title": "Sunny 2 bedroom flat",
        "price": "750000.00",
        "type": ListingType.RENT,
        "bedrooms": 2,
        "location_name": "Admiralty Way, Lekki",
        "latitude": 6.4474,
        "longitude": 3.4735,
    }


@pytest.fixture
def make_listing(agent):
    """Return a factory creating listings, defaulting to the primary agent.

    Args:
        agent: The owning agent.

    Returns:
        A callable accepting keyword overrides and returning a ``Listing``.
    """

    def _factory(**overrides) -> Listing:
        defaults = {
            "title": "Test listing",
            "price": Decimal("1000000.00"),
            "type": ListingType.RENT,
            "bedrooms": 2,
            "location_name": "Lekki",
            "location": Point(3.4735, 6.4474, srid=4326),
            "agent": agent,
            "created_by": agent,
            "updated_by": agent,
        }
        defaults.update(overrides)
        return Listing.objects.create(**defaults)

    return _factory
