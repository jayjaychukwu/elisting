"""Integration tests for the listings HTTP API."""

import json
from decimal import Decimal

import pytest
from django.contrib.gis.geos import Point
from django.urls import reverse

from apps.listings.enums import ListingType
from apps.listings.models import Listing

pytestmark = pytest.mark.django_db

LISTINGS_URL = "/api/v1/listings/"
SEARCH_URL = "/api/v1/listings/search/"


class TestReadEndpoints:
    """Public list, retrieve and search behaviour."""

    def test_list_returns_paginated_success_envelope(self, api_client, make_listing):
        make_listing()
        make_listing()

        response = api_client.get(LISTINGS_URL)

        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["meta"]["total_count"] == 2
        assert response.data["meta"]["page"] == 1
        assert len(response.data["data"]) == 2

    def test_list_respects_page_size(self, api_client, make_listing):
        for index in range(5):
            make_listing(title=f"Listing {index}")

        response = api_client.get(LISTINGS_URL, {"page_size": 2, "page": 2})

        assert response.data["meta"]["total_pages"] == 3
        assert response.data["meta"]["page"] == 2
        assert len(response.data["data"]) == 2
        assert response.data["meta"]["next"]

    def test_retrieve_returns_listing_with_coordinates(self, api_client, make_listing):
        listing = make_listing()

        response = api_client.get(f"{LISTINGS_URL}{listing.id}/")

        assert response.status_code == 200
        assert response.data["data"]["latitude"] == 6.4474
        assert response.data["data"]["longitude"] == 3.4735
        assert response.data["data"]["agent_id"] == listing.agent_id

    def test_unknown_listing_returns_404_envelope(self, api_client):
        response = api_client.get(f"{LISTINGS_URL}00000000-0000-0000-0000-000000000000/")

        assert response.status_code == 404
        assert response.data["success"] is False
        assert response.data["error_code"] == "not_found"

    def test_unknown_route_returns_404_envelope(self, api_client):
        response = api_client.get("/api/v1/nope/")

        assert response.status_code == 404
        # Unknown paths never reach DRF, so the root handler returns JsonResponse.
        payload = json.loads(response.content)
        assert payload["success"] is False
        assert payload["error_code"] == "not_found"

    def test_soft_deleted_listing_is_hidden(self, api_client, auth_client, make_listing):
        listing = make_listing()
        auth_client.delete(f"{LISTINGS_URL}{listing.id}/")

        assert api_client.get(f"{LISTINGS_URL}{listing.id}/").status_code == 404
        assert api_client.get(LISTINGS_URL).data["meta"]["total_count"] == 0


class TestCreateEndpoint:
    """Authenticated create behaviour."""

    def test_agent_can_create_listing(self, auth_client, listing_payload):
        response = auth_client.post(LISTINGS_URL, listing_payload, format="json")

        assert response.status_code == 201
        assert response.data["message"] == "Listing created."
        assert response.data["data"]["title"] == listing_payload["title"]
        assert Listing.objects.count() == 1

    def test_created_listing_owns_actor_and_audit_fields(self, auth_client, agent, listing_payload):
        response = auth_client.post(LISTINGS_URL, listing_payload, format="json")

        listing = Listing.objects.get(id=response.data["data"]["id"])
        assert listing.agent == agent
        assert listing.created_by == agent
        assert listing.deleted_at is None

    def test_anonymous_create_is_rejected(self, api_client, listing_payload):
        response = api_client.post(LISTINGS_URL, listing_payload, format="json")

        assert response.status_code == 401
        assert response.data["error_code"] == "authentication_failed"

    def test_invalid_payload_returns_field_errors(self, auth_client, listing_payload):
        listing_payload.update({"type": "invalid", "bedrooms": -1, "latitude": 500})

        response = auth_client.post(LISTINGS_URL, listing_payload, format="json")

        assert response.status_code == 400
        assert response.data["error_code"] == "validation_error"
        assert set(response.data["errors"]) >= {"type", "bedrooms", "latitude"}

    def test_agent_cannot_create_listing_for_another_agent(
        self, auth_client, other_agent, listing_payload
    ):
        listing_payload["agent_id"] = str(other_agent.id)

        response = auth_client.post(LISTINGS_URL, listing_payload, format="json")

        assert response.status_code == 403
        assert response.data["error_code"] == "permission_denied"

    def test_admin_can_create_listing_for_another_agent(
        self, api_client, admin_user, agent, listing_payload
    ):
        api_client.force_authenticate(user=admin_user)
        listing_payload["agent_id"] = str(agent.id)

        response = api_client.post(LISTINGS_URL, listing_payload, format="json")

        assert response.status_code == 201
        assert response.data["data"]["agent_id"] == agent.id


