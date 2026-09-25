"""Thin HTTP views for the listings API.

Views only handle request/response concerns: authentication, validation,
serialisation and status codes. Every business decision lives in
:mod:`apps.listings.services`.
"""

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response

from apps.listings.permissions import IsAuthenticatedOrReadOnly
from apps.listings.serializers import (
    ListingListResponseSerializer,
    ListingResponseSerializer,
    ListingSearchQuerySerializer,
    ListingSerializer,
    ListingWriteSerializer,
)
from apps.listings.services import ListingService
from core.pagination import StandardResultsSetPagination
from core.responses import ResponseHandler
from core.serializers import ErrorResponseSerializer

LISTING_ERRORS = {
    400: ErrorResponseSerializer,
    401: ErrorResponseSerializer,
    403: ErrorResponseSerializer,
    404: ErrorResponseSerializer,
}


class ListingViewSet(viewsets.ModelViewSet):
    """CRUD endpoints and geo aware search for property listings.

    Reads are public; create, update and delete require a JWT access token and
    are restricted to the agent that owns the listing (admins may manage any).
    """

    permission_classes = [IsAuthenticatedOrReadOnly]
    lookup_field = "id"

    def get_queryset(self):
        """Return the queryset used for list and detail actions.

        Returns:
            A queryset of live listings, newest first.
        """
        return ListingService.list()

    def get_serializer_class(self):
        """Pick the write serializer for create/update, read serializer otherwise.

        Returns:
            The serializer class matching the current action.
        """
        if self.action in {"create", "update", "partial_update"}:
            return ListingWriteSerializer
        return ListingSerializer

    @swagger_auto_schema(
        operation_id="listListings",
        operation_summary="List listings",
        operation_description="Return a paginated list of live listings, newest first.",
        responses={200: ListingListResponseSerializer},
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        """List all live listings.

        Args:
            request: Incoming request.
            *args: Positional args passed by the router.
            **kwargs: Keyword args passed by the router.

        Returns:
            A paginated success envelope.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return ResponseHandler.success(serializer.data)

    @swagger_auto_schema(
        operation_id="retrieveListing",
        operation_summary="Retrieve a listing",
        operation_description="Return a single listing by id. Soft deleted listings return 404.",
        responses={200: ListingResponseSerializer, **LISTING_ERRORS},
    )
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        """Return a single listing.

        Args:
            request: Incoming request.
            *args: Positional args passed by the router.
            **kwargs: Keyword args including ``id``.

        Returns:
            A success envelope containing the listing.
        """
        listing = ListingService.get(listing_id=kwargs.get("id"))
        serializer = ListingSerializer(listing, context=self.get_serializer_context())
        return ResponseHandler.success(serializer.data)

    @swagger_auto_schema(
        operation_id="createListing",
        operation_summary="Create a listing",
        operation_description=(
            "Create a listing owned by the authenticated agent. Administrators may pass "
            "`agent_id` to assign a different agent."
        ),
        request_body=ListingWriteSerializer,
        responses={201: ListingResponseSerializer, **LISTING_ERRORS},
    )
    def create(self, request: Request, *args, **kwargs) -> Response:
        """Create a listing from the request payload.

        Args:
            request: Incoming request.
            *args: Positional args passed by the router.
            **kwargs: Keyword args passed by the router.

        Returns:
            A ``201`` success envelope containing the created listing.
        """
        write_serializer = ListingWriteSerializer(data=request.data)
        write_serializer.is_valid(raise_exception=True)
        listing = ListingService.create(
            data=dict(write_serializer.validated_data), actor=request.user
        )
        read_serializer = ListingSerializer(listing, context=self.get_serializer_context())
        return ResponseHandler.created(read_serializer.data, message="Listing created.")

    @swagger_auto_schema(
        operation_id="updateListing",
        operation_summary="Update a listing",
        operation_description="Replace a listing you own (admins may update any listing).",
        request_body=ListingWriteSerializer,
        responses={200: ListingResponseSerializer, **LISTING_ERRORS},
    )
    def update(self, request: Request, *args, **kwargs) -> Response:
        """Fully update a listing.

        Args:
            request: Incoming request.
            *args: Positional args passed by the router.
            **kwargs: Keyword args including ``id``.

        Returns:
            A success envelope containing the updated listing.
        """
        return self._perform_update(request, partial=False, listing_id=kwargs.get("id"))

    @swagger_auto_schema(
        operation_id="partialUpdateListing",
        operation_summary="Partially update a listing",
        operation_description="Update any subset of fields on a listing you own.",
        request_body=ListingWriteSerializer,
        responses={200: ListingResponseSerializer, **LISTING_ERRORS},
    )
    def partial_update(self, request: Request, *args, **kwargs) -> Response:
        """Partially update a listing.

        Args:
            request: Incoming request.
            *args: Positional args passed by the router.
            **kwargs: Keyword args including ``id``.

        Returns:
            A success envelope containing the updated listing.
        """
        return self._perform_update(request, partial=True, listing_id=kwargs.get("id"))

    def _perform_update(self, request: Request, *, partial: bool, listing_id) -> Response:
        """Validate the payload and delegate the update to the service layer.

        Args:
            request: Incoming request.
            partial: ``True`` for ``PATCH`` requests.
            listing_id: Primary key of the listing to update.

        Returns:
            A success envelope containing the updated listing.

        Raises:
            rest_framework.exceptions.ValidationError: If the payload is invalid.
        """
        write_serializer = ListingWriteSerializer(data=request.data, partial=partial)
        write_serializer.is_valid(raise_exception=True)
        listing = ListingService.update(
            listing_id=listing_id,
            data=dict(write_serializer.validated_data),
            actor=request.user,
            partial=partial,
        )
        read_serializer = ListingSerializer(listing, context=self.get_serializer_context())
        return ResponseHandler.success(read_serializer.data, message="Listing updated.")

    @swagger_auto_schema(
        operation_id="deleteListing",
        operation_summary="Delete a listing",
        operation_description=(
            "Soft delete a listing you own. The row is retained for auditing and "
            "no longer appears in read endpoints."
        ),
        responses={204: None, **LISTING_ERRORS},
    )
    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """Soft delete a listing.

        Args:
            request: Incoming request.
            *args: Positional args passed by the router.
            **kwargs: Keyword args including ``id``.

        Returns:
            An empty ``204`` response.
        """
        ListingService.delete(listing_id=kwargs.get("id"), actor=request.user)
        return ResponseHandler.no_content()

    @swagger_auto_schema(
        operation_id="searchListings",
        operation_summary="Search listings",
        operation_description=(
            "Filter listings by type, price range and bedrooms. Supply `lat` and `lng` "
            "(optionally with `radius_km`, default 5) to restrict results to that radius "
            "using PostGIS; geo results include `distance_km` and are ordered by distance."
        ),
        manual_parameters=[
            openapi.Parameter(
                "type",
                openapi.IN_QUERY,
                description="Listing type filter.",
                type=openapi.TYPE_STRING,
                enum=["rent", "sale", "shortlet"],
            ),
            openapi.Parameter(
                "min_price",
                openapi.IN_QUERY,
                description="Minimum price (inclusive).",
                type=openapi.TYPE_NUMBER,
            ),
            openapi.Parameter(
                "max_price",
                openapi.IN_QUERY,
                description="Maximum price (inclusive).",
                type=openapi.TYPE_NUMBER,
            ),
            openapi.Parameter(
                "bedrooms",
                openapi.IN_QUERY,
                description="Exact bedroom count.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "bedrooms_min",
                openapi.IN_QUERY,
                description="Minimum bedroom count.",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "lat",
                openapi.IN_QUERY,
                description="Latitude of the search centre. Requires lng.",
                type=openapi.TYPE_NUMBER,
            ),
            openapi.Parameter(
                "lng",
                openapi.IN_QUERY,
                description="Longitude of the search centre. Requires lat.",
                type=openapi.TYPE_NUMBER,
            ),
            openapi.Parameter(
                "radius_km",
                openapi.IN_QUERY,
                description="Radius in km around lat/lng. Default 5, max 20000.",
                type=openapi.TYPE_NUMBER,
            ),
            openapi.Parameter(
                "ordering",
                openapi.IN_QUERY,
                description=(
                    "Result ordering: distance (default for geo searches), newest, "
                    "price_asc or price_desc."
                ),
                type=openapi.TYPE_STRING,
                enum=["distance", "newest", "price_asc", "price_desc"],
            ),
            openapi.Parameter(
                "page",
                openapi.IN_QUERY,
                description="Page number (1 indexed).",
                type=openapi.TYPE_INTEGER,
            ),
            openapi.Parameter(
                "page_size",
                openapi.IN_QUERY,
                description=(
                    "Items per page "
                    f"(default {StandardResultsSetPagination.page_size}, "
                    f"max {StandardResultsSetPagination.max_page_size})."
                ),
                type=openapi.TYPE_INTEGER,
            ),
        ],
        responses={200: ListingListResponseSerializer, **LISTING_ERRORS},
    )
    @action(detail=False, methods=["get"], permission_classes=[IsAuthenticatedOrReadOnly])
    def search(self, request: Request) -> Response:
        """Search listings with filters and an optional radius.

        Args:
            request: Incoming request whose query parameters drive the search.

        Returns:
            A paginated success envelope with matching listings.

        Raises:
            rest_framework.exceptions.ValidationError: If the query parameters
                are invalid or inconsistent.
        """
        query_serializer = ListingSearchQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        queryset = ListingService.search(**query_serializer.validated_data)
        page = self.paginate_queryset(queryset)
        serializer = ListingSerializer(
            page if page is not None else queryset,
            many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return ResponseHandler.success(serializer.data)
