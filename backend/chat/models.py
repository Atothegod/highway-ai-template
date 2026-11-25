import secrets

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
    occurred_at = models.CharField(max_length=120, blank=True)
    impact = models.TextField(blank=True)
    contact = models.CharField(max_length=200, blank=True)
    urgency = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

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
