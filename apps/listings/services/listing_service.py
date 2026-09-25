"""Listing domain service.

All listing business rules live here as classmethods:

* create/update/delete enforce ownership and agent assignment rules,
* get/list/search build soft delete aware, geo capable querysets,
* every write invalidates the cached search results it can affect.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, ClassVar

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.db import models, transaction

from apps.accounts.models import User
from apps.accounts.services.user_service import UserService
from apps.listings.models import Listing
from core.cache import CacheManager, CacheNameSpaces
from core.exceptions import PermissionDeniedException, ValidationException
from core.services import BaseService


class ListingService(BaseService):
    """Operations on property listings."""

    model = Listing

    DEFAULT_SEARCH_RADIUS_KM = Decimal("5")

    ORDERING_MAP: ClassVar[dict[str, tuple[str, ...]]] = {
        "newest": ("-created_at",),
        "price_asc": ("price", "-created_at"),
        "price_desc": ("-price", "-created_at"),
    }

    @classmethod
    @transaction.atomic
    def create(cls, *, data: dict[str, Any], actor: User) -> Listing:
        """Create a listing on behalf of the authenticated user.

        The listing belongs to the acting agent unless an administrator assigns
        a different ``agent``. Audit fields are stamped from the actor.

        Args:
            data: Validated payload from
                :class:`~apps.listings.serializers.ListingWriteSerializer`.
            actor: The authenticated user performing the write.

        Returns:
            The newly created listing.
        """
        requested_agent = data.get("agent")
        agent = cls._resolve_agent(actor, requested_agent)
        fields = {key: value for key, value in data.items() if key != "agent"}
        listing = Listing.objects.create(
            agent=agent,
            created_by=actor,
            updated_by=actor,
            **fields,
        )
        cls._invalidate_search_cache()
        return listing

    @classmethod
    @transaction.atomic
    def update(
        cls,
        *,
        listing_id: Any,
        data: dict[str, Any],
        actor: User,
        partial: bool = False,
    ) -> Listing:
        """Update an existing listing, enforcing ownership rules.

        Args:
            listing_id: Primary key of the listing to update.
            data: Validated payload from
                :class:`~apps.listings.serializers.ListingWriteSerializer`.
            actor: The authenticated user performing the write.
            partial: ``True`` when called through ``PATCH``.

        Returns:
            The updated listing.

        Raises:
            NotFoundException: If the listing does not exist or was soft deleted.
            PermissionDeniedException: If the actor does not own the listing, or a
                non-admin attempts to reassign it.
            ValidationException: If a full update omits the location.
        """
        listing = cls.get(listing_id)
        cls._ensure_can_mutate(listing, actor)

        if not partial and "location" not in data:
            raise ValidationException("A full update must include both latitude and longitude.")

        if "agent" in data:
            requested_agent = data.pop("agent")
            if requested_agent.pk != listing.agent_id and not UserService.is_admin(actor):
                raise PermissionDeniedException(
                    "Only administrators can reassign a listing to another agent."
                )
            listing.agent = cls._resolve_agent(actor, requested_agent)

        for field, value in data.items():
            setattr(listing, field, value)

        listing.updated_by = actor
        listing.save()
        cls._invalidate_search_cache()
        return listing

    @classmethod
    @transaction.atomic
    def delete(cls, *, listing_id: Any, actor: User) -> Listing:
        """Soft delete a listing, keeping the row for auditing.

        Args:
            listing_id: Primary key of the listing to delete.
            actor: The authenticated user performing the delete; recorded in
                ``deleted_by``.

        Returns:
            The soft deleted listing.

        Raises:
            NotFoundException: If the listing does not exist or was already deleted.
            PermissionDeniedException: If the actor does not own the listing.
        """
        listing = cls.get(listing_id)
        cls._ensure_can_mutate(listing, actor)
        listing.soft_delete(user=actor)
        cls._invalidate_search_cache()
        return listing

    @classmethod
    def get(cls, listing_id: Any) -> Listing:
        """Return a single live listing by id.

        Args:
            listing_id: Primary key of the listing.

        Returns:
            The requested listing.

        Raises:
            NotFoundException: If the listing does not exist or was soft deleted.
        """
        return cls.get_object_or_raise(
            listing_id,
            message="Listing not found.",
            queryset=cls._active_listings(),
        )

    @classmethod
    def list(cls) -> models.QuerySet[Listing]:
        """Return all live listings, newest first.

        Returns:
            A queryset of live listings with the agent prefetched.
        """
        return cls._active_listings().order_by("-created_at")

    @classmethod
    def search(cls, **filters: Any) -> Sequence[Listing]:
        """Return cached search results for the given filters.

        Supported filters: ``type``, ``min_price``, ``max_price``, ``bedrooms``,
        ``bedrooms_min`` and, when ``lat``/``lng`` are provided, a PostGIS radius
        search. A geo search annotates ``distance`` and orders nearest first
        unless another ordering is requested.

        Results are cached in Redis (locmem in tests) as an ordered list of
        ``(id, distance)`` pairs keyed by the normalised filters. On a cache hit
        the rows are rebuilt with a single primary key query, so the filtering
        and spatial work happens at most once per TTL window. Any create, update
        or delete clears the namespace, so cached results cannot outlive a write.

        Args:
            **filters: Validated query parameters from
                :class:`~apps.listings.serializers.ListingSearchQuerySerializer`.

        Returns:
            The matching listings in search order.

        Raises:
            ValidationException: If ``ordering="distance"`` is requested without
                coordinates, or the ordering is unknown.
        """
        cache_key = cls._search_cache_key(filters)
        cached = CacheManager.get(cache_key)
        if cached is not None:
            return cls._materialise_search_results(cached)

        results = list(cls._search_queryset(**filters))
        CacheManager.set(
            cache_key,
            [cls._cache_entry(listing) for listing in results],
            ttl=CacheNameSpaces.LISTING_SEARCH_TTL,
        )
        return results

    @classmethod
    def _search_queryset(cls, **filters: Any) -> models.QuerySet[Listing]:
        """Build the uncached, filtered and geo-aware queryset.

        Args:
            **filters: Validated query parameters.

        Returns:
            A queryset of matching listings.

        Raises:
            ValidationException: If the ordering is impossible or unknown.
        """
        queryset = cls._active_listings()

        listing_type = filters.get("type")
        if listing_type:
            queryset = queryset.filter(type=listing_type)

        min_price = filters.get("min_price")
        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)

        max_price = filters.get("max_price")
        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)

        bedrooms = filters.get("bedrooms")
        if bedrooms is not None:
            queryset = queryset.filter(bedrooms=bedrooms)

        bedrooms_min = filters.get("bedrooms_min")
        if bedrooms_min is not None:
            queryset = queryset.filter(bedrooms__gte=bedrooms_min)

        has_geo_filter = bool(filters.get("has_geo_filter"))
        if has_geo_filter:
            centre = Point(filters["lng"], filters["lat"], srid=4326)
            radius_km = filters.get("radius_km") or cls.DEFAULT_SEARCH_RADIUS_KM
            queryset = queryset.filter(location__distance_lte=(centre, D(km=float(radius_km))))
            queryset = queryset.annotate(distance=Distance("location", centre))

        ordering = filters.get("ordering") or ("distance" if has_geo_filter else "newest")
        return cls._apply_ordering(queryset, ordering, has_geo_filter)

    @classmethod
    def _search_cache_key(cls, filters: dict[str, Any]) -> str:
        """Build the cache key for a set of search filters.

        Args:
            filters: Validated query parameters.

        Returns:
            A namespaced cache key specific to those filters.
        """
        parts = [
            f"{name}={filters[name]}"
            for name in sorted(filters)
            if filters[name] is not None and filters[name] is not False
        ]
        return CacheManager.make_key(CacheNameSpaces.LISTING_SEARCH, *parts)

    @staticmethod
    def _cache_entry(listing: Listing) -> tuple[str, float | None]:
        """Represent a listing as its cacheable ``(id, distance)`` pair.

        Args:
            listing: A listing, optionally annotated with ``distance`` in metres
                (PostGIS returns a GEOS distance object exposing ``m``).

        Returns:
            The listing id and its distance in metres, or ``None`` when the
            search was not a geo search.
        """
        distance = getattr(listing, "distance", None)
        if distance is None:
            return str(listing.pk), None
        return str(listing.pk), float(distance.m if hasattr(distance, "m") else distance)

    @classmethod
    def _materialise_search_results(
        cls, entries: Sequence[tuple[str, float | None]]
    ) -> Sequence[Listing]:
        """Rebuild listings from cached ``(id, distance)`` entries.

        Args:
            entries: Cached search entries in search order.

        Returns:
            The listings, in the same order, with cached distances re-attached.
        """
        rows = {
            str(row.pk): row
            for row in cls._active_listings().filter(pk__in=[entry[0] for entry in entries])
        }
        listings = []
        for listing_id, distance in entries:
            row = rows.get(listing_id)
            if row is None:
                continue
            if distance is not None:
                row.distance = distance
            listings.append(row)
        return listings

    @staticmethod
    def _invalidate_search_cache() -> None:
        """Clear every cached search result.

        Called from every write path so listings never appear stale in search.
        """
        CacheManager.clear_namespace(CacheNameSpaces.LISTING_SEARCH)

    @classmethod
    def _active_listings(cls) -> models.QuerySet[Listing]:
        """Return the base queryset of live listings with the agent prefetched.

        Returns:
            A soft delete aware queryset of listings.
        """
        return Listing.objects.select_related("agent")

    @classmethod
    def _resolve_agent(cls, actor: User, requested_agent: User | None) -> User:
        """Decide which agent a listing should belong to.

        Args:
            actor: The authenticated user performing the write.
            requested_agent: Agent requested by the client, if any.

        Returns:
            The agent that should own the listing.

        Raises:
            PermissionDeniedException: If a non-admin tries to assign another agent.
        """
        if requested_agent is None or requested_agent.pk == actor.pk:
            return actor
        if UserService.is_admin(actor):
            return requested_agent
        raise PermissionDeniedException(
            "Only administrators can assign a listing to another agent."
        )

    @classmethod
    def _ensure_can_mutate(cls, listing: Listing, actor: User) -> None:
        """Verify that the actor may modify or delete the listing.

        Args:
            listing: The listing being mutated.
            actor: The authenticated user performing the write.

        Raises:
            PermissionDeniedException: If the actor neither owns the listing nor
                is an administrator.
        """
        if listing.agent_id == actor.pk or UserService.is_admin(actor):
            return
        raise PermissionDeniedException("You can only modify listings you own.")

    @classmethod
    def _apply_ordering(
        cls,
        queryset: models.QuerySet[Listing],
        ordering: str,
        has_geo_filter: bool,
    ) -> models.QuerySet[Listing]:
        """Apply a named ordering to a listing queryset.

        Args:
            queryset: Queryset to order.
            ordering: One of ``distance``, ``newest``, ``price_asc``, ``price_desc``.
            has_geo_filter: Whether the queryset carries a distance annotation.

        Returns:
            The ordered queryset.

        Raises:
            ValidationException: If the ordering is unknown or impossible.
        """
        if ordering == "distance":
            if not has_geo_filter:
                raise ValidationException("ordering='distance' requires lat and lng.")
            return queryset.order_by("distance", "id")
        fields = cls.ORDERING_MAP.get(ordering)
        if fields is None:
            raise ValidationException(f"Unsupported ordering '{ordering}'.")
        return queryset.order_by(*fields)
