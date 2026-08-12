import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView

from apps.accounts.models import User
from apps.institutions.models import Organization

from .forms import (
    AuditCaseForm,
    AuditorReassignmentForm,
    ClosureRequestForm,
    DecisionResolutionForm,
    FindingForm,
    RecommendationForm,
    ResponseForm,
    ReviewForm,
)
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
from .pdf import build_response_receipt


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")


def log_activity(request, action, case=None, target=None, details=None):
    ActivityLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        case=case,
        action=action,
        target_type=target.__class__.__name__ if target else "",
        target_id=str(target.pk) if target else "",
        details=details or {},
        ip_address=get_client_ip(request),
    )


def user_can_create_cases(user):
    return user.is_authenticated and user.role == User.Role.AUDITOR


def user_is_director(user):
    return user.is_authenticated and user.role == User.Role.AUDIT_MANAGER


def user_can_edit_case(user, case):
    if not user.is_authenticated or case.status != AuditCase.Status.DRAFT:
        return False
    return user.role == User.Role.AUDITOR and case.assigned_auditor_id == user.pk


def get_editable_case(user, pk):
    case = get_object_or_404(
        AuditCase.objects.select_related("audited_organization", "assigned_auditor"),
        pk=pk,
    )
    if not user_can_edit_case(user, case):
        raise PermissionDenied("No tiene autorización para modificar este expediente.")
    return case


def publication_issues(case):
    findings = list(case.findings.prefetch_related("recommendations"))
    issues = []
    if not case.report_file:
        issues.append("Adjunte el informe final en formato PDF.")
    if not case.report_date:
        issues.append("Indique la fecha oficial del informe.")
    if not case.response_deadline:
        issues.append("Indique la fecha límite general de respuesta.")
    if not findings:
        issues.append("Registre al menos un hallazgo.")
    for finding in findings:
        recommendations = list(finding.recommendations.all())
        if not recommendations:
            issues.append(f"El hallazgo {finding.number} necesita al menos una recomendación.")
        for recommendation in recommendations:
            if not recommendation.deadline:
                issues.append(
                    f"La recomendación {finding.number}.{recommendation.number} necesita fecha límite."
                )
    return issues


def closure_issues(case):
    recommendations = Recommendation.objects.filter(finding__case=case)
    issues = []
    if not recommendations.exists():
        issues.append("El expediente no contiene recomendaciones.")
        return issues
    open_recommendations = recommendations.exclude(
        status__in=[
            Recommendation.Status.COMPLIED,
            Recommendation.Status.PARTIAL,
            Recommendation.Status.NOT_COMPLIED,
        ]
    ).count()
    if open_recommendations:
        issues.append(
            f"Aún hay {open_recommendations} recomendación"
            f"{'es' if open_recommendations != 1 else ''} sin resultado definitivo."
        )
    return issues


def accessible_cases(user):
    queryset = AuditCase.objects.select_related("audited_organization", "assigned_auditor")
    if user.is_superuser or user.role in {User.Role.TECHNICAL_ADMIN, User.Role.AUDIT_MANAGER}:
        return queryset
    if user.role == User.Role.AUDITOR:
        return queryset.filter(assigned_auditor=user)
    if not user.organization_id:
        return queryset.none()
    return queryset.exclude(
        status__in=[AuditCase.Status.DRAFT, AuditCase.Status.PENDING_PUBLICATION]
    ).filter(
        Q(audited_organization_id=user.organization_id)
        | Q(findings__recommendations__responsible_organization_id=user.organization_id)
    ).distinct()


