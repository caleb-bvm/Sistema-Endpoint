from django.db import models


class Organization(models.Model):
    class Kind(models.TextChoices):
        EDUCATIONAL_CENTER = "educational_center", "Centro educativo"
        DEPARTMENTAL_OFFICE = "departmental_office", "Dirección Departamental"
        MINISTRY_UNIT = "ministry_unit", "Unidad del Ministerio"
        OTHER = "other", "Otra institución"

    code = models.CharField("código institucional", max_length=30, unique=True)
    name = models.CharField("nombre", max_length=255)
    kind = models.CharField("tipo", max_length=30, choices=Kind.choices)
    department = models.CharField("departamento", max_length=100, blank=True)
    municipality = models.CharField("municipio", max_length=100, blank=True)
    address = models.TextField("dirección", blank=True)
    is_active = models.BooleanField("activa", default=True)
    created_at = models.DateTimeField("creada", auto_now_add=True)
    updated_at = models.DateTimeField("actualizada", auto_now=True)

    class Meta:
        verbose_name = "institución"
        verbose_name_plural = "instituciones"
        ordering = ("name",)

    def __str__(self):
        return f"{self.code} - {self.name}"

