from django.contrib import admin
from django.db import transaction

from .models import ChatMessage, IncidentReport, StatusEvent
from .notifications import notify_case_status


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ("role", "content", "created_at")


class StatusEventInline(admin.TabularInline):
    model = StatusEvent
    extra = 0
    readonly_fields = ("status", "message", "created_at")


@admin.register(IncidentReport)
class IncidentReportAdmin(admin.ModelAdmin):
    list_display = ("ticket_id", "title", "status", "flow_state", "category_level_1", "category_level_2", "updated_at")
    list_filter = ("status", "flow_state", "category_level_1", "category_level_2")
    search_fields = ("ticket_id", "title", "description", "location", "contact")
    readonly_fields = ("ticket_id", "session_key", "created_at", "updated_at")
    inlines = (StatusEventInline, ChatMessageInline)

    @transaction.atomic
    def save_model(self, request, obj, form, change):
        previous_status = None
        if change:
            previous_status = IncidentReport.objects.select_for_update().filter(pk=obj.pk).values_list("status", flat=True).first()
        super().save_model(request, obj, form, change)
        if previous_status and previous_status != obj.status:
            notify_case_status(obj)


@admin.register(StatusEvent)
class StatusEventAdmin(admin.ModelAdmin):
    list_display = ("incident", "status", "message", "created_at")
    readonly_fields = ("incident", "status", "message", "created_at")
