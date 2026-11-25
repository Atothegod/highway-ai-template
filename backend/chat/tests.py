from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from .agent import AgentResult
from .models import IncidentReport, StatusEvent


class IncidentFlowTests(TestCase):
    @patch("chat.views.run_agent")
    def test_chat_creates_ticket_and_structured_incident(self, mocked_agent):
        mocked_agent.return_value = AgentResult(
            reply="ขอสรุปเหตุ กรุณายืนยันความถูกต้องครับ",
            flow_state="CONFIRMING",
            should_open_case=True,
            category_level_1="ปฏิบัติการและการจัดการ",
            category_level_2="ความพร้อมให้บริการรถไฟฟ้า",
            title="ประตูกั้นชานชาลาขัดข้อง",
            description="ประตูกั้นชานชาลาไม่เปิด",
            service_area="Rail",
            location="สถานีตัวอย่าง ชานชาลา 1",
            occurred_at="08:30",
            impact="ผู้โดยสารขึ้นรถไม่ได้",
            urgency="HIGH",
        )

        response = self.client.post(
            "/api/chat/", {"message": "ประตูกั้นชานชาลาไม่เปิด"}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        case = IncidentReport.objects.get()
        self.assertTrue(case.ticket_id.startswith("BEM-"))
        self.assertEqual(case.flow_state, IncidentReport.FlowState.CONFIRMING)
        self.assertEqual(case.category_level_2, "ความพร้อมให้บริการรถไฟฟ้า")
        self.assertIn("ผมเปิดเคสให้แล้ว", response.json()["reply"])
        self.assertIn(case.ticket_id, response.json()["reply"])
        self.assertEqual(case.messages.count(), 2)
        self.assertEqual(case.status_events.get().status, IncidentReport.Status.OPEN)

    @patch("chat.views.run_agent")
    def test_session_cannot_read_another_sessions_ticket(self, mocked_agent):
        mocked_agent.return_value = AgentResult(
            reply="ขอข้อมูลเพิ่มครับ", flow_state="COLLECTING", should_open_case=True
        )
        self.client.post("/api/chat/", {"message": "พบปัญหา"}, content_type="application/json")

        other_client = self.client_class()
        response = other_client.get("/api/chat/state/")

        self.assertEqual(response.json()["case"], None)

    @patch("chat.views.run_agent")
    def test_greeting_does_not_create_ticket(self, mocked_agent):
        mocked_agent.return_value = AgentResult(
            reply="สวัสดีครับ บอกผมได้เลยว่าพบปัญหาอะไร",
            flow_state="COLLECTING",
            should_open_case=False,
        )

        response = self.client.post(
            "/api/chat/", {"message": "สวัสดีครับ"}, content_type="application/json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["case"])
        self.assertFalse(IncidentReport.objects.exists())
        self.assertEqual(len(self.client.get("/api/chat/state/").json()["messages"]), 2)

    def test_status_endpoint_returns_new_events(self):
        session = self.client.session
        session.save()
        case = IncidentReport.objects.create(session_key=session.session_key)
        session["current_ticket_id"] = case.ticket_id
        session.save()
        event = StatusEvent.objects.create(
            incident=case,
            status=IncidentReport.Status.IN_PROGRESS,
            message="เจ้าหน้าที่กำลังดำเนินการ",
        )

        response = self.client.get("/api/ticket/status/?after=0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["events"][0]["id"], event.id)
        self.assertEqual(response.json()["case"]["status"], IncidentReport.Status.OPEN)


class MonitoringTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user("operator", password="secret", is_staff=True)

    def test_monitoring_requires_staff_login(self):
        response = self.client.get("/monitor/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_monitoring_api_returns_stats_and_filters(self):
        IncidentReport.objects.create(session_key="one", title="ลิฟต์ขัดข้อง", urgency="HIGH")
        IncidentReport.objects.create(session_key="two", title="เคสปิด", status=IncidentReport.Status.CLOSED)
        self.client.force_login(self.staff)

        response = self.client.get("/api/monitor/cases/?status=OPEN&q=ลิฟต์")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["stats"]["total"], 2)
        self.assertEqual(response.json()["stats"]["urgent"], 1)
        self.assertEqual(response.json()["result_count"], 1)
        self.assertEqual(response.json()["cases"][0]["title"], "ลิฟต์ขัดข้อง")
