from django import forms

from apps.core.validators import validate_evidence_file

from .models import Evidence, Response, Review


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
