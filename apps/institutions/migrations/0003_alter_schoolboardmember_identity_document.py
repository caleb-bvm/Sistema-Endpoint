import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("institutions", "0002_schoolboardperiod_schoolboardmember"),
    ]

    operations = [
        migrations.AlterField(
            model_name="schoolboardmember",
            name="identity_document",
            field=models.CharField(
                blank=True,
                max_length=10,
                validators=[
                    django.core.validators.RegexValidator(
                        code="invalid_dui_format",
                        message="Ingrese el DUI con el formato 00000000-0.",
                        regex="^\\d{8}-\\d$",
                    )
                ],
                verbose_name="DUI (Documento Único de Identidad)",
            ),
        ),
    ]
