from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from .agent import AgentResult
from .models import IncidentReport, StatusEvent


class ChatLoginTests(TestCase):
    def test_chat_requires_username_and_consent(self):
        self.assertRedirects(self.client.get("/"), "/login/")
        for username, consent in (("reporter", ""), ("   ", "on")):
            with self.subTest(username=username, consent=consent):
                response = self.client.post("/login/", {"username": username, "pdpa_consent": consent})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
                self.assertNotIn("chat_identity", self.client.session)

        for method, path in (
            ("get", "/api/chat/state/"),
            ("post", "/api/chat/"),
            ("get", "/api/ticket/status/"),
            ("post", "/api/chat/reset/"),
        ):
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path).status_code, 403)

    def test_login_binds_consent_to_existing_chat_session(self):
        session = self.client.session
        case = IncidentReport.objects.create(session_key=session.session_key)
        session["current_ticket_id"] = case.pk
        session.save()

        response = self.client.post("/login/", {"username": "  reporter  ", "pdpa_consent": "on"})
        self.assertRedirects(response, "/")
        self.assertContains(self.client.get("/"), "reporter")
        self.assertEqual(self.client.session.session_key, session.session_key)
        identity = self.client.session["chat_identity"]
        self.assertEqual(identity["username"], "reporter")
        self.assertTrue(identity["consented_at"])
        self.assertEqual(self.client.get("/api/chat/state/").json()["case"]["ticket_id"], case.pk)
        self.assertEqual(self.client.post("/api/chat/reset/").status_code, 200)
        self.assertEqual(self.client.session["chat_identity"], identity)


class IncidentFlowTests(TestCase):
    def setUp(self):
        self.client.post("/login/", {"username": "reporter", "pdpa_consent": "on"})

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
        self.assertEqual(case.session_key, self.client.session.session_key)
        self.assertTrue(case.ticket_id.startswith("BEM-"))
        self.assertEqual(case.flow_state, IncidentReport.FlowState.CONFIRMING)
        self.assertEqual(case.category_level_2, "ความพร้อมให้บริการรถไฟฟ้า")
        self.assertIn("ผมเปิดเคสให้แล้ว", response.json()["reply"])
        self.assertIn(case.ticket_id, response.json()["reply"])
        self.assertEqual(case.messages.count(), 2)
        self.assertEqual(case.status_events.get().status, IncidentReport.Status.OPEN)

    @patch("chat.views.run_agent")
    def test_occurrence_keeps_original_and_clears_stale_normalization(self, mocked_agent):
        mocked_agent.return_value = AgentResult(
            reply="รับทราบครับ", flow_state="COLLECTING", should_open_case=True,
            occurred_at="27 พฤศจิกายน 2026 เวลา 14:30",
            occurred_at_normalized="2026-11-27T14:30:00+07:00",
        )
        response = self.client.post("/api/chat/", {"message": "แจ้งเหตุ"}, content_type="application/json")
        self.assertEqual(response.json()["case"]["occurred_at_normalized"], "2026-11-27T14:30:00+07:00")

        mocked_agent.return_value.occurred_at = "ช่วงบ่าย ไม่ทราบเวลาแน่ชัด"
        mocked_agent.return_value.occurred_at_normalized = ""
        response = self.client.post("/api/chat/", {"message": "ขอแก้ไขเวลา"}, content_type="application/json")
        self.assertIsNone(response.json()["case"]["occurred_at_normalized"])
        self.assertEqual(IncidentReport.objects.get().occurred_at, "ช่วงบ่าย ไม่ทราบเวลาแน่ชัด")

    @patch.dict("os.environ", {"INCIDENT_GEOCODER_URL": "https://maps.example.test/search"})
    @patch("chat.views.urlopen")
    def test_map_starts_at_reported_place_without_saving_suggestion(self, geocoder):
        session = self.client.session
        case = IncidentReport.objects.create(session_key=session.session_key, location="สถานีสุขุมวิท")
        session["current_ticket_id"] = case.pk
        session.save()
        geocoder.return_value.__enter__.return_value.read.return_value = (
            '[{"lat":"13.737","lon":"100.561"}]'
        )

        response = self.client.get("/api/chat/pin/", {"ticket_id": case.pk})

        self.assertEqual(response.json()["hint"], [13.737, 100.561])
        self.assertIn("countrycodes=th", geocoder.call_args.args[0].full_url)
        case.refresh_from_db()
        self.assertIsNone(case.latitude)
        self.assertIsNone(case.longitude)

    @patch("chat.views.run_agent")
    def test_submission_requires_confirmed_pin_and_stamps_once(self, mocked_agent):
        session = self.client.session
        case = IncidentReport.objects.create(session_key=session.session_key, location="13.75, 100.50")
        session["current_ticket_id"] = case.pk
        session.save()
        pin_url = f"/api/chat/pin/?ticket_id={case.pk}"
        self.assertEqual(self.client.get(pin_url).json()["hint"], [13.75, 100.50])

        mocked_agent.side_effect = lambda **kwargs: AgentResult(reply="รับเรื่องแล้วครับ", flow_state="SUBMITTED")
        payload = {"message": "ยืนยัน"}
        self.assertEqual(self.client.post("/api/chat/", payload, content_type="application/json").json()
                         ["case"]["flow_state"], "CONFIRMING")
        case.refresh_from_db()
        self.assertIsNone(case.submitted_at)

        other = self.client_class()
        other.post("/login/", {"username": "other", "pdpa_consent": "on"})
        coords = {"latitude": "13.751234", "longitude": "100.501234"}
        self.assertEqual(other.post(pin_url, coords, content_type="application/json").status_code, 404)
        self.assertEqual(self.client.post(pin_url, {**coords, "latitude": "91"},
                                          content_type="application/json").status_code, 400)
        saved = self.client.post(pin_url, coords, content_type="application/json")
        self.assertEqual(saved.json()["case"]["pin"], [13.751234, 100.501234])

        submitted = self.client.post("/api/chat/", payload, content_type="application/json").json()["case"]
        self.assertEqual(submitted["flow_state"], "SUBMITTED")
        self.assertIsNotNone(submitted["submitted_at"])
        retried = self.client.post("/api/chat/", payload, content_type="application/json").json()["case"]
        self.assertEqual(retried["submitted_at"], submitted["submitted_at"])

    @patch("chat.views.run_agent")
    def test_session_cannot_read_another_sessions_ticket(self, mocked_agent):
        mocked_agent.return_value = AgentResult(
            reply="ขอข้อมูลเพิ่มครับ", flow_state="COLLECTING", should_open_case=True
        )
        self.client.post("/api/chat/", {"message": "พบปัญหา"}, content_type="application/json")

        other_client = self.client_class()
        other_client.post("/login/", {"username": "reporter", "pdpa_consent": "on"})
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
        self.reporter.post("/login/", {"username": "reporter", "pdpa_consent": "on"})
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
        other_reporter = self.client_class()
        other_reporter.post("/login/", {"username": "reporter", "pdpa_consent": "on"})
        self.assertEqual(other_reporter.get("/api/ticket/status/").json()["events"], [])

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
