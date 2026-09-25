"""Documentation helper serializers shared across the API schema."""

from rest_framework import serializers


class PaginationMetaSerializer(serializers.Serializer):
    """Pagination metadata included in ``meta`` of paginated responses."""

    page = serializers.IntegerField(help_text="Current page number (1 indexed).")
    page_size = serializers.IntegerField(help_text="Number of items per page.")
    total_count = serializers.IntegerField(help_text="Total number of matching items.")
    total_pages = serializers.IntegerField(help_text="Total number of pages.")
    next = serializers.URLField(allow_null=True, help_text="URL of the next page.")
    previous = serializers.URLField(allow_null=True, help_text="URL of the previous page.")


class ErrorResponseSerializer(serializers.Serializer):
    """The error envelope returned by every failure response."""

    success = serializers.BooleanField(help_text="Always False for errors.")
    message = serializers.CharField(help_text="Human readable error summary.")
    errors = serializers.DictField(
        required=False,
        help_text='Field level error details, e.g. {"email": ["Required"]}.',
    )
    error_code = serializers.CharField(
        help_text="Machine readable code, e.g. validation_error, not_found."
    )
