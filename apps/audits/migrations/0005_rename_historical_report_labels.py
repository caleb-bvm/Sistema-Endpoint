from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audits", "0004_response_school_board_period"),
    ]

    operations = [
        migrations.AlterField(
            model_name="auditdocument",
            name="document_type",
            field=models.CharField(
                choices=[
                    ("historical_report", "Informe anterior"),
                    ("report", "Informe del expediente"),
                    ("notification", "Notificación"),
                    ("other", "Otro documento"),
                ],
                max_length=30,
                verbose_name="tipo de documento",
            ),
        ),
        migrations.AlterField(
            model_name="auditdocument",
            name="status",
            field=models.CharField(
                choices=[
                    ("historical", "Anterior"),
                    ("draft", "Borrador"),
                    ("pending_approval", "Pendiente de aprobación"),
                    ("approved", "Aprobado"),
                    ("returned", "Devuelto"),
                ],
                max_length=24,
                verbose_name="estado",
            ),
        ),
    ]
