"""Tests for the cache primitives and listing search caching."""

from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point

from apps.listings.enums import ListingType
from apps.listings.services import ListingService
from core.cache import CacheManager, CacheNameSpaces

pytestmark = pytest.mark.django_db

LEKKI = {"lat": 6.4474, "lng": 3.4735, "has_geo_filter": True}


def _payload(agent, **overrides) -> dict:
    """Return a valid create payload owned by an agent.

    Args:
        agent: The owning agent.
        **overrides: Fields to override.

    Returns:
        A dictionary suitable for ``ListingService.create``.
    """
    data = {
        "title": "Cached listing",
        "price": Decimal("500000.00"),
        "type": ListingType.RENT,
        "bedrooms": 2,
        "location_name": "Lekki",
        "location": Point(3.4735, 6.4474, srid=4326),
    }
    data.update(overrides)
    return data


def _metres(listing) -> float | None:
    """Return a listing's distance in metres, whatever form it arrives in."""
    distance = getattr(listing, "distance", None)
    if distance is None:
        return None
    return float(distance.m if hasattr(distance, "m") else distance)


class TestCacheManager:
    """Tests for :class:`~core.cache.CacheManager`."""

    def test_make_key_is_namespaced_and_deterministic(self):
        first = CacheManager.make_key(CacheNameSpaces.LISTING_SEARCH, "type=rent")
        second = CacheManager.make_key(CacheNameSpaces.LISTING_SEARCH, "type=rent")

        assert first == second
        assert first.startswith(f"{CacheNameSpaces.LISTING_SEARCH}:")

    def test_make_key_hashes_multiple_parts(self):
        key = CacheManager.make_key(CacheNameSpaces.LISTING_SEARCH, "type=rent", "bedrooms=3")

        assert key.count(":") == 2
        assert "type=rent" not in key

    def test_get_or_set_computes_once(self):
        calls = []

        def factory():
            calls.append(1)
            return ["value"]

        key = CacheManager.make_key(CacheNameSpaces.LISTING_SEARCH, "get-or-set")
        first = CacheManager.get_or_set(key, factory, ttl=30)
        second = CacheManager.get_or_set(key, factory, ttl=30)

        assert first == second == ["value"]
        assert len(calls) == 1

    def test_clear_namespace_removes_registered_keys(self):
        namespace = "tests:namespace"
        kept = CacheManager.make_key("tests:other", "kept")
        first = CacheManager.make_key(namespace, "one")
        second = CacheManager.make_key(namespace, "two")
        CacheManager.set(first, 1, ttl=30)
        CacheManager.set(second, 2, ttl=30)
        CacheManager.set(kept, 3, ttl=30)

        removed = CacheManager.clear_namespace(namespace)

        assert removed == 2
        assert CacheManager.get(first) is None
        assert CacheManager.get(second) is None
        assert CacheManager.get(kept) == 3


class TestListingSearchCaching:
    """Tests for search caching and invalidation in :class:`ListingService`."""

    def test_first_search_populates_the_cache(self, make_listing, django_assert_num_queries):
        make_listing()

        with django_assert_num_queries(1):
            ListingService.search(type=ListingType.RENT)

        assert CacheManager.get(ListingService._search_cache_key({"type": ListingType.RENT}))

    def test_repeated_search_is_served_from_cache(self, make_listing, django_assert_num_queries):
        near = make_listing(location=Point(3.4735, 6.4474, srid=4326))
        make_listing(location=Point(3.4219, 6.4281, srid=4326))
        filters = {"type": ListingType.RENT, **LEKKI, "radius_km": Decimal("10")}

        first = ListingService.search(**filters)
        # A hit rebuilds rows with one primary key query; no spatial work re-runs.
        with django_assert_num_queries(1):
            second = ListingService.search(**filters)

        assert [listing.id for listing in second] == [listing.id for listing in first]
        assert second[0].id == near.id
        assert second[0].distance == 0.0

    def test_cached_distances_survive_the_round_trip(self, make_listing):
        make_listing(location=Point(3.4735, 6.4474, srid=4326))
        make_listing(location=Point(3.4219, 6.4281, srid=4326))
        filters = {"type": ListingType.RENT, **LEKKI, "radius_km": Decimal("10")}

        first = ListingService.search(**filters)
        second = ListingService.search(**filters)

        assert [_metres(listing) for listing in second] == [_metres(listing) for listing in first]

    def test_different_filters_use_different_cache_entries(self, make_listing):
        rent = make_listing(type=ListingType.RENT)
        sale = make_listing(type=ListingType.SALE)

        assert ListingService.search(type=ListingType.RENT)[0].id == rent.id
        assert ListingService.search(type=ListingType.SALE)[0].id == sale.id

    def test_create_invalidates_cached_search(self, agent, make_listing):
        make_listing(type=ListingType.SALE)
        before = ListingService.search(type=ListingType.SALE)

        ListingService.create(data=_payload(agent, type=ListingType.SALE), actor=agent)
        after = ListingService.search(type=ListingType.SALE)

        assert len(before) == 1
        assert len(after) == 2

    def test_update_invalidates_cached_search(self, agent, make_listing):
        make_listing(type=ListingType.SALE, bedrooms=1)
        assert ListingService.search(type=ListingType.SALE, bedrooms=1)

        listing = make_listing(type=ListingType.SALE, bedrooms=1)
        ListingService.update(
            listing_id=listing.id, data={"bedrooms": 5}, actor=agent, partial=True
        )
        results = ListingService.search(type=ListingType.SALE, bedrooms=5)

        assert [row.id for row in results] == [listing.id]

    def test_delete_invalidates_cached_search(self, agent, make_listing):
        listing = make_listing(type=ListingType.SALE)
        assert len(ListingService.search(type=ListingType.SALE)) == 1

        ListingService.delete(listing_id=listing.id, actor=agent)

        assert ListingService.search(type=ListingType.SALE) == []


class TestCachedSearchEndpoint:
    """Integration coverage for the cached search endpoint."""

    def test_repeated_search_requests_return_identical_payloads(
        self, api_client, make_listing, django_assert_num_queries
    ):
        make_listing()
        url = "/api/v1/listings/search/?type=rent&lat=6.4474&lng=3.4735&radius_km=10"

        first = api_client.get(url)
        with django_assert_num_queries(1):
            second = api_client.get(url)

        assert first.status_code == second.status_code == 200
        assert first.data == second.data
