from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0002_translate_taxonomy")]

    operations = [
        migrations.AddField(
            model_name="incidentreport",
            name="latitude",
            field=models.DecimalField(
                "ละติจูด", max_digits=9, decimal_places=6, blank=True, null=True,
                validators=[MinValueValidator(-90), MaxValueValidator(90)],
            ),
        ),
        migrations.AddField(
            model_name="incidentreport",
            name="longitude",
            field=models.DecimalField(
                "ลองจิจูด", max_digits=9, decimal_places=6, blank=True, null=True,
                validators=[MinValueValidator(-180), MaxValueValidator(180)],
            ),
        ),
    ]
