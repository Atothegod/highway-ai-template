from django.urls import path
from . import views

urlpatterns = [
    path("", views.chat_page, name="chat"),
    path("monitor/", views.monitoring_page, name="monitoring"),
    path("api/monitor/cases/", views.monitoring_cases, name="monitoring_cases"),
    path("api/chat/state/", views.chat_state, name="chat_state"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/ticket/status/", views.status_events, name="status_events"),
    path("api/chat/reset/", views.reset_chat, name="reset_chat"),
]
