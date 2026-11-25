import json
from types import SimpleNamespace

from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .agent import AGENT_PROFILE, run_agent
from .models import ChatMessage, IncidentReport, StatusEvent

MAX_HISTORY_MESSAGES = 30
STATUS_LABELS = dict(IncidentReport.Status.choices)
FLOW_LABELS = dict(IncidentReport.FlowState.choices)


def _blank_case():
    fields = (
        "category_level_1", "category_level_2", "title", "description", "service_area",
        "location", "occurred_at", "impact", "contact", "urgency",
    )
    return SimpleNamespace(
        ticket_id="ยังไม่เปิดเคส", status="NOT_OPENED",
        flow_state=IncidentReport.FlowState.COLLECTING,
        **{field: "" for field in fields},
    )


def _ensure_session(request):
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def _current_case(request):
    ticket_id = request.session.get("current_ticket_id")
    if not ticket_id:
        return None
    return IncidentReport.objects.filter(ticket_id=ticket_id, session_key=_ensure_session(request)).first()


def _case_data(case):
    if not case:
        return None
    return {
        "ticket_id": case.ticket_id,
        "status": case.status,
        "status_label": STATUS_LABELS[case.status],
        "flow_state": case.flow_state,
        "flow_label": FLOW_LABELS[case.flow_state],
        "category_level_1": case.category_level_1,
        "category_level_2": case.category_level_2,
        "title": case.title,
        "description": case.description,
        "service_area": case.service_area,
        "location": case.location,
        "occurred_at": case.occurred_at,
        "impact": case.impact,
        "contact": case.contact,
        "urgency": case.urgency,
        "updated_at": case.updated_at.isoformat(),
    }


def _event_data(event):
    return {
        "id": event.id,
        "ticket_id": event.incident_id,
        "status": event.status,
        "status_label": STATUS_LABELS[event.status],
        "message": event.message,
        "created_at": event.created_at.isoformat(),
    }


@ensure_csrf_cookie
def chat_page(request):
    _ensure_session(request)
    return render(request, "chat/index.html", {"agent": AGENT_PROFILE})


@staff_member_required
def monitoring_page(request):
    return render(request, "chat/monitoring.html")


@staff_member_required
@require_GET
def monitoring_cases(request):
    cases = IncidentReport.objects.all()
    search = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    urgency = request.GET.get("urgency", "").strip()

    if search:
        cases = cases.filter(
            Q(ticket_id__icontains=search) | Q(title__icontains=search)
            | Q(description__icontains=search) | Q(location__icontains=search)
            | Q(category_level_1__icontains=search) | Q(category_level_2__icontains=search)
        )
    if status in STATUS_LABELS:
        cases = cases.filter(status=status)
    if urgency in {"HIGH", "MEDIUM", "LOW"}:
        cases = cases.filter(urgency=urgency)

    all_cases = IncidentReport.objects.all()
    counts = {row["status"]: row["total"] for row in all_cases.values("status").annotate(total=Count("ticket_id"))}
    stats = {
        "total": all_cases.count(),
        "open": counts.get(IncidentReport.Status.OPEN, 0),
        "in_progress": counts.get(IncidentReport.Status.IN_PROGRESS, 0),
        "closed": counts.get(IncidentReport.Status.CLOSED, 0),
        "urgent": all_cases.filter(urgency="HIGH").exclude(status=IncidentReport.Status.CLOSED).count(),
    }
    items = []
    for case in cases.prefetch_related("status_events")[:200]:
        item = _case_data(case)
        item.update({
            "created_at": case.created_at.isoformat(),
            "events": [_event_data(event) for event in case.status_events.all()],
        })
        items.append(item)
    return JsonResponse({"stats": stats, "cases": items, "result_count": len(items)})


