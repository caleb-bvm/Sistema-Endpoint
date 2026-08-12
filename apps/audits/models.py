import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.validators import validate_evidence_file


def private_upload_path(instance, filename):
    extension = Path(filename).suffix.lower()
    case_id = getattr(instance, "case_id", None)
    if not case_id and hasattr(instance, "response"):
        case_id = instance.response.recommendation.finding.case_id
    return f"expedientes/{case_id or 'pendiente'}/{uuid.uuid4().hex}{extension}"


class AuditCase(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Enviado"
        IN_RESPONSE = "in_response", "En respuesta"
        UNDER_REVIEW = "under_review", "En revisión"
        CORRECTION_REQUIRED = "correction_required", "Requiere corrección"
        CLOSED = "closed", "Cerrado"

    reference = models.CharField("referencia", max_length=60, unique=True)
    title = models.CharField("título", max_length=300)
    audited_organization = models.ForeignKey(
        "institutions.Organization",
        verbose_name="institución auditada",
        on_delete=models.PROTECT,
        related_name="audit_cases",
    )
    report_file = models.FileField(
        "informe PDF",
        upload_to=private_upload_path,
        validators=[validate_evidence_file],
        blank=True,
    )
    report_date = models.DateField("fecha del informe", null=True, blank=True)
    period_start = models.DateField("inicio del período", null=True, blank=True)
    period_end = models.DateField("fin del período", null=True, blank=True)
    response_deadline = models.DateField("fecha límite general", null=True, blank=True)
    status = models.CharField("estado", max_length=30, choices=Status.choices, default=Status.DRAFT)
    assigned_auditor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="auditor responsable",
        on_delete=models.PROTECT,
        related_name="assigned_cases",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="creado por",
        on_delete=models.PROTECT,
        related_name="created_cases",
    )
    created_at = models.DateTimeField("creado", auto_now_add=True)
    updated_at = models.DateTimeField("actualizado", auto_now=True)

    class Meta:
        verbose_name = "expediente de auditoría"
        verbose_name_plural = "expedientes de auditoría"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.reference} - {self.audited_organization.name}"


class Finding(models.Model):
    class RiskLevel(models.TextChoices):
        LOW = "low", "Bajo"
        MEDIUM = "medium", "Medio"
        HIGH = "high", "Alto"
        CRITICAL = "critical", "Crítico"

    case = models.ForeignKey(AuditCase, verbose_name="expediente", on_delete=models.CASCADE, related_name="findings")
    number = models.PositiveIntegerField("número", validators=[MinValueValidator(1)])
    title = models.CharField("título", max_length=350)
    risk_level = models.CharField("riesgo", max_length=10, choices=RiskLevel.choices)
    condition = models.TextField("condición", blank=True)
    criteria = models.TextField("criterio", blank=True)
    cause = models.TextField("causa", blank=True)
    effect = models.TextField("efecto", blank=True)

    class Meta:
        verbose_name = "hallazgo"
        verbose_name_plural = "hallazgos"
        ordering = ("number",)
        constraints = [
            models.UniqueConstraint(fields=("case", "number"), name="unique_finding_number_per_case")
        ]

    def __str__(self):
        return f"Hallazgo {self.number}: {self.title}"


class Recommendation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        SUBMITTED = "submitted", "Respuesta enviada"
        UNDER_REVIEW = "under_review", "En revisión"
        CORRECTION_REQUIRED = "correction_required", "Requiere corrección"
        COMPLIED = "complied", "Cumplida"
        PARTIAL = "partial", "Parcialmente cumplida"
        NOT_COMPLIED = "not_complied", "No cumplida"

    finding = models.ForeignKey(Finding, verbose_name="hallazgo", on_delete=models.CASCADE, related_name="recommendations")
    number = models.PositiveIntegerField("número", validators=[MinValueValidator(1)])
    text = models.TextField("recomendación")
    responsible_organization = models.ForeignKey(
        "institutions.Organization",
        verbose_name="institución responsable",
        on_delete=models.PROTECT,
        related_name="recommendations",
    )
    deadline = models.DateField("fecha límite", null=True, blank=True)
    evidence_requirements = models.TextField("evidencias requeridas", blank=True)
    status = models.CharField("estado", max_length=30, choices=Status.choices, default=Status.PENDING)

    class Meta:
        verbose_name = "recomendación"
        verbose_name_plural = "recomendaciones"
        ordering = ("finding__number", "number")
        constraints = [
            models.UniqueConstraint(
                fields=("finding", "number"), name="unique_recommendation_number_per_finding"
            )
        ]

    def __str__(self):
        return f"{self.finding.case.reference} / H{self.finding.number} / R{self.number}"


