"""Root URL configuration: admin, API v1, auth tokens and API docs."""

from django.contrib import admin
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.exception_handler import api_not_found

schema_view = get_schema_view(
    openapi.Info(
        title="Property Listings API",
        default_version="v1",
        description=(
            "API for browsing, searching and managing property listings. "
            "Read endpoints are public; write endpoints require a JWT access token."
        ),
        contact=openapi.Contact(name="Property Listings API"),
        license=openapi.License(name="MIT"),
    ),
    public=True,
    permission_classes=(AllowAny,),
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path(
        "api/v1/auth/token/refresh/",
        TokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path("api/v1/", include("apps.listings.urls")),
    path("swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="swagger-ui"),
    path(
        "swagger.json",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    path("redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="redoc"),
    # Catch-all so unknown API paths always return the JSON error envelope,
    # even when DEBUG is on (Django's handler404 only applies with DEBUG=False).
    re_path(r"^api/.*$", api_not_found),
]

handler404 = "core.exception_handler.api_not_found"
handler500 = "core.exception_handler.api_internal_server_error"
