"""Django admin configuration for listings."""

from django.contrib import admin

from apps.listings.models import Listing


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    """Admin definition for property listings.

    Lists and filters every meaningful column, supports searching by title,
    location and agent, and exposes soft delete/restore actions.
    """

    list_display = (
        "title",
        "type",
        "price",
        "bedrooms",
        "location_name",
        "agent",
        "created_at",
        "deleted_at",
    )
    list_filter = ("type", "bedrooms", "created_at", "deleted_at")
    search_fields = ("title", "location_name", "agent__username", "agent__email")
    list_select_related = ("agent",)
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "latitude",
        "longitude",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
        "deleted_by",
    )
    fieldsets = (
        (
            "Listing",
            {
                "fields": (
                    "id",
                    "title",
                    "type",
                    "price",
                    "bedrooms",
                    "agent",
                )
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "location_name",
                    "location",
                    "latitude",
                    "longitude",
                )
            },
        ),
        (
            "Audit",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                    "deleted_at",
                    "created_by",
                    "updated_by",
                    "deleted_by",
                )
            },
        ),
    )
    actions = ("restore_selected", "hard_delete_selected")

    def get_queryset(self, request):
        """Return live and soft deleted listings for admin browsing.

        Args:
            request: Current admin request.

        Returns:
            A queryset based on the ``all_objects`` manager.
        """
        return self.model.all_objects.select_related("agent")

    @admin.action(description="Restore selected listings")
    def restore_selected(self, request, queryset):
        """Clear the soft delete marker for the selected listings."""
        queryset.filter(deleted_at__isnull=False).update(deleted_at=None, deleted_by=None)
        self.message_user(request, "Selected listings restored.")
        return None

    @admin.action(description="Permanently delete selected listings")
    def hard_delete_selected(self, request, queryset):
        """Physically delete the selected listings, ignoring soft deletes."""
        count, _ = queryset.hard_delete()
        self.message_user(request, f"{count} listing(s) permanently deleted.")
        return None
