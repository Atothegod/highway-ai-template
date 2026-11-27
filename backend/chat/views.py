import json
import os
import re
from decimal import Decimal, InvalidOperation
from functools import wraps
from types import SimpleNamespace
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.db import transaction
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.admin.utils import quote
from django.contrib.auth.views import LoginView
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .agent import AGENT_PROFILE, run_agent
from .forms import ChatLoginForm, OperationsCaseForm, OperationsLoginForm, OperationsMoveForm
from .models import ChatMessage, IncidentReport, StatusEvent
from .notifications import STATUS_MESSAGES, notify_case_status, status_chat_message
from .routing import CATEGORY_CHOICES, POLICY, TEAM_CHOICES, TEAMS, apply_initial_routing

MAX_HISTORY_MESSAGES = 30
STATUS_LABELS = dict(IncidentReport.Status.choices)
FLOW_LABELS = dict(IncidentReport.FlowState.choices)
CHAT_IDENTITY = "chat_identity"
CHAT_CONSENT_VERSION = 1


def _chat_identity(request):
    identity = request.session.get(CHAT_IDENTITY)
    if identity and identity["consent_version"] == CHAT_CONSENT_VERSION:
        return identity
    return None


def chat_session_required(view):
    @wraps(view)
    def gated_view(request, *args, **kwargs):
        if not _chat_identity(request):
            return JsonResponse({"error": "กรุณาเข้าสู่แชตและให้ความยินยอมก่อนใช้งาน"}, status=403)
        return view(request, *args, **kwargs)

    return never_cache(gated_view)


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
        "human_mode": case.human_mode,
        "category_level_1": case.category_level_1,
        "category_level_2": case.category_level_2,
        "title": case.title,
        "description": case.description,
        "service_area": case.service_area,
        "location": case.location,
        "pin": [float(case.latitude), float(case.longitude)] if (
            case.latitude is not None and case.longitude is not None
        ) else None,
        "pin_hint": _case_coordinates(case),
        "submitted_at": case.submitted_at.isoformat() if case.submitted_at else None,
        "occurred_at": case.occurred_at,
        "occurred_at_normalized": case.occurred_at_normalized.isoformat() if case.occurred_at_normalized else None,
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
        "chat_message": status_chat_message(event.incident_id, event.status)
        if STATUS_MESSAGES.get(event.status) == event.message else None,
        "created_at": event.created_at.isoformat(),
    }


@require_GET
def landing_page(request):
    return render(request, "chat/landing.html")


class OperationsLoginView(LoginView):
    template_name = "chat/login.html"
    authentication_form = OperationsLoginForm
    next_page = reverse_lazy("operations_dashboard")
    extra_context = {"operations_login": True}

    def get(self, request, *args, **kwargs):
        if request.user.is_active and request.user.is_staff:
            return redirect(self.get_success_url())
        return super().get(request, *args, **kwargs)


@never_cache
@require_http_methods(["GET", "POST"])
def chat_login(request):
    if _chat_identity(request):
        return redirect("chat")
    form = ChatLoginForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        request.session[CHAT_IDENTITY] = {
            "username": form.cleaned_data["username"],
            "consented_at": timezone.now().isoformat(),
            "consent_version": CHAT_CONSENT_VERSION,
        }
        return redirect("chat")
    return render(request, "chat/login.html", {"form": form})


@never_cache
@require_POST
def chat_logout(request):
    for key in (CHAT_IDENTITY, "current_ticket_id", "pre_case_history"):
        request.session.pop(key, None)
    return redirect("chat_login")


