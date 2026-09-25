"""Django admin configuration for users."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from apps.accounts.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Admin definition for the custom user model.

    Extends the stock ``UserAdmin`` with role/phone fields and exposes soft
    deleted users through the read-only ``all_objects`` manager.
    """

    list_display = (
        "username",
        "email",
        "role",
        "is_active",
        "is_staff",
        "created_at",
        "deleted_at",
    )
    list_filter = ("role", "is_active", "is_staff", "is_superuser", "deleted_at")
    search_fields = ("username", "email", "first_name", "last_name", "phone_number")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "created_by",
        "updated_by",
        "deleted_by",
    )
    fieldsets = (
        (None, {"fields": ("id", "username", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "phone_number",
                    "role",
                )
            },
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
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
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "username",
                    "email",
                    "password1",
                    "password2",
                    "role",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )

    def get_queryset(self, request):
        """Return live and soft deleted users for admin browsing.

        Args:
            request: Current admin request.

        Returns:
            A queryset based on the ``all_objects`` manager.
        """
        return self.model.all_objects.get_queryset()
