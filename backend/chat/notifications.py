from .models import ChatMessage, IncidentReport, StatusEvent


STATUS_MESSAGES = {
    IncidentReport.Status.OPEN: "เปิดเคสและรอการตรวจสอบ",
    IncidentReport.Status.IN_PROGRESS: "เจ้าหน้าที่กำลังดำเนินการตรวจสอบและแก้ไข",
    IncidentReport.Status.CLOSED: "ดำเนินการเสร็จสิ้นและปิดเคสแล้ว",
}


def status_chat_message(ticket_id, status):
    return f"อัปเดต {ticket_id} · {STATUS_MESSAGES[status]}"


def notify_case_status(incident):
    message = STATUS_MESSAGES[incident.status]
    StatusEvent.objects.create(incident=incident, status=incident.status, message=message)
    ChatMessage.objects.create(
        incident=incident,
        role=ChatMessage.Role.ASSISTANT,
        content=status_chat_message(incident.ticket_id, incident.status),
    )
