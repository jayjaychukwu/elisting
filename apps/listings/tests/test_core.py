"""Tests for the shared core utilities: responses, handlers and soft deletes."""

import json

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import NotFound as DRFNotFound
from rest_framework.exceptions import ValidationError as DRFValidationError

from apps.listings.models import Listing
from core.exception_handler import api_exception_handler, api_not_found
from core.exceptions import ConflictException, NotFoundException
from core.pagination import StandardResultsSetPagination
from core.responses import ResponseHandler

pytestmark = pytest.mark.django_db


class TestResponseHandler:
    """The single source of response envelopes."""

    def test_success_payload_shape(self):
        payload = ResponseHandler.success_payload(data={"id": 1}, message="ok")

        assert payload == {"success": True, "message": "ok", "data": {"id": 1}}

    def test_success_payload_includes_meta_when_given(self):
        payload = ResponseHandler.success_payload(data=[], meta={"page": 1})

        assert payload["meta"] == {"page": 1}

    def test_error_payload_shape(self):
        payload = ResponseHandler.error_payload(
            message="nope", errors={"title": ["Required"]}, error_code="validation_error"
        )

        assert payload["success"] is False
        assert payload["errors"] == {"title": ["Required"]}


class TestExceptionHandler:
    """Mapping of every exception family to the error envelope."""

    def _response(self, exc):
        return api_exception_handler(exc, {"request": None, "view": None})

    def test_app_exception_uses_its_own_status_and_code(self):
        response = self._response(NotFoundException("Listing not found."))

        assert response.status_code == 404
        assert response.data["error_code"] == "not_found"
        assert response.data["message"] == "Listing not found."

    def test_conflict_exception_maps_to_409(self):
        response = self._response(ConflictException())

        assert response.status_code == 409

    def test_drf_validation_error_normalises_field_errors(self):
        response = self._response(DRFValidationError({"price": ["This field must be positive."]}))

        assert response.status_code == 400
        assert response.data["error_code"] == "validation_error"
        assert response.data["errors"] == {"price": ["This field must be positive."]}

    def test_drf_not_found_is_handled(self):
        response = self._response(DRFNotFound())

        assert response.status_code == 404
        assert response.data["success"] is False

    def test_unexpected_exception_returns_generic_500(self):
        response = self._response(RuntimeError("secret internal detail"))

        assert response.status_code == 500
        assert response.data["error_code"] == "internal_server_error"
        assert "secret internal detail" not in json.dumps(response.data)

    def test_root_404_handler_returns_json_envelope(self):
        response = api_not_found(RequestFactory().get("/api/v1/missing/"))

        assert response.status_code == 404
        assert json.loads(response.content)["error_code"] == "not_found"


class TestPagination:
    """Page number pagination defaults exposed in the standard envelope."""

    def test_defaults(self):
        assert StandardResultsSetPagination.page_size == 10
        assert StandardResultsSetPagination.max_page_size == 50
        assert StandardResultsSetPagination.page_query_param == "page"


class TestBaseModelSoftDelete:
    """Soft delete helpers on the shared abstract model."""

    def test_soft_delete_sets_audit_fields_and_hides_row(self, make_listing, agent):
        listing = make_listing()

        listing.soft_delete(user=agent)

        assert listing.deleted_at is not None
        assert listing.deleted_by == agent
        assert not Listing.objects.filter(pk=listing.pk).exists()
        assert Listing.deleted_objects.filter(pk=listing.pk).exists()

    def test_restore_brings_listing_back(self, make_listing, agent):
        listing = make_listing()
        listing.soft_delete(user=agent)

        listing.restore(user=agent)

        assert listing.deleted_at is None
        assert Listing.objects.filter(pk=listing.pk).exists()

    def test_hard_delete_removes_the_row(self, make_listing):
        listing = make_listing()

        listing.delete(hard=True)

        assert not Listing.all_objects.filter(pk=listing.pk).exists()

    def test_queryset_soft_delete_and_restore(self, make_listing, agent):
        listing = make_listing()

        Listing.objects.all().delete(user=agent)
        assert not Listing.objects.exists()

        Listing.deleted_objects.all().restore()
        assert Listing.objects.filter(pk=listing.pk).exists()
