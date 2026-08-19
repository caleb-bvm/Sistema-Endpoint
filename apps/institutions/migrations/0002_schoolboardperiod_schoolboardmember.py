import apps.core.validators
import apps.institutions.models
import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("institutions", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SchoolBoardPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(verbose_name="fecha de inicio")),
                ("end_date", models.DateField(verbose_name="fecha de finalización")),
                ("school_year_start", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1900)], verbose_name="año escolar inicial")),
                ("school_year_end", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1900)], verbose_name="año escolar final")),
                ("supporting_document", models.FileField(upload_to=apps.institutions.models.cde_document_upload_path, validators=[apps.core.validators.validate_evidence_file], verbose_name="acta o documento de conformación")),
                ("supporting_document_name", models.CharField(blank=True, max_length=255, verbose_name="nombre original del documento")),
                ("notes", models.TextField(blank=True, verbose_name="observaciones")),
                ("is_current", models.BooleanField(default=True, verbose_name="vigente")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="registrado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="actualizado")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_school_board_periods", to=settings.AUTH_USER_MODEL, verbose_name="registrado por")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="school_board_periods", to="institutions.organization", verbose_name="centro educativo")),
                ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="updated_school_board_periods", to=settings.AUTH_USER_MODEL, verbose_name="actualizado por")),
            ],
            options={
                "verbose_name": "período del Consejo Directivo Escolar",
                "verbose_name_plural": "períodos del Consejo Directivo Escolar",
                "ordering": ("-start_date", "-created_at"),
            },
        ),
        migrations.CreateModel(
            name="SchoolBoardMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=255, verbose_name="nombre completo")),
                ("identity_document", models.CharField(blank=True, max_length=80, verbose_name="documento de identificación")),
                ("position", models.CharField(max_length=150, verbose_name="cargo dentro del CDE")),
                ("sector", models.CharField(choices=[("parents", "Padres de familia"), ("teachers", "Docentes"), ("students", "Estudiantes"), ("directorate", "Dirección del centro"), ("other", "Otro sector")], max_length=20, verbose_name="sector que representa")),
                ("is_legal_representative", models.BooleanField(default=False, verbose_name="ejerce representación legal")),
                ("joined_on", models.DateField(verbose_name="fecha de incorporación")),
                ("left_on", models.DateField(blank=True, null=True, verbose_name="fecha de salida")),
                ("exit_reason", models.TextField(blank=True, verbose_name="motivo de salida o sustitución")),
                ("change_document", models.FileField(blank=True, upload_to=apps.institutions.models.cde_document_upload_path, validators=[apps.core.validators.validate_evidence_file], verbose_name="documento de respaldo de la salida o sustitución")),
                ("change_document_name", models.CharField(blank=True, max_length=255, verbose_name="nombre original del documento de cambio")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="registrado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="actualizado")),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_school_board_members", to=settings.AUTH_USER_MODEL, verbose_name="registrado por")),
                ("period", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="members", to="institutions.schoolboardperiod", verbose_name="período del CDE")),
                ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="updated_school_board_members", to=settings.AUTH_USER_MODEL, verbose_name="actualizado por")),
            ],
            options={
                "verbose_name": "integrante del Consejo Directivo Escolar",
                "verbose_name_plural": "integrantes del Consejo Directivo Escolar",
                "ordering": ("left_on", "position", "full_name"),
            },
        ),
        migrations.AddConstraint(
            model_name="schoolboardperiod",
            constraint=models.UniqueConstraint(condition=models.Q(("is_current", True)), fields=("organization",), name="one_current_school_board_per_organization"),
        ),
        migrations.AddConstraint(
            model_name="schoolboardperiod",
            constraint=models.CheckConstraint(condition=models.Q(("end_date__gte", models.F("start_date"))), name="school_board_period_valid_dates"),
        ),
        migrations.AddConstraint(
            model_name="schoolboardperiod",
            constraint=models.CheckConstraint(condition=models.Q(("school_year_end__gte", models.F("school_year_start"))), name="school_board_period_valid_years"),
        ),
        migrations.AddConstraint(
            model_name="schoolboardmember",
            constraint=models.CheckConstraint(condition=models.Q(("left_on__isnull", True), ("left_on__gte", models.F("joined_on")), _connector="OR"), name="school_board_member_valid_dates"),
        ),
    ]
