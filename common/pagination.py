
"""Reusable pagination classes for the OmaxasAI REST API."""

from rest_framework.pagination import (
    CursorPagination,
    PageNumberPagination,
)
from rest_framework.response import Response


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard page-number pagination for API list endpoints.

    Example:
        /api/knowledge/?page=2&page_size=20
    """

    page_size = 20
    page_size_query_param = "page_size"
    page_query_param = "page"
    max_page_size = 100

    def get_paginated_response(self, data):
        """Return results with useful pagination metadata."""

        return Response(
            {
                "success": True,
                "pagination": {
                    "count": self.page.paginator.count,
                    "page": self.page.number,
                    "page_size": self.get_page_size(self.request),
                    "total_pages": self.page.paginator.num_pages,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                },
                "results": data,
            }
        )


class SmallResultsSetPagination(StandardResultsSetPagination):
    """Pagination for endpoints where smaller pages are preferable."""

    page_size = 10
    max_page_size = 50


class LargeResultsSetPagination(StandardResultsSetPagination):
    """Pagination for endpoints that may return more records per page."""

    page_size = 50
    max_page_size = 100


class StandardCursorPagination(CursorPagination):
    """
    Cursor pagination for consistently ordered, frequently changing feeds.

    The queryset must have a stable ordering field, such as created_at.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    cursor_query_param = "cursor"
    ordering = "-created_at"


class SmallCursorPagination(StandardCursorPagination):
    """Cursor pagination for smaller, frequently refreshed feeds."""

    page_size = 10
    max_page_size = 50