def get_accessible_case(user, pk):
    return get_object_or_404(accessible_cases(user), pk=pk)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "audits/dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == User.Role.AUDIT_MANAGER:
            return redirect("director_dashboard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cases = accessible_cases(self.request.user)
        context["recent_cases"] = cases[:6]
        context["total_cases"] = cases.count()
        context["open_cases"] = cases.exclude(status=AuditCase.Status.CLOSED).count()
        if self.request.user.is_audit_staff:
            context["pending_recommendations"] = Recommendation.objects.filter(
                finding__case__in=cases,
                status__in=[
                    Recommendation.Status.SUBMITTED,
                    Recommendation.Status.UNDER_REVIEW,
                ]
            ).count()
        elif self.request.user.organization_id:
            context["pending_recommendations"] = Recommendation.objects.filter(
                responsible_organization_id=self.request.user.organization_id,
                status__in=[Recommendation.Status.PENDING, Recommendation.Status.CORRECTION_REQUIRED],
            ).count()
        else:
            context["pending_recommendations"] = 0
        return context


class DirectorDashboardView(LoginRequiredMixin, TemplateView):
    template_name = "audits/director_dashboard.html"

    def dispatch(self, request, *args, **kwargs):
        if not user_is_director(request.user):
            raise PermissionDenied("Esta sección es exclusiva de la Dirección de Auditoría.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = timezone.localdate()
        cases = AuditCase.objects.all()
        open_recommendation_statuses = [
            Recommendation.Status.PENDING,
            Recommendation.Status.SUBMITTED,
            Recommendation.Status.UNDER_REVIEW,
            Recommendation.Status.CORRECTION_REQUIRED,
        ]
        pending_decisions = CaseDecision.objects.filter(status=CaseDecision.Status.PENDING)
        terminal_recommendations = Recommendation.objects.filter(
            status__in=[
                Recommendation.Status.COMPLIED,
                Recommendation.Status.PARTIAL,
                Recommendation.Status.NOT_COMPLIED,
            ]
        )
        complied = terminal_recommendations.filter(status=Recommendation.Status.COMPLIED).count()
        terminal_count = terminal_recommendations.count()

        active_institutional_user = User.objects.filter(
            organization_id=OuterRef("pk"),
            role=User.Role.INSTITUTION,
            is_active=True,
        )
        centers_without_users = (
            Organization.objects.filter(
                recommendations__finding__case__status__in=[
                    AuditCase.Status.PUBLISHED,
                    AuditCase.Status.IN_RESPONSE,
                    AuditCase.Status.UNDER_REVIEW,
                    AuditCase.Status.CORRECTION_REQUIRED,
                    AuditCase.Status.PENDING_CLOSURE,
                ]
            )
            .annotate(has_active_user=Exists(active_institutional_user))
            .filter(has_active_user=False)
            .distinct()
        )
        auditor_workload = (
            User.objects.filter(role=User.Role.AUDITOR, is_active=True)
            .annotate(
                open_cases_count=Count(
                    "assigned_cases",
                    filter=~Q(assigned_cases__status=AuditCase.Status.CLOSED),
                    distinct=True,
                ),
                pending_reviews_count=Count(
                    "assigned_cases__findings__recommendations__responses",
                    filter=Q(
                        assigned_cases__findings__recommendations__responses__review__isnull=True
                    ),
                    distinct=True,
                ),
            )
            .order_by("-open_cases_count", "first_name", "last_name", "username")
        )

        context.update(
            {
                "total_cases": cases.count(),
                "open_cases": cases.exclude(
                    status__in=[AuditCase.Status.DRAFT, AuditCase.Status.CLOSED]
                ).count(),
                "pending_decisions_count": pending_decisions.count(),
                "pending_decisions": pending_decisions.select_related(
                    "case__audited_organization", "case__assigned_auditor", "requested_by"
                )[:6],
                "overdue_recommendations": Recommendation.objects.filter(
                    deadline__lt=today,
                    status__in=open_recommendation_statuses,
                ).count(),
                "critical_findings": Finding.objects.filter(
                    risk_level=Finding.RiskLevel.CRITICAL
                )
                .exclude(case__status=AuditCase.Status.CLOSED)
                .count(),
                "pending_reviews": Response.objects.filter(review__isnull=True).count(),
                "compliance_rate": round((complied / terminal_count) * 100) if terminal_count else 0,
                "centers_without_users_count": centers_without_users.count(),
                "centers_without_users": centers_without_users.order_by("name")[:6],
                "auditor_workload": auditor_workload,
                "recent_decisions": CaseDecision.objects.exclude(
                    status=CaseDecision.Status.PENDING
                ).select_related("case", "decided_by")[:5],
            }
        )
        return context


def director_decision_list(request):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    if not user_is_director(request.user):
        raise PermissionDenied("Esta sección es exclusiva de la Dirección de Auditoría.")
    decisions = CaseDecision.objects.select_related(
        "case__audited_organization", "case__assigned_auditor", "requested_by", "decided_by"
    )
    status = request.GET.get("status", CaseDecision.Status.PENDING)
    kind = request.GET.get("kind", "")
    if status in CaseDecision.Status.values:
        decisions = decisions.filter(status=status)
    if kind in CaseDecision.Kind.values:
        decisions = decisions.filter(kind=kind)
    return render(
        request,
        "audits/director_decision_list.html",
        {
            "decisions": decisions,
            "selected_status": status,
            "selected_kind": kind,
            "statuses": CaseDecision.Status.choices,
            "kinds": CaseDecision.Kind.choices,
        },
    )


@transaction.atomic
def director_decision_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    if not user_is_director(request.user):
        raise PermissionDenied("Esta decisión corresponde a la Dirección de Auditoría.")
    decision = get_object_or_404(
        CaseDecision.objects.select_for_update().select_related(
            "case__audited_organization", "case__assigned_auditor", "requested_by", "decided_by"
        ),
        pk=pk,
    )
    case = decision.case
    form = DecisionResolutionForm(request.POST or None)
    if request.method == "POST":
        if decision.status != CaseDecision.Status.PENDING:
            messages.info(request, "Esta solicitud ya fue resuelta.")
            return redirect("director_decision_detail", pk=decision.pk)
        if form.is_valid():
            action = form.cleaned_data["action"]
            justification = form.cleaned_data["justification"]
            if action == DecisionResolutionForm.Action.APPROVE:
                if decision.kind == CaseDecision.Kind.PUBLICATION:
                    if case.status != AuditCase.Status.PENDING_PUBLICATION:
                        messages.error(request, "El expediente ya no está pendiente de publicación.")
                        return redirect("director_decision_detail", pk=decision.pk)
                    if publication_issues(case):
                        messages.error(
                            request,
                            "El expediente dejó de reunir los requisitos de publicación.",
                        )
                        return redirect("director_decision_detail", pk=decision.pk)
                    case.status = AuditCase.Status.PUBLISHED
                    activity_action = "case_publication_approved"
                else:
                    if case.status != AuditCase.Status.PENDING_CLOSURE:
                        messages.error(request, "El expediente ya no está pendiente de cierre.")
                        return redirect("director_decision_detail", pk=decision.pk)
                    if closure_issues(case):
                        messages.error(
                            request,
                            "El expediente ya no reúne las condiciones para el cierre.",
                        )
                        return redirect("director_decision_detail", pk=decision.pk)
                    case.status = AuditCase.Status.CLOSED
                    activity_action = "case_closure_approved"
                decision.status = CaseDecision.Status.APPROVED
                success_message = f"La solicitud de {decision.get_kind_display().lower()} fue aprobada."
            else:
                if decision.kind == CaseDecision.Kind.PUBLICATION:
                    case.status = AuditCase.Status.DRAFT
                    activity_action = "case_publication_returned"
                else:
                    case.status = decision.previous_case_status or AuditCase.Status.UNDER_REVIEW
                    activity_action = "case_closure_returned"
                decision.status = CaseDecision.Status.RETURNED
                success_message = f"La solicitud de {decision.get_kind_display().lower()} fue devuelta."

            decision.decision_note = justification
            decision.decided_by = request.user
            decision.decided_at = timezone.now()
            case.save(update_fields=["status", "updated_at"])
            decision.save(
                update_fields=["status", "decision_note", "decided_by", "decided_at"]
            )
            log_activity(
                request,
                activity_action,
                case=case,
                target=decision,
                details={"justification": justification},
            )
            messages.success(request, success_message)
            return redirect("director_decisions")
    findings = case.findings.prefetch_related("recommendations__responsible_organization")
    return render(
        request,
        "audits/director_decision_detail.html",
        {"decision": decision, "case": case, "findings": findings, "form": form},
    )


class CaseListView(LoginRequiredMixin, ListView):
    template_name = "audits/case_list.html"
    context_object_name = "cases"
    paginate_by = 20

    def get_queryset(self):
        queryset = accessible_cases(self.request.user)
        search = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search)
                | Q(title__icontains=search)
                | Q(audited_organization__name__icontains=search)
                | Q(audited_organization__code__icontains=search)
                | Q(assigned_auditor__username__icontains=search)
                | Q(assigned_auditor__first_name__icontains=search)
                | Q(assigned_auditor__last_name__icontains=search)
            )
        if status in AuditCase.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["statuses"] = AuditCase.Status.choices
        return context


