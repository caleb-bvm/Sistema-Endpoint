from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "get_full_name", "role", "organization", "is_active")
    list_filter = ("role", "is_active", "organization__kind")
    search_fields = ("username", "first_name", "last_name", "email", "organization__name")
    fieldsets = UserAdmin.fieldsets + (
        (
            "Acceso institucional",
            {"fields": ("role", "organization", "job_title", "must_change_password")},
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Acceso institucional",
            {"fields": ("role", "organization", "job_title", "must_change_password")},
        ),
    )

