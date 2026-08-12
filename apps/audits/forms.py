from pathlib import Path

from django import forms

from apps.accounts.models import User
from apps.institutions.models import Organization

from apps.core.validators import validate_evidence_file

from .models import AuditCase, Evidence, Finding, Recommendation, Response, Review


class AuditCaseForm(forms.ModelForm):
    class Meta:
        model = AuditCase
        fields = (
            "reference",
            "title",
            "audited_organization",
            "report_file",
            "report_date",
            "period_start",
            "period_end",
            "response_deadline",
            "assigned_auditor",
        )
        widgets = {
            "title": forms.Textarea(attrs={"rows": 2}),
            "report_file": forms.ClearableFileInput(attrs={"accept": ".pdf,application/pdf"}),
            "report_date": forms.DateInput(attrs={"type": "date"}),
            "period_start": forms.DateInput(attrs={"type": "date"}),
            "period_end": forms.DateInput(attrs={"type": "date"}),
            "response_deadline": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "reference": "Use la referencia oficial y única del informe.",
            "report_file": "Puede guardarlo como borrador sin informe; se exigirá un PDF antes de publicar.",
            "response_deadline": "Fecha general para que las instituciones responsables respondan.",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["audited_organization"].queryset = Organization.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["assigned_auditor"].queryset = User.objects.filter(
            is_active=True,
            role=User.Role.AUDITOR,
        ).order_by("first_name", "last_name", "username")
        if user and user.role == User.Role.AUDITOR:
            self.fields["assigned_auditor"].queryset = User.objects.filter(pk=user.pk)
            self.fields["assigned_auditor"].initial = user.pk
            self.fields["assigned_auditor"].disabled = True
            self.fields["assigned_auditor"].help_text = "El expediente quedará asignado a usted."

    def clean_report_file(self):
        report = self.cleaned_data.get("report_file")
        if report and Path(report.name).suffix.lower() != ".pdf":
            raise forms.ValidationError("El informe de auditoría debe ser un archivo PDF.")
        return report

    def clean(self):
        cleaned = super().clean()
        period_start = cleaned.get("period_start")
        period_end = cleaned.get("period_end")
        report_date = cleaned.get("report_date")
        response_deadline = cleaned.get("response_deadline")
        if period_start and period_end and period_start > period_end:
            self.add_error("period_end", "El fin del período no puede ser anterior al inicio.")
        if report_date and response_deadline and response_deadline < report_date:
            self.add_error(
                "response_deadline",
                "La fecha límite de respuesta no puede ser anterior a la fecha del informe.",
            )
        return cleaned


class FindingForm(forms.ModelForm):
    class Meta:
        model = Finding
        fields = ("number", "title", "risk_level", "condition", "criteria", "cause", "effect")
        widgets = {
            "title": forms.Textarea(attrs={"rows": 2}),
            "condition": forms.Textarea(attrs={"rows": 4}),
            "criteria": forms.Textarea(attrs={"rows": 3}),
            "cause": forms.Textarea(attrs={"rows": 3}),
            "effect": forms.Textarea(attrs={"rows": 3}),
        }


class RecommendationForm(forms.ModelForm):
    class Meta:
        model = Recommendation
        fields = ("number", "text", "responsible_organization", "deadline", "evidence_requirements")
        widgets = {
            "text": forms.Textarea(attrs={"rows": 5}),
            "deadline": forms.DateInput(attrs={"type": "date"}),
            "evidence_requirements": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {
            "responsible_organization": "Puede ser el centro auditado u otra dependencia responsable.",
            "evidence_requirements": "Detalle los documentos que permitirán comprobar el cumplimiento.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["responsible_organization"].queryset = Organization.objects.filter(
            is_active=True
        ).order_by("name")


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)] if data else []


class ResponseForm(forms.ModelForm):
    evidence_category = forms.ChoiceField(label="Tipo de documentación", choices=Evidence.Category.choices)
    evidence_description = forms.CharField(
        label="Descripción de la documentación",
        max_length=300,
        help_text="Indique la relación de los archivos adjuntos con las acciones reportadas.",
    )
    files = MultipleFileField(
        label="Documentos de respaldo",
        validators=[validate_evidence_file],
        help_text="Formatos admitidos: PDF, JPG, PNG, DOCX o XLSX. Se aplica el límite configurado por archivo.",
    )

    class Meta:
        model = Response
        fields = (
            "declared_status",
            "action_description",
            "action_date",
            "responsible_name",
            "responsible_job_title",
            "non_compliance_reason",
            "action_plan",
            "expected_completion_date",
            "accuracy_declaration",
        )
        widgets = {
            "action_description": forms.Textarea(attrs={"rows": 5}),
            "action_date": forms.DateInput(attrs={"type": "date"}),
            "non_compliance_reason": forms.Textarea(attrs={"rows": 3}),
            "action_plan": forms.Textarea(attrs={"rows": 3}),
            "expected_completion_date": forms.DateInput(attrs={"type": "date"}),
        }
        help_texts = {
            "accuracy_declaration": "Declaro que la información y los archivos presentados son correctos.",
        }

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("declared_status")
        if status == Response.DeclaredStatus.COMPLETED and not cleaned.get("action_date"):
            self.add_error("action_date", "Indique la fecha en que se completó la acción.")
        if status == Response.DeclaredStatus.UNABLE:
            if not cleaned.get("non_compliance_reason"):
                self.add_error("non_compliance_reason", "Explique por qué no fue posible cumplir.")
            if not cleaned.get("action_plan"):
                self.add_error("action_plan", "Indique el plan de acción pendiente.")
            if not cleaned.get("expected_completion_date"):
                self.add_error("expected_completion_date", "Indique una fecha estimada de cumplimiento.")
        if not cleaned.get("accuracy_declaration"):
            self.add_error(
                "accuracy_declaration",
                "Debe aceptar la declaración de veracidad antes de enviar la respuesta.",
            )
        return cleaned


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ("outcome", "comments")
        widgets = {"comments": forms.Textarea(attrs={"rows": 6})}