@transaction.atomic
def case_create(request):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    if not user_can_create_cases(request.user):
        raise PermissionDenied("Esta acción corresponde al personal auditor autorizado.")
    form = AuditCaseForm(
        request.POST or None,
        request.FILES or None,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        case = form.save(commit=False)
        case.status = AuditCase.Status.DRAFT
        case.created_by = request.user
        if request.user.role == User.Role.AUDITOR:
            case.assigned_auditor = request.user
        case.save()
        log_activity(request, "case_draft_created", case=case, target=case)
        messages.success(request, "El borrador fue creado. Ahora agregue los hallazgos y recomendaciones.")
        return redirect("case_builder", pk=case.pk)
    return render(
        request,
        "audits/case_form.html",
        {"form": form, "case": None, "form_title": "Nuevo expediente"},
    )


@transaction.atomic
def case_edit(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_editable_case(request.user, pk)
    form = AuditCaseForm(
        request.POST or None,
        request.FILES or None,
        instance=case,
        user=request.user,
    )
    if request.method == "POST" and form.is_valid():
        case = form.save()
        log_activity(request, "case_draft_updated", case=case, target=case)
        messages.success(request, "Los datos generales del expediente fueron actualizados.")
        return redirect("case_builder", pk=case.pk)
    return render(
        request,
        "audits/case_form.html",
        {"form": form, "case": case, "form_title": "Editar datos generales"},
    )


def case_builder(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_editable_case(request.user, pk)
    findings = case.findings.prefetch_related("recommendations__responsible_organization")
    return render(
        request,
        "audits/case_builder.html",
        {"case": case, "findings": findings, "publication_issues": publication_issues(case)},
    )


@transaction.atomic
def finding_create(request, case_pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_editable_case(request.user, case_pk)
    next_number = (case.findings.aggregate(value=Max("number"))["value"] or 0) + 1
    form = FindingForm(request.POST or None, initial={"number": next_number})
    if request.method == "POST" and form.is_valid():
        finding = form.save(commit=False)
        finding.case = case
        finding.save()
        log_activity(request, "finding_created", case=case, target=finding)
        messages.success(request, f"El hallazgo {finding.number} fue agregado.")
        return redirect("case_builder", pk=case.pk)
    return render(
        request,
        "audits/editor_form.html",
        {
            "form": form,
            "case": case,
            "form_title": "Agregar hallazgo",
            "form_intro": "Registre la información que fundamenta el hallazgo.",
            "submit_label": "Guardar hallazgo",
        },
    )


@transaction.atomic
def finding_edit(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    finding = get_object_or_404(Finding.objects.select_related("case"), pk=pk)
    case = get_editable_case(request.user, finding.case_id)
    form = FindingForm(request.POST or None, instance=finding)
    if request.method == "POST" and form.is_valid():
        finding = form.save()
        log_activity(request, "finding_updated", case=case, target=finding)
        messages.success(request, f"El hallazgo {finding.number} fue actualizado.")
        return redirect("case_builder", pk=case.pk)
    return render(
        request,
        "audits/editor_form.html",
        {
            "form": form,
            "case": case,
            "form_title": f"Editar hallazgo {finding.number}",
            "form_intro": "Actualice la información del hallazgo antes de publicar.",
            "submit_label": "Guardar cambios",
        },
    )


@require_POST
@transaction.atomic
def finding_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    finding = get_object_or_404(Finding.objects.select_related("case"), pk=pk)
    case = get_editable_case(request.user, finding.case_id)
    number = finding.number
    log_activity(request, "finding_deleted", case=case, target=finding, details={"number": number})
    finding.delete()
    messages.success(request, f"El hallazgo {number} y sus recomendaciones fueron eliminados.")
    return redirect("case_builder", pk=case.pk)


@transaction.atomic
def recommendation_create(request, finding_pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    finding = get_object_or_404(Finding.objects.select_related("case"), pk=finding_pk)
    case = get_editable_case(request.user, finding.case_id)
    next_number = (finding.recommendations.aggregate(value=Max("number"))["value"] or 0) + 1
    form = RecommendationForm(
        request.POST or None,
        initial={
            "number": next_number,
            "responsible_organization": case.audited_organization_id,
            "deadline": case.response_deadline,
        },
    )
    if request.method == "POST" and form.is_valid():
        recommendation = form.save(commit=False)
        recommendation.finding = finding
        recommendation.save()
        log_activity(request, "recommendation_created", case=case, target=recommendation)
        messages.success(request, f"La recomendación {finding.number}.{recommendation.number} fue agregada.")
        return redirect("case_builder", pk=case.pk)
    return render(
        request,
        "audits/editor_form.html",
        {
            "form": form,
            "case": case,
            "form_title": f"Agregar recomendación al hallazgo {finding.number}",
            "form_intro": "Asigne un responsable, una fecha límite y la evidencia esperada.",
            "submit_label": "Guardar recomendación",
        },
    )


@transaction.atomic
def recommendation_edit(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    recommendation = get_object_or_404(
        Recommendation.objects.select_related("finding__case"), pk=pk
    )
    case = get_editable_case(request.user, recommendation.finding.case_id)
    form = RecommendationForm(request.POST or None, instance=recommendation)
    if request.method == "POST" and form.is_valid():
        recommendation = form.save()
        log_activity(request, "recommendation_updated", case=case, target=recommendation)
        messages.success(
            request,
            f"La recomendación {recommendation.finding.number}.{recommendation.number} fue actualizada.",
        )
        return redirect("case_builder", pk=case.pk)
    return render(
        request,
        "audits/editor_form.html",
        {
            "form": form,
            "case": case,
            "form_title": (
                f"Editar recomendación {recommendation.finding.number}.{recommendation.number}"
            ),
            "form_intro": "Actualice la asignación y los requisitos antes de publicar.",
            "submit_label": "Guardar cambios",
        },
    )


@require_POST
@transaction.atomic
def recommendation_delete(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    recommendation = get_object_or_404(
        Recommendation.objects.select_related("finding__case"), pk=pk
    )
    case = get_editable_case(request.user, recommendation.finding.case_id)
    label = f"{recommendation.finding.number}.{recommendation.number}"
    log_activity(
        request,
        "recommendation_deleted",
        case=case,
        target=recommendation,
        details={"number": label},
    )
    recommendation.delete()
    messages.success(request, f"La recomendación {label} fue eliminada.")
    return redirect("case_builder", pk=case.pk)


@transaction.atomic
def case_publish(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_object_or_404(
        AuditCase.objects.select_for_update().select_related(
            "audited_organization", "assigned_auditor"
        ),
        pk=pk,
    )
    if not user_can_edit_case(request.user, case):
        raise PermissionDenied("No tiene autorización para enviar este expediente.")
    issues = publication_issues(case)
    findings = case.findings.prefetch_related("recommendations__responsible_organization")
    if request.method == "POST":
        if issues:
            messages.error(request, "Complete los requisitos señalados antes de publicar.")
        else:
            decision = CaseDecision.objects.create(
                case=case,
                kind=CaseDecision.Kind.PUBLICATION,
                requested_by=request.user,
                previous_case_status=case.status,
            )
            case.status = AuditCase.Status.PENDING_PUBLICATION
            case.save(update_fields=["status", "updated_at"])
            log_activity(request, "case_publication_requested", case=case, target=decision)
            messages.success(
                request,
                "El expediente fue enviado a la Dirección de Auditoría para aprobación.",
            )
            return redirect("case_detail", pk=case.pk)
    return render(
        request,
        "audits/case_publish.html",
        {"case": case, "findings": findings, "publication_issues": issues},
    )


@transaction.atomic
def request_case_closure(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_object_or_404(
        AuditCase.objects.select_for_update().select_related(
            "audited_organization", "assigned_auditor"
        ),
        pk=pk,
    )
    if request.user.role != User.Role.AUDITOR or case.assigned_auditor_id != request.user.pk:
        raise PermissionDenied("Solo el auditor asignado puede solicitar el cierre.")
    if case.status in {
        AuditCase.Status.DRAFT,
        AuditCase.Status.PENDING_PUBLICATION,
        AuditCase.Status.PENDING_CLOSURE,
        AuditCase.Status.CLOSED,
    }:
        raise PermissionDenied("El expediente no admite una solicitud de cierre en su estado actual.")
    issues = closure_issues(case)
    form = ClosureRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if issues:
            messages.error(request, "Complete la revisión de las recomendaciones antes de solicitar el cierre.")
        else:
            previous_status = case.status
            decision = CaseDecision.objects.create(
                case=case,
                kind=CaseDecision.Kind.CLOSURE,
                request_note=form.cleaned_data["justification"],
                previous_case_status=previous_status,
                requested_by=request.user,
            )
            case.status = AuditCase.Status.PENDING_CLOSURE
            case.save(update_fields=["status", "updated_at"])
            log_activity(
                request,
                "case_closure_requested",
                case=case,
                target=decision,
                details={"justification": form.cleaned_data["justification"]},
            )
            messages.success(request, "La solicitud de cierre fue enviada a la Dirección de Auditoría.")
            return redirect("case_detail", pk=case.pk)
    return render(
        request,
        "audits/case_closure_request.html",
        {"case": case, "form": form, "closure_issues": issues},
    )


@transaction.atomic
def director_reassign_case(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    if not user_is_director(request.user):
        raise PermissionDenied("La reasignación corresponde a la Dirección de Auditoría.")
    case = get_object_or_404(
        AuditCase.objects.select_for_update().select_related(
            "audited_organization", "assigned_auditor"
        ),
        pk=pk,
    )
    if case.status == AuditCase.Status.CLOSED:
        raise PermissionDenied("Un expediente cerrado no puede reasignarse.")
    previous_auditor = case.assigned_auditor
    form = AuditorReassignmentForm(
        request.POST or None,
        current_auditor=previous_auditor,
    )
    if request.method == "POST" and form.is_valid():
        new_auditor = form.cleaned_data["assigned_auditor"]
        justification = form.cleaned_data["justification"]
        case.assigned_auditor = new_auditor
        case.save(update_fields=["assigned_auditor", "updated_at"])
        log_activity(
            request,
            "case_reassigned",
            case=case,
            target=case,
            details={
                "previous_auditor_id": previous_auditor.pk,
                "previous_auditor": previous_auditor.get_full_name() or previous_auditor.username,
                "new_auditor_id": new_auditor.pk,
                "new_auditor": new_auditor.get_full_name() or new_auditor.username,
                "justification": justification,
            },
        )
        messages.success(request, "El expediente fue reasignado y la decisión quedó registrada.")
        return redirect("case_detail", pk=case.pk)
    return render(
        request,
        "audits/director_reassign_case.html",
        {"case": case, "form": form, "previous_auditor": previous_auditor},
    )


def case_detail(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_accessible_case(request.user, pk)
    findings = case.findings.prefetch_related(
        "recommendations__responsible_organization",
        "recommendations__responses__evidence",
        "recommendations__responses__review",
    )
    return render(
        request,
        "audits/case_detail.html",
        {
            "case": case,
            "findings": findings,
            "can_edit_case": user_can_edit_case(request.user, case),
            "can_request_closure": (
                request.user.role == User.Role.AUDITOR
                and case.assigned_auditor_id == request.user.pk
                and case.status
                not in {
                    AuditCase.Status.DRAFT,
                    AuditCase.Status.PENDING_PUBLICATION,
                    AuditCase.Status.PENDING_CLOSURE,
                    AuditCase.Status.CLOSED,
                }
            ),
            "closure_issues": closure_issues(case),
            "pending_decision": case.decisions.filter(
                status=CaseDecision.Status.PENDING
            ).first(),
            "can_reassign_case": user_is_director(request.user)
            and case.status != AuditCase.Status.CLOSED,
        },
    )


def download_report(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    case = get_accessible_case(request.user, pk)
    if not case.report_file:
        raise Http404("Este expediente no tiene un informe adjunto.")
    log_activity(request, "report_downloaded", case=case, target=case)
    return FileResponse(
        case.report_file.open("rb"),
        as_attachment=True,
        filename=f"{case.reference}.pdf",
    )


@transaction.atomic
def respond_recommendation(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    recommendation = get_object_or_404(
        Recommendation.objects.select_related("finding__case", "responsible_organization"), pk=pk
    )
    case = recommendation.finding.case
    if case.status in {
        AuditCase.Status.DRAFT,
        AuditCase.Status.PENDING_PUBLICATION,
        AuditCase.Status.PENDING_CLOSURE,
        AuditCase.Status.CLOSED,
    }:
        raise Http404("La recomendación aún no ha sido publicada.")
    if (
        request.user.role != User.Role.INSTITUTION
        or not request.user.organization_id
        or recommendation.responsible_organization_id != request.user.organization_id
    ):
        raise PermissionDenied("No tiene autorización para responder esta recomendación.")
    if recommendation.status not in {
        Recommendation.Status.PENDING,
        Recommendation.Status.CORRECTION_REQUIRED,
    }:
        messages.info(request, "Esta recomendación no admite una respuesta nueva en su estado actual.")
        return redirect("case_detail", pk=case.pk)

    if request.method == "POST":
        form = ResponseForm(request.POST, request.FILES)
        if form.is_valid():
            latest_version = recommendation.responses.aggregate(value=Max("version"))["value"] or 0
            response = form.save(commit=False)
            response.recommendation = recommendation
            response.version = latest_version + 1
            response.submitted_by = request.user
            response.save()

            for uploaded_file in form.cleaned_data["files"]:
                digest = hashlib.sha256()
                for chunk in uploaded_file.chunks():
                    digest.update(chunk)
                uploaded_file.seek(0)
                Evidence.objects.create(
                    response=response,
                    file=uploaded_file,
                    original_filename=uploaded_file.name[:255],
                    category=form.cleaned_data["evidence_category"],
                    description=form.cleaned_data["evidence_description"],
                    size=uploaded_file.size,
                    sha256=digest.hexdigest(),
                    scan_status=(
                        Evidence.ScanStatus.PENDING
                        if settings.FILE_SCAN_REQUIRED
                        else Evidence.ScanStatus.CLEAN
                    ),
                    uploaded_by=request.user,
                )

            recommendation.status = Recommendation.Status.SUBMITTED
            recommendation.save(update_fields=["status"])
            if case.status != AuditCase.Status.CLOSED:
                case.status = AuditCase.Status.UNDER_REVIEW
                case.save(update_fields=["status", "updated_at"])
            log_activity(
                request,
                "response_submitted",
                case=case,
                target=response,
                details={"recommendation": recommendation.pk, "version": response.version},
            )
            messages.success(request, "La respuesta fue enviada y quedó registrada en el expediente.")
            return redirect("case_detail", pk=case.pk)
    else:
        form = ResponseForm(
            initial={
                "responsible_name": request.user.get_full_name(),
                "responsible_job_title": request.user.job_title,
            }
        )
    return render(
        request,
        "audits/respond.html",
        {"form": form, "recommendation": recommendation, "case": case},
    )


@transaction.atomic
def review_response(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    if request.user.role not in {User.Role.AUDITOR, User.Role.AUDIT_MANAGER}:
        raise PermissionDenied("Esta acción corresponde al personal de Auditoría.")
    response = get_object_or_404(
        Response.objects.select_related("recommendation__finding__case", "submitted_by"), pk=pk
    )
    get_accessible_case(request.user, response.recommendation.finding.case_id)
    if hasattr(response, "review"):
        messages.info(request, "Esta versión ya fue revisada.")
        return redirect("case_detail", pk=response.recommendation.finding.case_id)
    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.response = response
            review.reviewed_by = request.user
            review.save()
            recommendation = response.recommendation
            recommendation.status = {
                Review.Outcome.CORRECTION_REQUIRED: Recommendation.Status.CORRECTION_REQUIRED,
                Review.Outcome.COMPLIED: Recommendation.Status.COMPLIED,
                Review.Outcome.PARTIAL: Recommendation.Status.PARTIAL,
                Review.Outcome.NOT_COMPLIED: Recommendation.Status.NOT_COMPLIED,
            }[review.outcome]
            recommendation.save(update_fields=["status"])
            case = recommendation.finding.case
            if review.outcome == Review.Outcome.CORRECTION_REQUIRED:
                case.status = AuditCase.Status.CORRECTION_REQUIRED
                case.save(update_fields=["status", "updated_at"])
            log_activity(
                request,
                "response_reviewed",
                case=case,
                target=review,
                details={"outcome": review.outcome, "response": response.pk},
            )
            messages.success(request, "La revisión fue registrada correctamente.")
            return redirect("case_detail", pk=case.pk)
    else:
        form = ReviewForm()
    return render(request, "audits/review.html", {"form": form, "response": response})


def download_evidence(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    evidence = get_object_or_404(
        Evidence.objects.select_related("response__recommendation__finding__case"), pk=pk
    )
    case = evidence.response.recommendation.finding.case
    get_accessible_case(request.user, case.pk)
    if settings.FILE_SCAN_REQUIRED and evidence.scan_status != Evidence.ScanStatus.CLEAN:
        raise Http404("La evidencia aún no está disponible.")
    log_activity(request, "evidence_downloaded", case=case, target=evidence)
    return FileResponse(
        evidence.file.open("rb"),
        as_attachment=True,
        filename=evidence.original_filename,
    )


def response_receipt(request, pk):
    if not request.user.is_authenticated:
        return redirect(f"/ingresar/?next={request.path}")
    response = get_object_or_404(
        Response.objects.select_related(
            "recommendation__finding__case__audited_organization",
            "recommendation__responsible_organization",
        ).prefetch_related("evidence"),
        pk=pk,
    )
    case = response.recommendation.finding.case
    get_accessible_case(request.user, case.pk)
    pdf_buffer, folio = build_response_receipt(response)
    log_activity(request, "response_receipt_downloaded", case=case, target=response, details={"folio": folio})
    return FileResponse(pdf_buffer, as_attachment=True, filename=f"{folio}.pdf")
