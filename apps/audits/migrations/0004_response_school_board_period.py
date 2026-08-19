import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("audits", "0003_businessdayholiday_recommendation_carried_from_and_more"),
        ("institutions", "0002_schoolboardperiod_schoolboardmember"),
    ]

    operations = [
        migrations.AddField(
            model_name="response",
            name="school_board_period",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="responses",
                to="institutions.schoolboardperiod",
                verbose_name="CDE vigente al presentar la respuesta",
            ),
        ),
    ]
