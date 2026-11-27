from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("chat/", views.chat_page, name="chat"),
    path("login/", views.chat_login, name="chat_login"),
    path("operations/login/", views.OperationsLoginView.as_view(), name="operations_login"),
    path("logout/", views.chat_logout, name="chat_logout"),
    path("monitor/", views.monitoring_page, name="monitoring"),
    path("operations/", views.operations_dashboard, name="operations_dashboard"),
    path("operations/map/", views.operations_map, name="operations_map"),
    path("operations/board/", views.operations_board, name="operations_board"),
    path("operations/conversations/", views.operations_conversations, name="operations_conversations"),
    path("api/operations/conversations/<str:ticket_id>/", views.operations_conversation, name="operations_conversation"),
    path("api/operations/cases/<str:ticket_id>/", views.operations_case_update, name="operations_case_update"),
    path("api/monitor/cases/", views.monitoring_cases, name="monitoring_cases"),
    path("api/chat/pin/", views.chat_pin, name="chat_pin"),
    path("api/chat/state/", views.chat_state, name="chat_state"),
    path("api/chat/", views.chat_api, name="chat_api"),
    path("api/ticket/status/", views.status_events, name="status_events"),
    path("api/chat/reset/", views.reset_chat, name="reset_chat"),
]
