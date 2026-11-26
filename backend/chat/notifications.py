from .models import ChatMessage, IncidentReport, StatusEvent


STATUS_MESSAGES = {
    IncidentReport.Status.OPEN: "เปิดเคสและรอการตรวจสอบ",
    IncidentReport.Status.IN_PROGRESS: "เจ้าหน้าที่กำลังดำเนินการตรวจสอบและแก้ไข",
    IncidentReport.Status.CLOSED: "ดำเนินการเสร็จสิ้นและปิดเคสแล้ว",
}


def notify_case_status(incident):
    message = STATUS_MESSAGES[incident.status]
    StatusEvent.objects.create(incident=incident, status=incident.status, message=message)
    ChatMessage.objects.create(
        incident=incident,
        role=ChatMessage.Role.ASSISTANT,
        content=f"อัปเดต {incident.ticket_id} · {message}",
    )
