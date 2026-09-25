"""Serializers for listings.

Read and write shapes are split so the generated Swagger schema is precise:
the write schema exposes ``latitude``/``longitude`` and the optional
``agent_id`` override, while the read schema exposes the stored coordinates
and the optional ``distance_km`` annotation.
"""

from decimal import Decimal

from django.contrib.gis.geos import Point
from rest_framework import serializers

from apps.accounts.models import User
from apps.listings.enums import ListingType
from apps.listings.models import Listing
from core.serializers import PaginationMetaSerializer


class ListingSerializer(serializers.ModelSerializer):
    """Read representation of a listing, including distance when present."""

    agent_id = serializers.PrimaryKeyRelatedField(
        source="agent",
        queryset=User.objects.all(),
    )
    agent_username = serializers.CharField(source="agent.username", read_only=True)
    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)
    distance_km = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        """Serializer metadata."""

        model = Listing
        fields = (
            "id",
            "title",
            "price",
            "type",
            "bedrooms",
            "location_name",
            "latitude",
            "longitude",
            "agent_id",
            "agent_username",
            "distance_km",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_distance_km(self, obj: Listing) -> float | None:
        """Return the distance annotation in kilometres.

        Args:
            obj: The serialised listing, optionally annotated with ``distance``
                by the geo search service. PostGIS returns a GEOS distance
                geometry; its ``m`` attribute holds the value in metres.

        Returns:
            Distance in kilometres rounded to three decimals, or ``None`` when
            the listing was not retrieved through a geo search.
        """
        distance = getattr(obj, "distance", None)
        if distance is None:
            return None
        metres = distance.m if hasattr(distance, "m") else float(distance)
        return round(metres / 1000, 3)


class ListingResponseSerializer(serializers.Serializer):
    """Success envelope returned by single listing endpoints."""

    success = serializers.BooleanField()
    message = serializers.CharField(allow_blank=True)
    data = ListingSerializer()


class ListingListResponseSerializer(serializers.Serializer):
    """Success envelope returned by paginated listing endpoints."""

    success = serializers.BooleanField()
    message = serializers.CharField(allow_blank=True)
    data = ListingSerializer(many=True)
    meta = PaginationMetaSerializer()


class ListingWriteSerializer(serializers.ModelSerializer):
    """Validated input used to create or update a listing.

    Coordinates are supplied as plain ``latitude``/``longitude`` numbers and
    assembled into a WGS84 ``Point`` by :meth:`validate`.
    """

    latitude = serializers.FloatField(
        min_value=-90,
        max_value=90,
        error_messages={"max_value": "Latitude must be between -90 and 90."},
    )
    longitude = serializers.FloatField(
        min_value=-180,
        max_value=180,
        error_messages={"max_value": "Longitude must be between -180 and 180."},
    )
    agent_id = serializers.PrimaryKeyRelatedField(
        source="agent",
        queryset=User.objects.all(),
        required=False,
        help_text=(
            "Optional. Agents default to the authenticated user; admins may assign any agent."
        ),
    )

    class Meta:
        """Serializer metadata."""

        model = Listing
        fields = (
            "title",
            "price",
            "type",
            "bedrooms",
            "location_name",
            "latitude",
            "longitude",
            "agent_id",
        )
        extra_kwargs = {
            "title": {"max_length": 200},
            "location_name": {"max_length": 255},
        }

    def validate(self, attrs):
        """Ensure both coordinates are supplied together and build the geometry.

        ``latitude``/``longitude`` are removed from the validated data and
        replaced by a WGS84 ``Point`` stored in ``location``. On a partial
        update that omits both fields, the existing geometry is left untouched.

        Args:
            attrs: Validated field data.

        Returns:
            The validated data, with a ``location`` ``Point`` added when
            coordinates were supplied.

        Raises:
            serializers.ValidationError: If only one coordinate is supplied.
        """
        latitude = attrs.pop("latitude", None)
        longitude = attrs.pop("longitude", None)
        if latitude is None and longitude is None:
            return attrs
        if latitude is None or longitude is None:
            raise serializers.ValidationError(
                {"location": ["latitude and longitude must be supplied together."]}
            )
        attrs["location"] = Point(longitude, latitude, srid=4326)
        return attrs

    def create(self, validated_data):
        """Create a listing from validated data.

        Args:
            validated_data: Data produced by :meth:`validate`.

        Returns:
            The newly created :class:`~apps.listings.models.Listing`.
        """
        return Listing.objects.create(**validated_data)

    def update(self, instance, validated_data):
        """Update a listing from validated data.

        Args:
            instance: Existing listing.
            validated_data: Data produced by :meth:`validate`.

        Returns:
            The updated listing.
        """
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


class ListingSearchQuerySerializer(serializers.Serializer):
    """Validates the query parameters accepted by the search endpoint."""

    type = serializers.ChoiceField(choices=ListingType.choices, required=False)
    min_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )
    max_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False
    )
    bedrooms = serializers.IntegerField(min_value=0, max_value=100, required=False)
    bedrooms_min = serializers.IntegerField(min_value=0, max_value=100, required=False)
    lat = serializers.FloatField(
        min_value=-90,
        max_value=90,
        required=False,
        help_text="Latitude of the search centre. Must be supplied with lng.",
    )
    lng = serializers.FloatField(
        min_value=-180,
        max_value=180,
        required=False,
        help_text="Longitude of the search centre. Must be supplied with lat.",
    )
    radius_km = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        min_value=Decimal("0.1"),
        max_value=Decimal("20000"),
        required=False,
        help_text="Radius in km around lat/lng. Default 5, max 20000. Requires lat and lng.",
    )
    ordering = serializers.ChoiceField(
        choices=("distance", "newest", "price_asc", "price_desc"),
        required=False,
        help_text="Result ordering. Defaults to distance when a radius is used, else newest.",
    )

    def validate(self, attrs):
        """Validate cross field rules and normalise the geo parameters.

        Args:
            attrs: Field level validated query params.

        Returns:
            The normalised query params, including ``has_geo_filter``.

        Raises:
            serializers.ValidationError: If the combination of parameters is
                inconsistent (missing lng, radius without coordinates or
                ``max_price`` below ``min_price``).
        """
        lat = attrs.get("lat")
        lng = attrs.get("lng")
        radius = attrs.get("radius_km")

        if (lat is None) != (lng is None):
            missing_field = "lng" if lat is not None else "lat"
            raise serializers.ValidationError(
                {missing_field: ["lat and lng must be supplied together."]}
            )
        if lat is None and radius is not None:
            raise serializers.ValidationError({"radius_km": ["radius_km requires lat and lng."]})

        min_price = attrs.get("min_price")
        max_price = attrs.get("max_price")
        if min_price is not None and max_price is not None and min_price > max_price:
            raise serializers.ValidationError(
                {"max_price": ["max_price must be greater than or equal to min_price."]}
            )

        attrs["has_geo_filter"] = lat is not None
        return attrs
