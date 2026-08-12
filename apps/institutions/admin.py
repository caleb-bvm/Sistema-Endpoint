from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "kind", "department", "municipality", "is_active")
    list_filter = ("kind", "department", "is_active")
    search_fields = ("code", "name", "department", "municipality")

