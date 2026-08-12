from django.contrib import admin

from .models import (
    ActivityLog,
    AuditCase,
    CaseDecision,
    Evidence,
    Finding,
    Recommendation,
    Response,
    Review,
)


class RecommendationInline(admin.StackedInline):
    model = Recommendation
    extra = 0


@admin.register(AuditCase)
class AuditCaseAdmin(admin.ModelAdmin):
    list_display = ("reference", "audited_organization", "status", "assigned_auditor", "response_deadline")
    list_filter = ("status", "audited_organization__department")
    search_fields = ("reference", "title", "audited_organization__name", "audited_organization__code")
    autocomplete_fields = ("audited_organization", "assigned_auditor", "created_by")


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("case", "number", "title", "risk_level")
    list_filter = ("risk_level",)
    search_fields = ("case__reference", "title")
    inlines = (RecommendationInline,)


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    list_display = ("__str__", "responsible_organization", "deadline", "status")
    list_filter = ("status", "deadline", "responsible_organization__kind")
    search_fields = ("finding__case__reference", "text", "responsible_organization__name")


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("recommendation", "version", "declared_status", "submitted_by", "submitted_at")
    list_filter = ("declared_status", "submitted_at")
    readonly_fields = ("submitted_at",)


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "response", "category", "scan_status", "uploaded_at")
    list_filter = ("scan_status", "category")
    search_fields = ("original_filename", "description", "sha256")
    readonly_fields = ("sha256", "size", "uploaded_at")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("response", "outcome", "reviewed_by", "reviewed_at")
    list_filter = ("outcome",)
    readonly_fields = ("reviewed_at",)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "case", "ip_address")
    list_filter = ("action", "created_at")
    search_fields = ("actor__username", "case__reference", "target_id")
    readonly_fields = (
        "actor",
        "case",
        "action",
        "target_type",
        "target_id",
        "details",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CaseDecision)
class CaseDecisionAdmin(admin.ModelAdmin):
    list_display = ("requested_at", "case", "kind", "status", "requested_by", "decided_by")
    list_filter = ("kind", "status", "requested_at")
    search_fields = ("case__reference", "case__audited_organization__name", "decision_note")
    readonly_fields = (
        "case",
        "kind",
        "status",
        "request_note",
        "previous_case_status",
        "requested_by",
        "requested_at",
        "decision_note",
        "decided_by",
        "decided_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