class TestUpdateAndDeleteEndpoints:
    """Ownership rules and soft delete behaviour."""

    def test_owner_can_patch_listing(self, auth_client, make_listing):
        listing = make_listing()

        response = auth_client.patch(
            f"{LISTINGS_URL}{listing.id}/", {"price": "125000.00"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["data"]["price"] == "125000.00"
        listing.refresh_from_db()
        assert listing.price == Decimal("125000.00")

    def test_patch_with_only_one_coordinate_is_rejected(self, auth_client, make_listing):
        listing = make_listing()

        response = auth_client.patch(
            f"{LISTINGS_URL}{listing.id}/", {"latitude": 6.5}, format="json"
        )

        assert response.status_code == 400
        assert "location" in response.data["errors"]

    def test_non_owner_cannot_patch_listing(self, api_client, other_agent, make_listing):
        listing = make_listing()
        api_client.force_authenticate(user=other_agent)

        response = api_client.patch(
            f"{LISTINGS_URL}{listing.id}/", {"price": "1.00"}, format="json"
        )

        assert response.status_code == 403
        assert response.data["error_code"] == "permission_denied"

    def test_delete_returns_204_and_soft_deletes(self, auth_client, agent, make_listing):
        listing = make_listing()

        response = auth_client.delete(f"{LISTINGS_URL}{listing.id}/")

        assert response.status_code == 204
        row = Listing.all_objects.get(pk=listing.id)
        assert row.deleted_at is not None
        assert row.deleted_by == agent


class TestSearchEndpoint:
    """Search filters and geo behaviour over HTTP."""

    def test_filters_are_combined(self, api_client, make_listing):
        match = make_listing(type=ListingType.RENT, price=Decimal("800000"), bedrooms=3)
        make_listing(type=ListingType.RENT, price=Decimal("20000000"), bedrooms=3)
        make_listing(type=ListingType.SALE, price=Decimal("800000"), bedrooms=3)

        response = api_client.get(
            SEARCH_URL,
            {
                "type": ListingType.RENT,
                "min_price": "500000",
                "max_price": "1500000",
                "bedrooms": 3,
            },
        )

        assert response.status_code == 200
        assert [item["id"] for item in response.data["data"]] == [str(match.id)]

    def test_radius_search_returns_distance_km(self, api_client, make_listing):
        near = make_listing(location=Point(3.4735, 6.4474, srid=4326))
        make_listing(location=Point(3.3200, 6.6200, srid=4326))

        response = api_client.get(SEARCH_URL, {"lat": 6.4474, "lng": 3.4735, "radius_km": "5"})

        assert response.status_code == 200
        assert [item["id"] for item in response.data["data"]] == [str(near.id)]
        assert response.data["data"][0]["distance_km"] == 0.0

    def test_radius_search_orders_by_distance(self, api_client, make_listing):
        far = make_listing(location=Point(3.4219, 6.4281, srid=4326))
        near = make_listing(location=Point(3.4745, 6.4484, srid=4326))

        response = api_client.get(SEARCH_URL, {"lat": 6.4474, "lng": 3.4735, "radius_km": "10"})

        returned = [item["id"] for item in response.data["data"]]
        assert returned == [str(near.id), str(far.id)]
        distances = [item["distance_km"] for item in response.data["data"]]
        assert distances == sorted(distances)

    def test_price_ordering_is_supported(self, api_client, make_listing):
        cheap = make_listing(price=Decimal("1000"))
        pricey = make_listing(price=Decimal("900000"))

        response = api_client.get(SEARCH_URL, {"ordering": "price_asc"})

        assert [item["id"] for item in response.data["data"]] == [
            str(cheap.id),
            str(pricey.id),
        ]

    def test_lat_without_lng_is_rejected(self, api_client):
        response = api_client.get(SEARCH_URL, {"lat": 6.4474})

        assert response.status_code == 400
        assert "lng" in response.data["errors"]

    def test_radius_without_coordinates_is_rejected(self, api_client):
        response = api_client.get(SEARCH_URL, {"radius_km": "5"})

        assert response.status_code == 400
        assert "radius_km" in response.data["errors"]

    def test_min_price_above_max_price_is_rejected(self, api_client):
        response = api_client.get(SEARCH_URL, {"min_price": "900", "max_price": "100"})

        assert response.status_code == 400
        assert "max_price" in response.data["errors"]

    def test_distance_ordering_without_coordinates_is_rejected(self, api_client):
        response = api_client.get(SEARCH_URL, {"ordering": "distance"})

        assert response.status_code == 400
        assert response.data["error_code"] == "validation_error"


class TestAuthEndpoints:
    """JWT issuance through the simplejwt endpoints."""

    def test_token_endpoint_returns_access_and_refresh(self, api_client, agent):
        response = api_client.post(
            reverse("token_obtain_pair"),
            {"username": agent.username, "password": "TestPass123!"},
            format="json",
        )

        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data

    def test_token_endpoint_rejects_bad_password(self, api_client, agent):
        response = api_client.post(
            reverse("token_obtain_pair"),
            {"username": agent.username, "password": "wrong"},
            format="json",
        )

        assert response.status_code == 401
