"""URL routing for the listings app."""

from rest_framework.routers import DefaultRouter

from apps.listings.views import ListingViewSet

app_name = "listings"

router = DefaultRouter()
router.register("listings", ListingViewSet, basename="listing")

urlpatterns = router.urls
