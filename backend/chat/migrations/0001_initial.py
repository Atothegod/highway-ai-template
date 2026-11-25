from django.db import migrations, models
import django.db.models.deletion
import chat.models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            name="IncidentReport",
            fields=[
                ("ticket_id", models.CharField(default=chat.models.make_ticket_id, editable=False, max_length=32, primary_key=True, serialize=False)),
                ("session_key", models.CharField(db_index=True, max_length=40)),
                ("status", models.CharField(choices=[("OPEN", "เปิดเคส"), ("IN_PROGRESS", "กำลังดำเนินการ"), ("CLOSED", "ปิดเคส")], default="OPEN", max_length=20)),
                ("flow_state", models.CharField(choices=[("COLLECTING", "กำลังเก็บข้อมูล"), ("CONFIRMING", "รอยืนยันข้อมูล"), ("SUBMITTED", "รับเรื่องแล้ว")], default="COLLECTING", max_length=20)),
                ("category_level_1", models.CharField(blank=True, max_length=100)),
                ("category_level_2", models.CharField(blank=True, max_length=120)),
                ("title", models.CharField(blank=True, max_length=240)),
                ("description", models.TextField(blank=True)),
                ("service_area", models.CharField(blank=True, max_length=120)),
                ("location", models.CharField(blank=True, max_length=300)),
                ("occurred_at", models.CharField(blank=True, max_length=120)),
                ("impact", models.TextField(blank=True)),
                ("contact", models.CharField(blank=True, max_length=200)),
                ("urgency", models.CharField(blank=True, max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ChatMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("user", "ผู้ใช้"), ("assistant", "BEM Care")], max_length=12)),
                ("content", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="chat.incidentreport")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
        migrations.CreateModel(
            name="StatusEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("OPEN", "เปิดเคส"), ("IN_PROGRESS", "กำลังดำเนินการ"), ("CLOSED", "ปิดเคส")], max_length=20)),
                ("message", models.CharField(max_length=300)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("incident", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="status_events", to="chat.incidentreport")),
            ],
            options={"ordering": ["created_at", "id"]},
        ),
    ]