@never_cache
@require_GET
@ensure_csrf_cookie
def chat_page(request):
    identity = _chat_identity(request)
    if not identity:
        return redirect("chat_login")
    return render(request, "chat/index.html", {
        "agent": AGENT_PROFILE,
        "username": identity["username"],
        "incident_tile_url": os.getenv("INCIDENT_MAP_TILE_URL", "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
        "incident_tile_attribution": os.getenv(
            "INCIDENT_MAP_ATTRIBUTION",
            '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        ),
    })


@staff_member_required(login_url="operations_login")
def monitoring_page(request):
    return render(request, "chat/monitoring.html")


@staff_member_required(login_url="operations_login")
@require_GET
def operations_dashboard(request):
    return render(request, "chat/operations/dashboard.html", {"active_view": "dashboard"})


@staff_member_required(login_url="operations_login")
@require_GET
def operations_map(request):
    return render(request, "chat/operations/map.html", {
        "active_view": "map",
        "routing_categories": CATEGORY_CHOICES,
        "routing_teams": TEAM_CHOICES,
        "handoff_choices": IncidentReport._meta.get_field("grc_handoff_status").choices,
    })


@staff_member_required(login_url="operations_login")
@require_GET
def operations_board(request):
    return render(request, "chat/operations/board.html", {
        "active_view": "board",
        "routing_categories": CATEGORY_CHOICES,
        "routing_teams": TEAM_CHOICES,
        "handoff_choices": IncidentReport._meta.get_field("grc_handoff_status").choices,
    })


def _conversation_permission(request, *, write=False):
    if not request.user.has_perm("chat.view_chatmessage") or (
        write and not request.user.has_perm("chat.add_chatmessage")
    ):
        raise PermissionDenied


def _reporter_names(cases):
    keys = {case.session_key for case in cases if not case.reporter_name}
    sessions = Session.objects.filter(session_key__in=keys, expire_date__gt=timezone.now())
    names = {session.pk: session.get_decoded().get(CHAT_IDENTITY, {}).get("username", "")
             for session in sessions}
    return {case.pk: case.reporter_name or names.get(case.session_key, "") for case in cases}


@staff_member_required(login_url="operations_login")
@never_cache
@require_GET
def operations_conversations(request):
    _conversation_permission(request)
    search = request.GET.get("q", "").strip()[:150]
    cases = IncidentReport.objects.order_by("-updated_at", "ticket_id")
    if search:
        cases = cases.filter(
            Q(ticket_id__icontains=search) | Q(reporter_name__icontains=search) | Q(title__icontains=search)
        )
    page = Paginator(cases, 40).get_page(request.GET.get("page"))
    items = list(page.object_list)
    selected = IncidentReport.objects.filter(pk=request.GET.get("ticket")).first()
    names = _reporter_names([*items, *([selected] if selected else [])])
    return render(request, "chat/operations/conversations.html", {
        "active_view": "conversations",
        "page": page,
        "conversations": [(case, names[case.pk]) for case in items],
        "selected": selected,
        "reporter_name": names[selected.pk] if selected else "",
        "search": search,
        "can_reply": request.user.has_perm("chat.add_chatmessage"),
    })


@staff_member_required(login_url="operations_login")
@never_cache
@require_http_methods(["GET", "POST"])
def operations_conversation(request, ticket_id):
    _conversation_permission(request, write=request.method == "POST")
    if request.method == "GET":
        case = get_object_or_404(IncidentReport, pk=ticket_id)
        try:
            before = int(request.GET.get("before", 0))
            after = int(request.GET.get("after", 0))
        except ValueError:
            return JsonResponse({"error": "หมายเลขข้อความไม่ถูกต้อง"}, status=400)
        messages = case.messages.all()
        if before > 0:
            messages = messages.filter(pk__lt=before)
        fields = ("id", "role", "author_name", "content", "created_at")
        if after > 0:
            rows = list(messages.filter(pk__gt=after).order_by("pk").values(*fields)[:100])
            has_older = False
        else:
            latest = list(messages.order_by("-pk").values(*fields)[:101])
            rows = list(reversed(latest[:100]))
            has_older = len(latest) > 100
        return JsonResponse({
            "messages": rows,
            "has_older": has_older,
            "human_mode": case.human_mode,
            "closed": case.status == IncidentReport.Status.CLOSED,
        })

    action = request.POST.get("action")
    message = request.POST.get("message", "").strip()
    if action not in {"reply", "take_over", "resume"} or (action == "reply" and not 1 <= len(message) <= 4000):
        return JsonResponse({"error": "กรุณาระบุข้อความ 1–4,000 ตัวอักษร"}, status=400)
    with transaction.atomic():
        case = get_object_or_404(IncidentReport.objects.select_for_update(), pk=ticket_id)
        if case.status == IncidentReport.Status.CLOSED:
            return JsonResponse({"error": "เคสนี้ปิดแล้ว"}, status=409)
        case.human_mode = action != "resume"
        case.save(update_fields=["human_mode", "updated_at"])
        if action == "reply":
            ChatMessage.objects.create(
                incident=case, role=ChatMessage.Role.STAFF,
                author_name=request.user.get_username(), content=message,
            )
    return JsonResponse({"ok": True})


@staff_member_required(login_url="operations_login")
@require_POST
@transaction.atomic
def operations_case_update(request, ticket_id):
    if not request.user.has_perm("chat.change_incidentreport"):
        return JsonResponse({"error": "บัญชีนี้ไม่มีสิทธิ์แก้ไขเคส"}, status=403)
    case = IncidentReport.objects.select_for_update().filter(pk=ticket_id).first()
    if case is None:
        return JsonResponse({"error": "ไม่พบเคสนี้"}, status=404)
    previous_status = case.status
    previous_category = case.routing_category
    version = case.updated_at.isoformat()
    form_class = OperationsMoveForm if request.POST.get("action") == "move" else OperationsCaseForm
    data = request.POST.copy()
    for field in ("routing_category", "assigned_team", "resolution_summary", "grc_case_id", "grc_handoff_status"):
        if field not in data:
            data[field] = getattr(case, field)
    form = form_class(data, instance=case)
    if not form.is_valid():
        errors = [error for field_errors in form.errors.values() for error in field_errors]
        return JsonResponse({"error": " ".join(errors)}, status=400)
    if form.has_changed():
        if request.POST.get("version") != version:
            return JsonResponse({"error": "เคสถูกอัปเดตแล้ว กรุณาเปิดเคสใหม่ก่อนบันทึก"}, status=409)
        now = timezone.now()
        changed = set(form.changed_data)
        if "assigned_team" in changed:
            case.assigned_at = now if case.assigned_team else None
            changed.add("assigned_at")
        if "resolution_summary" in changed:
            case.resolved_at = (case.resolved_at or now) if case.resolution_summary else None
            changed.add("resolved_at")
        rematch = case.routing_category != previous_category
        prior_policy = POLICY.get(previous_category)
        if rematch and prior_policy and "assigned_team" not in changed and case.assigned_team == prior_policy[1]:
            case.assigned_team, case.assigned_at = "", None
            changed.update(("assigned_team", "assigned_at"))
        if rematch and not case.routing_category:
            case.sla_due_at = None
            changed.add("sla_due_at")
        changed.update(apply_initial_routing(case, now, rematch=rematch))
        case.save(update_fields=[*changed, "updated_at"])
        if case.status != previous_status:
            notify_case_status(case)
    return JsonResponse({"ok": True})


def _case_coordinates(case):
    if case.latitude is not None and case.longitude is not None:
        latitude, longitude = float(case.latitude), float(case.longitude)
    else:
        # Accept a complete coordinate pair supplied in the existing location field.
        pair = re.fullmatch(r"\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*", case.location)
        if not pair:
            return None
        latitude, longitude = map(float, pair.groups())
    if -90 <= latitude <= 90 and -180 <= longitude <= 180:
        return [latitude, longitude]
    return None


@staff_member_required(login_url="operations_login")
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
    can_edit = request.user.has_perm("chat.change_incidentreport")
    for case in cases.prefetch_related("status_events")[:200]:
        item = _case_data(case)
        policy = POLICY.get(case.routing_category)
        item.update({
            "received_at": (case.received_at or case.created_at).isoformat(),
            "routing_category": case.routing_category,
            "routing_level": policy[2] if policy else "",
            "assigned_team": case.assigned_team,
            "assigned_team_label": TEAMS.get(case.assigned_team, case.assigned_team),
            "assigned_at": case.assigned_at.isoformat() if case.assigned_at else None,
            "sla_due_at": case.sla_due_at.isoformat() if case.sla_due_at else None,
            "resolved_at": case.resolved_at.isoformat() if case.resolved_at else None,
            "resolution_summary": case.resolution_summary,
            "grc_case_id": case.grc_case_id,
            "grc_handoff_status": case.grc_handoff_status,
            "grc_handoff_label": case.get_grc_handoff_status_display(),
            "created_at": case.created_at.isoformat(),
            "coordinates": _case_coordinates(case),
            "saved_coordinates": [float(case.latitude), float(case.longitude)]
            if case.latitude is not None and case.longitude is not None else None,
            "update_url": reverse("operations_case_update", args=[case.pk]) if can_edit else "",
            "edit_url": reverse("admin:chat_incidentreport_change", args=[quote(case.pk)]) if can_edit else "",
            "events": [_event_data(event) for event in case.status_events.all()],
        })
        items.append(item)
    return JsonResponse({"stats": stats, "cases": items, "result_count": len(items)})


@require_GET
@chat_session_required
@transaction.atomic
def chat_state(request):
    session_key = _ensure_session(request)
    case = IncidentReport.objects.select_for_update().filter(
        ticket_id=request.session.get("current_ticket_id"), session_key=session_key,
    ).first()
    cursor = StatusEvent.objects.filter(incident__session_key=session_key).order_by("-id").values_list("id", flat=True).first() or 0
    if not case:
        return JsonResponse({
            "case": None,
            "messages": request.session.get("pre_case_history", []),
            "events": [],
            "cursor": cursor,
        })
    status_messages = {status_chat_message(case.pk, status) for status in STATUS_MESSAGES}
    messages = list(case.messages.values("id", "role", "content", "created_at"))
    for message in messages:
        message["is_status_update"] = (
            message["role"] == ChatMessage.Role.ASSISTANT and message["content"] in status_messages
        )
    return JsonResponse({
        "case": _case_data(case),
        "messages": messages,
        "events": [_event_data(event) for event in case.status_events.all()],
        "cursor": cursor,
        "staff_cursor": max((message["id"] for message in messages if message["role"] == ChatMessage.Role.STAFF), default=0),
    })


@require_http_methods(["GET", "POST"])
@chat_session_required
def chat_pin(request):
    case = _current_case(request)
    if not case or request.GET.get("ticket_id") != case.pk:
        return JsonResponse({"error": "ไม่พบเคสปัจจุบัน"}, status=404)

    if request.method == "GET":
        hint = _case_coordinates(case)
        endpoint = os.getenv("INCIDENT_GEOCODER_URL")
        if hint is None and endpoint and case.location:
            query = urlencode({"q": case.location, "format": "jsonv2", "limit": 1, "countrycodes": "th"})
            try:
                req = Request(f"{endpoint}?{query}", headers={"User-Agent": "BEM-Incident-Reporting"})
                with urlopen(req, timeout=3) as response:
                    results = json.load(response)
                if results:
                    lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        hint = [lat, lon]
            except (URLError, OSError, ValueError, TypeError, KeyError, IndexError):
                pass
        return JsonResponse({"hint": hint})

    try:
        data = json.loads(request.body)
        lat, lon = Decimal(str(data["latitude"])), Decimal(str(data["longitude"]))
        if not (lat.is_finite() and lon.is_finite() and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError
        case.latitude = lat.quantize(Decimal("0.000001"))
        case.longitude = lon.quantize(Decimal("0.000001"))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return JsonResponse({"error": "กรุณาระบุพิกัดที่ถูกต้องทั้งสองค่า"}, status=400)

    changed = IncidentReport.objects.filter(pk=case.pk).exclude(status=IncidentReport.Status.CLOSED).update(
        latitude=case.latitude, longitude=case.longitude, updated_at=timezone.now(),
    )
    if not changed:
        return JsonResponse({"error": "เคสนี้ปิดแล้ว"}, status=409)
    case.refresh_from_db()
    return JsonResponse({"case": _case_data(case)})


def _closed_chat_reply(case, message):
    reply = f"เคส {case.pk} ปิดแล้วครับ"
    ChatMessage.objects.bulk_create([
        ChatMessage(incident=case, role=ChatMessage.Role.USER, content=message),
        ChatMessage(incident=case, role=ChatMessage.Role.ASSISTANT, content=reply),
    ])
    return JsonResponse({"reply": reply, "case": _case_data(case)})


def _receive_human_message(case, message):
    ChatMessage.objects.create(incident=case, role=ChatMessage.Role.USER, content=message)
    case.save(update_fields=["updated_at"])
    return JsonResponse({"reply": None, "case": _case_data(case)})


@require_POST
@chat_session_required
def chat_api(request):
    received_at = timezone.now()
    try:
        data = json.loads(request.body)
        message = str(data["message"]).strip()
        if not message or len(message) > 4000:
            raise ValueError
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "กรุณาระบุข้อความไม่เกิน 4,000 ตัวอักษร"}, status=400)

    case = _current_case(request)
    if case and (case.status == IncidentReport.Status.CLOSED or case.human_mode):
        with transaction.atomic():
            case = IncidentReport.objects.select_for_update().get(pk=case.pk)
            if case.status == IncidentReport.Status.CLOSED:
                return _closed_chat_reply(case, message)
            if case.human_mode:
                return _receive_human_message(case, message)
    if case:
        previous = list(case.messages.order_by("-created_at")[:MAX_HISTORY_MESSAGES])
        previous.reverse()
        history_items = [{"role": item.role, "content": item.content} for item in previous]
    else:
        history_items = request.session.get("pre_case_history", [])[-MAX_HISTORY_MESSAGES:]
    is_first_message = case is None
    history = "\n".join(
        f"{dict(ChatMessage.Role.choices).get(item['role'], 'BEM Care')}: {item['content']}"
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
        case = IncidentReport.objects.create(
            session_key=_ensure_session(request), received_at=received_at,
            reporter_name=_chat_identity(request)["username"],
        )
        ChatMessage.objects.bulk_create([
            ChatMessage(incident=case, role=item["role"], content=item["content"])
            for item in history_items
        ])
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
        case = IncidentReport.objects.select_for_update().get(pk=case.pk)
        if case.status == IncidentReport.Status.CLOSED:
            return _closed_chat_reply(case, message)
        if case.human_mode:
            return _receive_human_message(case, message)
        changed_fields = ["updated_at"]
        was_submitted = case.flow_state == IncidentReport.FlowState.SUBMITTED
        if not was_submitted and result.routing_category in POLICY:
            case.routing_category = result.routing_category
            changed_fields.append("routing_category")
        if case.flow_state != IncidentReport.FlowState.SUBMITTED:
            if result.flow_state == IncidentReport.FlowState.SUBMITTED:
                if case.latitude is None or case.longitude is None:
                    result.flow_state = IncidentReport.FlowState.CONFIRMING
                    result.reply = "กรุณาเลือกจุดเกิดเหตุจากการ์ดนี้ แล้วส่งข้อความยืนยันอีกครั้งครับ"
                else:
                    case.submitted_at = timezone.now()
                    changed_fields.append("submitted_at")
            case.flow_state = result.flow_state
            changed_fields.append("flow_state")
        ChatMessage.objects.create(incident=case, role=ChatMessage.Role.USER, content=message)
        ChatMessage.objects.create(incident=case, role=ChatMessage.Role.ASSISTANT, content=result.reply)
        previous_occurrence = case.occurred_at
        for field in update_fields:
            value = getattr(result, field)
            if value:
                setattr(case, field, value)
                changed_fields.append(field)
        if result.occurred_at:
            try:
                normalized = parse_datetime(result.occurred_at_normalized)
            except ValueError:
                normalized = None
            if normalized is not None and timezone.is_aware(normalized):
                case.occurred_at_normalized = normalized
                changed_fields.append("occurred_at_normalized")
            elif case.occurred_at != previous_occurrence:
                case.occurred_at_normalized = None
                changed_fields.append("occurred_at_normalized")
        if not was_submitted:
            changed_fields.extend(apply_initial_routing(case, timezone.now()))
        case.save(update_fields=changed_fields)

    return JsonResponse({"reply": result.reply, "case": _case_data(case)})


@require_GET
@chat_session_required
def status_events(request):
    try:
        after = max(0, int(request.GET.get("after", 0)))
        staff_after = max(0, int(request.GET.get("staff_after", 0)))
    except ValueError:
        after = staff_after = 0
    events = [
        _event_data(event) for event in StatusEvent.objects.filter(
            incident__session_key=_ensure_session(request), id__gt=after,
        ).order_by("id")
    ]
    case = _current_case(request)
    staff_messages = list(case.messages.filter(
        role=ChatMessage.Role.STAFF, pk__gt=staff_after,
    ).order_by("pk").values("id", "role", "content")) if case else []
    return JsonResponse({"case": _case_data(case), "events": events, "staff_messages": staff_messages})


@require_POST
@chat_session_required
def reset_chat(request):
    request.session.pop("current_ticket_id", None)
    request.session.pop("pre_case_history", None)
    cursor = StatusEvent.objects.filter(
        incident__session_key=_ensure_session(request)
    ).order_by("-id").values_list("id", flat=True).first() or 0
    return JsonResponse({"ok": True, "cursor": cursor})
