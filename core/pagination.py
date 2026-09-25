"""Pagination shared by every list and search endpoint."""

from collections import OrderedDict
from typing import Any

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from core.responses import ResponseHandler


class StandardResultsSetPagination(PageNumberPagination):
    """Page number pagination that renders results in the standard envelope.

    Query parameters: ``page`` (1-indexed) and ``page_size``.
    """

    page_size = 10
    page_size_query_param = "page_size"
    page_query_param = "page"
    max_page_size = 50

    def get_paginated_response(self, data: Any) -> Response:
        """Return the paginated payload wrapped in the success envelope.

        Args:
            data: Serialised page of results.

        Returns:
            A DRF ``Response`` with the page in ``data`` and pagination
            details in ``meta``.
        """
        meta = OrderedDict(
            [
                ("page", self.page.number),
                ("page_size", self.get_page_size(self.request)),
                ("total_count", self.page.paginator.count),
                ("total_pages", self.page.paginator.num_pages),
                ("next", self.get_next_link()),
                ("previous", self.get_previous_link()),
            ]
        )
        return ResponseHandler.success(data=data, message="", meta=dict(meta))
