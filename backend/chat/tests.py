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


class OperationsBoardTests(TestCase):
    def setUp(self):
        self.reporter = self.client_class()
        session = self.reporter.session
        self.case = IncidentReport.objects.create(session_key=session.session_key)
        session["current_ticket_id"] = self.case.pk
        session.save()
        self.editor = get_user_model().objects.create_user(
            username="operations-editor", is_staff=True, is_superuser=True,
        )
        self.endpoint = f"/api/operations/cases/{self.case.pk}/"
        self.values = {
            "status": "CLOSED", "urgency": "HIGH", "location": "สถานีตัวอย่าง",
            "latitude": "13.756300", "longitude": "100.501800",
            "version": self.case.updated_at.isoformat(),
        }

    def test_close_case_and_save_coordinates_notifies_only_reporter(self):
        self.client.force_login(self.editor)
        response = self.client.post(self.endpoint, self.values)
        self.assertEqual(response.status_code, 200, response.content)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, IncidentReport.Status.CLOSED)
        self.assertEqual(str(self.case.latitude), "13.756300")
        self.assertEqual(str(self.case.longitude), "100.501800")
        self.assertEqual(self.case.urgency, "HIGH")
        self.assertEqual(self.case.location, "สถานีตัวอย่าง")
        self.assertEqual(self.client.post(self.endpoint, self.values).status_code, 200)
        self.assertEqual(self.case.status_events.count(), 1)
        self.assertEqual(self.case.messages.count(), 1)

        monitor = self.client.get("/api/monitor/cases/").json()["cases"][0]
        self.assertEqual(monitor["coordinates"], [13.7563, 100.5018])
        event = self.reporter.get("/api/ticket/status/?after=0").json()["events"][0]
        self.assertEqual(event["status"], IncidentReport.Status.CLOSED)
        messages = self.reporter.get("/api/chat/state/").json()["messages"]
        self.assertIn("ปิดเคสแล้ว", messages[0]["content"])
        self.assertEqual(self.client_class().get("/api/ticket/status/").json()["events"], [])

    def test_permissions_coordinates_and_stale_updates(self):
        viewer = get_user_model().objects.create_user(username="operations-viewer", is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(self.endpoint, self.values).status_code, 403)
        self.assertNotContains(self.client.get("/operations/board/"), 'id="case-editor"')
        self.client.force_login(self.editor)
        self.assertContains(self.client.get("/operations/board/"), 'id="pin-map"')
        for fields in ({"longitude": ""}, {"latitude": "91"}):
            self.assertEqual(self.client.post(self.endpoint, self.values | fields).status_code, 400)
        self.assertEqual(self.client.post(self.endpoint, self.values | {"version": "stale"}).status_code, 409)

        response = self.client.post(self.endpoint, self.values | {"status": "OPEN"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(self.case.status_events.exists())
        self.assertFalse(self.case.messages.exists())

    def test_update_requires_csrf_token(self):
        client = self.client_class(enforce_csrf_checks=True)
        client.force_login(self.editor)
        self.assertEqual(client.post(self.endpoint, self.values).status_code, 403)
        client.get("/operations/board/")
        values = self.values | {"csrfmiddlewaretoken": client.cookies["csrftoken"].value}
        self.assertEqual(client.post(self.endpoint, values).status_code, 200)

    def test_board_move_preserves_other_fields(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.post(self.endpoint, self.values).status_code, 200)
        self.case.refresh_from_db()
        move = {"action": "move", "status": "IN_PROGRESS", "version": self.case.updated_at.isoformat()}
        self.assertEqual(self.client.post(self.endpoint, move | {"status": "unknown"}).status_code, 400)
        self.assertEqual(self.client.post(self.endpoint, move | {"version": "stale"}).status_code, 409)
        self.assertEqual(self.client.post(self.endpoint, move).status_code, 200)
        self.assertEqual(self.client.post(self.endpoint, move).status_code, 200)
        self.case.refresh_from_db()
        self.assertEqual(self.case.status, IncidentReport.Status.IN_PROGRESS)
        self.assertEqual(self.case.location, self.values["location"])
        self.assertEqual(self.case.urgency, self.values["urgency"])
        self.assertEqual(str(self.case.latitude), self.values["latitude"])
        self.assertEqual(str(self.case.longitude), self.values["longitude"])
        self.assertEqual(self.case.status_events.count(), 2)
        self.assertEqual(self.case.messages.count(), 2)