class Response(models.Model):
    class DeclaredStatus(models.TextChoices):
        NOT_STARTED = "not_started", "No iniciada"
        IN_PROGRESS = "in_progress", "En proceso"
        COMPLETED = "completed", "Completada"
        UNABLE = "unable", "No fue posible cumplir"

    recommendation = models.ForeignKey(
        Recommendation, verbose_name="recomendación", on_delete=models.PROTECT, related_name="responses"
    )
    version = models.PositiveIntegerField("versión", validators=[MinValueValidator(1)])
    declared_status = models.CharField("estado declarado", max_length=20, choices=DeclaredStatus.choices)
    action_description = models.TextField("acciones realizadas")
    action_date = models.DateField("fecha de ejecución", null=True, blank=True)
    responsible_name = models.CharField("nombre del responsable", max_length=200)
    responsible_job_title = models.CharField("cargo del responsable", max_length=150)
    non_compliance_reason = models.TextField("motivo de incumplimiento", blank=True)
    action_plan = models.TextField("plan de acción pendiente", blank=True)
    expected_completion_date = models.DateField("fecha estimada de cumplimiento", null=True, blank=True)
    accuracy_declaration = models.BooleanField("declaración de veracidad", default=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="enviada por",
        on_delete=models.PROTECT,
        related_name="submitted_responses",
    )
    submitted_at = models.DateTimeField("enviada", auto_now_add=True)

    class Meta:
        verbose_name = "respuesta"
        verbose_name_plural = "respuestas"
        ordering = ("-version",)
        constraints = [
            models.UniqueConstraint(
                fields=("recommendation", "version"), name="unique_response_version_per_recommendation"
            )
        ]

    def __str__(self):
        return f"{self.recommendation} / versión {self.version}"


class Evidence(models.Model):
    class Category(models.TextChoices):
        MINUTES = "minutes", "Acta"
        ACCOUNTING = "accounting", "Registro contable"
        BANKING = "banking", "Documento bancario"
        INVOICE = "invoice", "Factura o recibo"
        CONTRACT = "contract", "Contrato"
        IMAGE = "image", "Imagen"
        OTHER = "other", "Otra evidencia"

    class ScanStatus(models.TextChoices):
        PENDING = "pending", "Pendiente de análisis"
        CLEAN = "clean", "Aprobado"
        REJECTED = "rejected", "Rechazado"

    response = models.ForeignKey(Response, verbose_name="respuesta", on_delete=models.CASCADE, related_name="evidence")
    file = models.FileField("archivo", upload_to=private_upload_path, validators=[validate_evidence_file])
    original_filename = models.CharField("nombre original", max_length=255)
    category = models.CharField("categoría", max_length=20, choices=Category.choices, default=Category.OTHER)
    description = models.CharField("descripción", max_length=300)
    size = models.PositiveBigIntegerField("tamaño", default=0)
    sha256 = models.CharField("huella SHA-256", max_length=64)
    scan_status = models.CharField(
        "estado de análisis", max_length=10, choices=ScanStatus.choices, default=ScanStatus.PENDING
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="subida por",
        on_delete=models.PROTECT,
        related_name="uploaded_evidence",
    )
    uploaded_at = models.DateTimeField("subida", auto_now_add=True)

    class Meta:
        verbose_name = "evidencia"
        verbose_name_plural = "evidencias"
        ordering = ("uploaded_at",)

    def __str__(self):
        return self.original_filename


class Review(models.Model):
    class Outcome(models.TextChoices):
        CORRECTION_REQUIRED = "correction_required", "Requiere corrección"
        COMPLIED = "complied", "Cumplida"
        PARTIAL = "partial", "Parcialmente cumplida"
        NOT_COMPLIED = "not_complied", "No cumplida"

    response = models.OneToOneField(Response, verbose_name="respuesta", on_delete=models.PROTECT, related_name="review")
    outcome = models.CharField("resultado", max_length=30, choices=Outcome.choices)
    comments = models.TextField("comentarios de Auditoría")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="revisada por",
        on_delete=models.PROTECT,
        related_name="reviews",
    )
    reviewed_at = models.DateTimeField("revisada", auto_now_add=True)

    class Meta:
        verbose_name = "revisión"
        verbose_name_plural = "revisiones"
        ordering = ("-reviewed_at",)

    def __str__(self):
        return f"{self.response} - {self.get_outcome_display()}"


class ActivityLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="usuario",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    case = models.ForeignKey(
        AuditCase,
        verbose_name="expediente",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField("acción", max_length=80)
    target_type = models.CharField("tipo de objeto", max_length=80, blank=True)
    target_id = models.CharField("identificador", max_length=80, blank=True)
    details = models.JSONField("detalles", default=dict, blank=True)
    ip_address = models.GenericIPAddressField("dirección IP", null=True, blank=True)
    created_at = models.DateTimeField("fecha", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "evento de bitácora"
        verbose_name_plural = "bitácora"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} - {self.action}"