@require_GET
def chat_state(request):
    session_key = _ensure_session(request)
    cursor = StatusEvent.objects.filter(incident__session_key=session_key).order_by("-id").values_list("id", flat=True).first() or 0
    case = _current_case(request)
    if not case:
        return JsonResponse({
            "case": None,
            "messages": request.session.get("pre_case_history", []),
            "events": [],
            "cursor": cursor,
        })
    return JsonResponse({
        "case": _case_data(case),
        "messages": list(case.messages.values("role", "content", "created_at")),
        "events": [_event_data(event) for event in case.status_events.all()],
        "cursor": cursor,
    })


@require_POST
def chat_api(request):
    try:
        data = json.loads(request.body)
        message = str(data["message"]).strip()
        if not message or len(message) > 4000:
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "กรุณาระบุข้อความไม่เกิน 4,000 ตัวอักษร"}, status=400)

    case = _current_case(request)
    if case:
        previous = list(case.messages.order_by("-created_at")[:MAX_HISTORY_MESSAGES])
        previous.reverse()
        history_items = [{"role": item.role, "content": item.content} for item in previous]
    else:
        history_items = request.session.get("pre_case_history", [])[-MAX_HISTORY_MESSAGES:]
    is_first_message = case is None
    history = "\n".join(
        f"{'ผู้ใช้' if item['role'] == ChatMessage.Role.USER else 'BEM Care'}: {item['content']}"
        for item in history_items
    )
    try:
        result = run_agent(case=case or _blank_case(), history=history, message=message)
    except Exception:
        return JsonResponse({"error": "ระบบผู้ช่วยขัดข้องชั่วคราว กรุณาลองใหม่อีกครั้ง"}, status=502)

    if case is None and not result.should_open_case:
        history_items.extend([
            {"role": ChatMessage.Role.USER, "content": message},
            {"role": ChatMessage.Role.ASSISTANT, "content": result.reply},
        ])
        request.session["pre_case_history"] = history_items[-MAX_HISTORY_MESSAGES:]
        return JsonResponse({"reply": result.reply, "case": None})

    if case is None:
        case = IncidentReport.objects.create(session_key=_ensure_session(request))
        request.session["current_ticket_id"] = case.ticket_id
        request.session.pop("pre_case_history", None)
        StatusEvent.objects.create(
            incident=case, status=IncidentReport.Status.OPEN,
            message="เปิดเคสและเริ่มรับรายละเอียดเหตุแล้ว",
        )

    if is_first_message:
        result.reply = (
            f"รับทราบครับ ผมเปิดเคสให้แล้ว\n"
            f"หมายเลขติดตามเรื่อง: {case.ticket_id}\n\n{result.reply}"
        )
    elif result.flow_state == IncidentReport.FlowState.SUBMITTED and case.ticket_id not in result.reply:
        result.reply = f"{result.reply}\n\nหมายเลขติดตามเรื่อง: {case.ticket_id}"

    update_fields = ("category_level_1", "category_level_2", "title", "description", "service_area",
                     "location", "occurred_at", "impact", "contact", "urgency")
    with transaction.atomic():
        ChatMessage.objects.create(incident=case, role=ChatMessage.Role.USER, content=message)
        ChatMessage.objects.create(incident=case, role=ChatMessage.Role.ASSISTANT, content=result.reply)
        case.flow_state = result.flow_state
        for field in update_fields:
            value = getattr(result, field)
            if value:
                setattr(case, field, value)
        case.save()

    return JsonResponse({"reply": result.reply, "case": _case_data(case)})


@require_GET
def status_events(request):
    case = _current_case(request)
    try:
        after = max(0, int(request.GET.get("after", 0)))
    except ValueError:
        after = 0
    events = StatusEvent.objects.filter(
        incident__session_key=_ensure_session(request), id__gt=after
    ).select_related("incident")
    return JsonResponse({"case": _case_data(case), "events": [_event_data(event) for event in events]})


@require_POST
def reset_chat(request):
    request.session.pop("current_ticket_id", None)
    request.session.pop("pre_case_history", None)
    cursor = StatusEvent.objects.filter(
        incident__session_key=_ensure_session(request)
    ).order_by("-id").values_list("id", flat=True).first() or 0
    return JsonResponse({"ok": True, "cursor": cursor})
