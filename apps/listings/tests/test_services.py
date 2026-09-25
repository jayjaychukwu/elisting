"""Unit tests for the listing service layer."""

from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point

from apps.listings.enums import ListingType
from apps.listings.models import Listing
from apps.listings.services import ListingService
from core.exceptions import NotFoundException, PermissionDeniedException, ValidationException

pytestmark = pytest.mark.django_db


def _payload(**overrides) -> dict:
    """Return a valid service payload.

    Args:
        **overrides: Fields to override.

    Returns:
        A dictionary suitable for the create/update service methods.
    """
    data = {
        "title": "Service level flat",
        "price": Decimal("500000.00"),
        "type": ListingType.RENT,
        "bedrooms": 2,
        "location_name": "Lekki",
        "location": Point(3.4735, 6.4474, srid=4326),
    }
    data.update(overrides)
    return data


class TestListingServiceCreate:
    """Tests for :meth:`ListingService.create`."""

    def test_creates_listing_owned_by_actor_with_audit_fields(self, agent):
        listing = ListingService.create(data=_payload(), actor=agent)

        assert listing.agent == agent
        assert listing.created_by == agent
        assert listing.updated_by == agent
        assert listing.latitude == 6.4474
        assert listing.longitude == 3.4735

    def test_agent_cannot_assign_listing_to_another_agent(self, agent, other_agent):
        with pytest.raises(PermissionDeniedException):
            ListingService.create(data=_payload(agent=other_agent), actor=agent)

    def test_admin_can_assign_listing_to_another_agent(self, admin_user, agent):
        listing = ListingService.create(data=_payload(agent=agent), actor=admin_user)

        assert listing.agent == agent
        assert listing.created_by == admin_user


class TestListingServiceUpdate:
    """Tests for :meth:`ListingService.update`."""

    def test_owner_can_update_listing(self, agent, make_listing):
        listing = make_listing()

        updated = ListingService.update(
            listing_id=listing.id,
            data=_payload(title="Updated title"),
            actor=agent,
        )

        assert updated.title == "Updated title"
        assert updated.updated_by == agent

    def test_non_owner_cannot_update_listing(self, agent, other_agent, make_listing):
        listing = make_listing()

        with pytest.raises(PermissionDeniedException):
            ListingService.update(
                listing_id=listing.id,
                data=_payload(title="Hijacked"),
                actor=other_agent,
            )

    def test_admin_can_update_any_listing(self, admin_user, agent, make_listing):
        listing = make_listing()

        updated = ListingService.update(
            listing_id=listing.id,
            data=_payload(title="Admin edit"),
            actor=admin_user,
        )

        assert updated.title == "Admin edit"
        assert updated.updated_by == admin_user

    def test_full_update_requires_location(self, agent, make_listing):
        listing = make_listing()
        data = _payload()
        data.pop("location")

        with pytest.raises(ValidationException):
            ListingService.update(listing_id=listing.id, data=data, actor=agent, partial=False)

    def test_partial_update_without_location_keeps_geometry(self, agent, make_listing):
        listing = make_listing()

        updated = ListingService.update(
            listing_id=listing.id,
            data={"price": Decimal("75000.00")},
            actor=agent,
            partial=True,
        )

        assert updated.price == Decimal("75000.00")
        assert updated.location == listing.location

    def test_agent_cannot_reassign_listing(self, agent, other_agent, make_listing):
        listing = make_listing()

        with pytest.raises(PermissionDeniedException):
            ListingService.update(
                listing_id=listing.id,
                data={"agent": other_agent},
                actor=agent,
                partial=True,
            )

    def test_missing_listing_raises_not_found(self, agent):
        with pytest.raises(NotFoundException):
            ListingService.update(
                listing_id="00000000-0000-0000-0000-000000000000",
                data=_payload(),
                actor=agent,
            )


class TestListingServiceDelete:
    """Tests for :meth:`ListingService.delete`."""

    def test_soft_delete_hides_listing_from_default_manager(self, agent, make_listing):
        listing = make_listing()

        deleted = ListingService.delete(listing_id=listing.id, actor=agent)

        assert deleted.deleted_at is not None
        assert deleted.deleted_by == agent
        assert not Listing.objects.filter(pk=listing.id).exists()
        assert Listing.all_objects.filter(pk=listing.id).exists()

    def test_soft_deleted_listing_cannot_be_fetched(self, agent, make_listing):
        listing = make_listing()
        ListingService.delete(listing_id=listing.id, actor=agent)

        with pytest.raises(NotFoundException):
            ListingService.get(listing_id=listing.id)

    def test_non_owner_cannot_delete_listing(self, agent, other_agent, make_listing):
        listing = make_listing()

        with pytest.raises(PermissionDeniedException):
            ListingService.delete(listing_id=listing.id, actor=other_agent)


class TestListingServiceSearch:
    """Tests for :meth:`ListingService.search` and :meth:`ListingService.list`."""

    def test_list_returns_live_listings_newest_first(self, agent, make_listing):
        first = make_listing()
        second = make_listing()

        assert [listing.id for listing in ListingService.list()] == [second.id, first.id]

    def test_filters_by_type(self, make_listing):
        make_listing(type=ListingType.RENT)
        sale = make_listing(type=ListingType.SALE)

        results = ListingService.search(type=ListingType.SALE)

        assert [listing.id for listing in results] == [sale.id]

    def test_filters_by_price_range(self, make_listing):
        cheap = make_listing(price=Decimal("100000.00"))
        make_listing(price=Decimal("900000.00"))

        results = ListingService.search(
            min_price=Decimal("50000.00"), max_price=Decimal("200000.00")
        )

        assert [listing.id for listing in results] == [cheap.id]

    def test_filters_by_exact_and_minimum_bedrooms(self, make_listing):
        one = make_listing(bedrooms=1)
        make_listing(bedrooms=4)

        assert [listing.id for listing in ListingService.search(bedrooms=1)] == [one.id]
        assert {listing.bedrooms for listing in ListingService.search(bedrooms_min=2)} == {4}

    def test_radius_filter_returns_only_nearby_listings(self, make_listing):
        near = make_listing(location=Point(3.4735, 6.4474, srid=4326))  # Lekki
        make_listing(location=Point(3.3200, 6.6200, srid=4326))  # Agege, ~30km away

        results = ListingService.search(
            lat=6.4474, lng=3.4735, radius_km=Decimal("5"), has_geo_filter=True
        )

        assert [listing.id for listing in results] == [near.id]

    def test_radius_results_are_ordered_by_distance(self, make_listing):
        far = make_listing(location=Point(3.4219, 6.4281, srid=4326))  # VI, ~3.4km
        near = make_listing(location=Point(3.4735, 6.4474, srid=4326))  # Lekki, 0km

        results = list(
            ListingService.search(
                lat=6.4474, lng=3.4735, radius_km=Decimal("10"), has_geo_filter=True
            )
        )

        assert [listing.id for listing in results] == [near.id, far.id]
        assert results[0].distance < results[1].distance

    def test_soft_deleted_listings_are_excluded(self, agent, make_listing):
        listing = make_listing()
        ListingService.delete(listing_id=listing.id, actor=agent)

        assert list(ListingService.search()) == []
        assert list(ListingService.list()) == []

    def test_distance_ordering_without_coordinates_raises(self):
        with pytest.raises(ValidationException):
            ListingService.search(ordering="distance", has_geo_filter=False)
