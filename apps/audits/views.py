import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView, TemplateView

from apps.accounts.models import User

from .forms import AuditCaseForm, FindingForm, RecommendationForm, ResponseForm, ReviewForm
from .models import ActivityLog, AuditCase, Evidence, Finding, Recommendation, Response, Review
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
    return user.is_authenticated and (
        user.is_superuser or user.role in {User.Role.AUDIT_MANAGER, User.Role.AUDITOR}
    )


def user_can_edit_case(user, case):
    if not user.is_authenticated or case.status != AuditCase.Status.DRAFT:
        return False
    if user.is_superuser or user.role == User.Role.AUDIT_MANAGER:
        return True
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


def accessible_cases(user):
    queryset = AuditCase.objects.select_related("audited_organization", "assigned_auditor")
    if user.is_superuser or user.role in {User.Role.TECHNICAL_ADMIN, User.Role.AUDIT_MANAGER}:
        return queryset
    if user.role == User.Role.AUDITOR:
        return queryset.filter(assigned_auditor=user)
    if not user.organization_id:
        return queryset.none()
    return queryset.exclude(status=AuditCase.Status.DRAFT).filter(
        Q(audited_organization_id=user.organization_id)
        | Q(findings__recommendations__responsible_organization_id=user.organization_id)
    ).distinct()


def get_accessible_case(user, pk):
    return get_object_or_404(accessible_cases(user), pk=pk)


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = "audits/dashboard.html"

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
    case = get_editable_case(request.user, pk)
    issues = publication_issues(case)
    findings = case.findings.prefetch_related("recommendations__responsible_organization")
    if request.method == "POST":
        if issues:
            messages.error(request, "Complete los requisitos señalados antes de publicar.")
        else:
            case.status = AuditCase.Status.PUBLISHED
            case.save(update_fields=["status", "updated_at"])
            log_activity(request, "case_published", case=case, target=case)
            messages.success(
                request,
                "El expediente fue publicado y ya está disponible para las instituciones responsables.",
            )
            return redirect("case_detail", pk=case.pk)
    return render(
        request,
        "audits/case_publish.html",
        {"case": case, "findings": findings, "publication_issues": issues},
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
        {"case": case, "findings": findings, "can_edit_case": user_can_edit_case(request.user, case)},
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
    if case.status == AuditCase.Status.DRAFT:
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
    if not request.user.is_audit_staff:
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
