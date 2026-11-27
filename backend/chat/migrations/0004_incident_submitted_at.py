from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("chat", "0003_incident_coordinates")]

    operations = [
        migrations.AddField(
            model_name="incidentreport",
            name="submitted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
