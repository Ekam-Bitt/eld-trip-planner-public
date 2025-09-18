from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Driver


@admin.register(Driver)
class DriverAdmin(BaseUserAdmin):
    ordering = ["id"]
    list_display = ["email", "name", "license_no", "is_active", "is_staff"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "license_no", "truck_type", "avg_mpg")}),
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
        ("Important dates", {"fields": ("last_login",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "name",
                    "license_no",
                    "truck_type",
                    "avg_mpg",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    search_fields = ("email", "name", "license_no")
