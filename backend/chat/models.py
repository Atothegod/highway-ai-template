import secrets

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def make_ticket_id():
    date = timezone.localdate().strftime("%Y%m%d")
    return f"BEM-{date}-{secrets.token_hex(3).upper()}"


class IncidentReport(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "เปิดเคส"
        IN_PROGRESS = "IN_PROGRESS", "กำลังดำเนินการ"
        CLOSED = "CLOSED", "ปิดเคส"

    class FlowState(models.TextChoices):
        COLLECTING = "COLLECTING", "กำลังเก็บข้อมูล"
        CONFIRMING = "CONFIRMING", "รอยืนยันข้อมูล"
        SUBMITTED = "SUBMITTED", "รับเรื่องแล้ว"

    ticket_id = models.CharField(max_length=32, primary_key=True, default=make_ticket_id, editable=False)
    session_key = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    flow_state = models.CharField(max_length=20, choices=FlowState.choices, default=FlowState.COLLECTING)
    category_level_1 = models.CharField(max_length=100, blank=True)
    category_level_2 = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=240, blank=True)
    description = models.TextField(blank=True)
    service_area = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=300, blank=True)
    latitude = models.DecimalField(
        "ละติจูด", max_digits=9, decimal_places=6, blank=True, null=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        "ลองจิจูด", max_digits=9, decimal_places=6, blank=True, null=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    occurred_at = models.CharField(max_length=120, blank=True)
    occurred_at_normalized = models.DateTimeField("วันเวลาเกิดเหตุที่ระบุได้", null=True, blank=True)
    routing_category = models.CharField("รหัสหมวดสำหรับ matching", max_length=6, blank=True)
    received_at = models.DateTimeField("เวลารับแจ้งครั้งแรก", null=True, blank=True)
    resolved_at = models.DateTimeField("เวลาแก้ไขเสร็จ", null=True, blank=True)
    assigned_team = models.CharField("ทีมรับผิดชอบ", max_length=120, blank=True)
    assigned_at = models.DateTimeField("เวลามอบหมาย", null=True, blank=True)
    sla_due_at = models.DateTimeField("กำหนด SLA", null=True, blank=True)
    resolution_summary = models.TextField("ผลการแก้ไข", blank=True)
    grc_case_id = models.CharField("เลขเคส GRC", max_length=120, blank=True)
    grc_handoff_status = models.CharField("สถานะส่งต่อ GRC", max_length=20, blank=True, choices=[
        ("PENDING", "รอส่งต่อ"), ("SENT", "ส่งแล้ว"), ("ACCEPTED", "GRC รับเรื่อง"), ("FAILED", "ส่งไม่สำเร็จ"),
    ])
    impact = models.TextField(blank=True)
    contact = models.CharField(max_length=200, blank=True)
    urgency = models.CharField(max_length=20, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.latitude is None and self.longitude is not None:
            raise ValidationError({"latitude": "กรุณาระบุละติจูดคู่กับลองจิจูด"})
        if self.longitude is None and self.latitude is not None:
            raise ValidationError({"longitude": "กรุณาระบุลองจิจูดคู่กับละติจูด"})

    def __str__(self):
        return f"{self.ticket_id} — {self.title or 'กำลังรับข้อมูล'}"


class ChatMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "ผู้ใช้"
        ASSISTANT = "assistant", "BEM Care"

    incident = models.ForeignKey(IncidentReport, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=12, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class StatusEvent(models.Model):
    incident = models.ForeignKey(IncidentReport, on_delete=models.CASCADE, related_name="status_events")
    status = models.CharField(max_length=20, choices=IncidentReport.Status.choices)
    message = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
