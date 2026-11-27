from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model

from .agent import AgentResult
from .models import IncidentReport, StatusEvent


class RoleLandingTests(TestCase):
    def test_landing_links_to_each_login(self):
        response = self.client.get("/")
        for path in ("/login/", "/operations/login/"):
            self.assertContains(response, f'href="{path}"')
        self.assertNotContains(response, "/admin/")

    def test_old_demo_bookmark_leads_to_protected_board(self):
        self.assertRedirects(self.client.get("/operations/demo/board/"), "/operations/board/",
                             fetch_redirect_response=False)
        self.assertRedirects(self.client.get("/operations/board/"), "/operations/login/?next=/operations/board/")
        self.assertEqual(self.client.get("/api/operations/demo/cases/").status_code, 404)
        self.assertRedirects(self.client.get("/operations/staff/login/?next=/operations/board/"),
                             "/operations/login/?next=/operations/board/")

    def test_operations_requires_staff_and_returns_to_requested_page(self):
        login_path = "/operations/login/?next=/operations/board/"
        self.assertRedirects(self.client.get("/operations/board/"), login_path)
        users = get_user_model().objects
        users.create_user(username="visitor", password="test-pass")
        users.create_user(username="operator", password="test-pass", is_staff=True)
        denied = self.client.post(login_path, {"username": "visitor", "password": "test-pass", "next": "/operations/board/"})
        self.assertContains(denied, "บัญชีนี้ไม่มีสิทธิ์เข้า Operations")
        allowed = self.client.post(login_path, {"username": "operator", "password": "test-pass", "next": "/operations/board/"})
        self.assertRedirects(allowed, "/operations/board/")


    def test_operations_staff_cannot_enter_admin_but_superuser_can(self):
        users = get_user_model().objects
        operator = users.create_user(username="ordinary-staff", password="test-pass", is_staff=True)
        self.client.force_login(operator)
        self.assertContains(self.client.get("/operations/"), "Dashboard")
        self.assertNotContains(self.client.get("/monitor/"), "/admin/")
        self.assertRedirects(self.client.get("/admin/"), "/admin/login/?next=/admin/")
        self.assertRedirects(self.client.get("/admin/chat/incidentreport/"),
                             "/admin/login/?next=/admin/chat/incidentreport/")
        self.client.logout()
        denied = self.client.post("/admin/login/", {"username": "ordinary-staff", "password": "test-pass"})
        self.assertContains(denied, "บัญชีนี้ไม่มีสิทธิ์เข้าหน้าผู้ดูแลระบบ")
        self.assertNotIn("_auth_user_id", self.client.session)

        administrator = users.create_superuser(username="administrator", password="test-pass")
        self.client.force_login(administrator)
        self.assertEqual(self.client.get("/admin/").status_code, 200)


    def test_logout_clears_both_roles_and_returns_to_landing(self):
        operator = get_user_model().objects.create_user(username="logout-operator", is_staff=True)
        self.client.force_login(operator)
        self.client.post("/login/", {"username": "reporter", "pdpa_consent": "on"})
        self.assertContains(self.client.get("/operations/"), "Logout")
        self.assertContains(self.client.get("/chat/"), "Logout")
        session_key = self.client.session.session_key
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.assertRedirects(self.client.post("/logout/"), "/")
        self.assertNotIn("chat_identity", self.client.session)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotEqual(self.client.session.session_key, session_key)
        self.assertRedirects(self.client.get("/chat/"), "/login/")
        self.assertRedirects(self.client.get("/operations/"), "/operations/login/?next=/operations/")


class ConversationsTests(TestCase):
    @patch("chat.views.run_agent")
    def test_staff_reply_is_delivered_and_pauses_agent_until_resumed(self, mocked_agent):
        reporter = self.client_class()
        reporter.post("/login/", {"username": "ผู้แจ้งทดสอบ", "pdpa_consent": "on"})
        mocked_agent.return_value = AgentResult(
            reply="รับทราบครับ", flow_state="COLLECTING", should_open_case=True,
        )
        response = reporter.post("/api/chat/", {"message": "พบเหตุทดสอบ"}, content_type="application/json")
        ticket = response.json()["case"]["ticket_id"]
        self.assertEqual(IncidentReport.objects.get(pk=ticket).reporter_name, "ผู้แจ้งทดสอบ")

        endpoint = f"/api/operations/conversations/{ticket}/"
        editor = get_user_model().objects.create_user(username="operator", is_staff=True, is_superuser=True)
        self.client.force_login(editor)
        page = self.client.get("/operations/conversations/", {"ticket": ticket})
        self.assertContains(page, "ผู้แจ้งทดสอบ")
        self.assertContains(page, "BEM Care Web")
        self.assertEqual(self.client.get(endpoint).json()["messages"][0]["content"], "พบเหตุทดสอบ")

        self.assertEqual(self.client.post(endpoint, {"action": "reply", "message": "กำลังตรวจสอบ"}).status_code, 200)
        poll = reporter.get("/api/ticket/status/", {"staff_after": 0}).json()
        self.assertTrue(poll["case"]["human_mode"])
        staff_message, = poll["staff_messages"]
        self.assertEqual(staff_message["content"], "กำลังตรวจสอบ")
        self.assertEqual(reporter.get("/api/chat/state/").json()["staff_cursor"], staff_message["id"])
        self.assertEqual(reporter.get("/api/ticket/status/", {"staff_after": staff_message["id"]}).json()["staff_messages"], [])
        self.assertEqual(self.client.get(endpoint).json()["messages"][-1]["author_name"], "operator")

        mocked_agent.reset_mock()
        response = reporter.post("/api/chat/", {"message": "ขอบคุณ"}, content_type="application/json")
        self.assertIsNone(response.json()["reply"])
        mocked_agent.assert_not_called()
        self.assertEqual(self.client.get(endpoint, {"after": staff_message["id"]}).json()["messages"][0]["content"], "ขอบคุณ")

        self.assertEqual(self.client.post(endpoint, {"action": "resume"}).status_code, 200)
        response = reporter.post("/api/chat/", {"message": "ขอแจ้งข้อมูลเพิ่ม"}, content_type="application/json")
        self.assertFalse(response.json()["case"]["human_mode"])
        mocked_agent.assert_called_once()

    def test_transcript_permissions_and_closed_case_guard(self):
        from django.contrib.auth.models import Permission

        case = IncidentReport.objects.create(session_key="reporter", status=IncidentReport.Status.CLOSED)
        endpoint = f"/api/operations/conversations/{case.pk}/"
        viewer = get_user_model().objects.create_user(username="viewer", is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="chat", codename="view_chatmessage"))
        self.assertEqual(self.client.get(endpoint).status_code, 200)
        self.assertEqual(self.client.post(endpoint, {"action": "reply", "message": "สวัสดี"}).status_code, 403)
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label="chat", codename="add_chatmessage"))
        self.assertEqual(self.client.post(endpoint, {"action": "reply", "message": "สวัสดี"}).status_code, 409)
        self.assertFalse(case.messages.exists())


class ChatLoginTests(TestCase):
    def test_chat_requires_username_and_consent(self):
        self.assertRedirects(self.client.get("/chat/"), "/login/")
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
        self.assertRedirects(response, "/chat/")
        self.assertContains(self.client.get("/chat/"), "reporter")
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
    def test_confirmed_routing_uses_receipt_time_and_document_defaults(self, mocked_agent):
        import datetime

        mocked_agent.return_value = AgentResult(
            reply="กรุณายืนยัน", flow_state="CONFIRMING", should_open_case=True,
            routing_category="T01.02", location="13.75, 100.50",
            occurred_at="ช่วงเช้า", occurred_at_normalized="",
        )
        self.client.post("/api/chat/", {"message": "ประตูกั้นชานชาลาขัดข้อง"}, content_type="application/json")
        case = IncidentReport.objects.get()
        self.assertIsNotNone(case.received_at)
        self.assertIsNone(case.occurred_at_normalized)
        self.assertEqual(case.assigned_team, "")
        self.client.post(f"/api/chat/pin/?ticket_id={case.pk}", {"latitude": 13.75, "longitude": 100.50},
                         content_type="application/json")
        mocked_agent.return_value.flow_state = "SUBMITTED"
        self.client.post("/api/chat/", {"message": "ยืนยัน"}, content_type="application/json")
        case.refresh_from_db()
        self.assertEqual(case.assigned_team, "RAIL-ME")
        self.assertEqual(case.sla_due_at, case.received_at + datetime.timedelta(hours=168))
        self.assertGreaterEqual(case.assigned_at, case.submitted_at)
        self.assertEqual(case.grc_handoff_status, "PENDING")
        self.assertEqual(case.grc_case_id, "")

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
        self.assertIn("/operations/login/", response.url)

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

    @patch("chat.views.run_agent")
    def test_status_changes_produce_live_and_persisted_chat_updates(self, mocked_agent):
        self.client.force_login(self.editor)
        cursor = self.reporter.get("/api/chat/state/").json()["cursor"]
        for status, expected in (
            ("IN_PROGRESS", "เจ้าหน้าที่กำลังดำเนินการตรวจสอบและแก้ไข"),
            ("CLOSED", "ดำเนินการเสร็จสิ้นและปิดเคสแล้ว"),
        ):
            version = self.case.updated_at.isoformat()
            response = self.client.post(self.endpoint, {"action": "move", "status": status, "version": version})
            self.assertEqual(response.status_code, 200)
            self.case.refresh_from_db()
            poll = self.reporter.get("/api/ticket/status/", {"after": cursor}).json()
            self.assertEqual(poll["case"]["status"], status)
            event, = poll["events"]
            self.assertEqual(event["chat_message"], f"อัปเดต {self.case.pk} · {expected}")
            cursor = event["id"]
        state = self.reporter.get("/api/chat/state/").json()
        self.assertEqual(state["cursor"], cursor)
        self.assertEqual(len(state["messages"]), 2)
        self.assertTrue(all(m["is_status_update"] for m in state["messages"]))
        self.assertEqual(state["events"], [])
        mocked_agent.return_value = AgentResult(
            reply="รับทราบครับ", flow_state="COLLECTING", should_open_case=True,
            description="เหตุใหม่",
        )
        followup = self.reporter.post("/api/chat/", {"message": "ขอแจ้งเหตุใหม่"},
                                      content_type="application/json").json()
        self.assertTrue(followup["started_new"])
        next_ticket = followup["case"]["ticket_id"]
        self.assertNotEqual(next_ticket, self.case.pk)
        self.assertEqual(followup["case"]["status"], "OPEN")
        self.assertEqual(mocked_agent.call_args.kwargs["history"], "")
        self.assertEqual(self.case.messages.count(), 2)
        self.assertEqual(self.case.status_events.count(), 2)
        new_state = self.reporter.get("/api/chat/state/").json()
        self.assertEqual([e["ticket_id"] for e in new_state["events"]], [next_ticket])
        self.assertFalse(any(self.case.pk in m["content"] for m in new_state["messages"]))
        poll = self.reporter.get("/api/ticket/status/").json()
        self.assertEqual([e["ticket_id"] for e in poll["events"]], [next_ticket])

    @patch("chat.views.run_agent")
    def test_case_closed_while_agent_is_processing_restarts_message(self, mocked_agent):
        def analyze(**kwargs):
            if kwargs["case"].pk == self.case.pk:
                IncidentReport.objects.filter(pk=self.case.pk).update(status=IncidentReport.Status.CLOSED)
            return AgentResult(reply="รับทราบครับ", flow_state="COLLECTING", should_open_case=True)

        def process(**kwargs):
            if isinstance(kwargs["case"], IncidentReport):
                return analyze(**kwargs)
            return AgentResult(reply="รับทราบครับ", flow_state="COLLECTING", should_open_case=True)

        mocked_agent.side_effect = process
        result = self.reporter.post("/api/chat/", {"message": "แจ้งเหตุอีกเรื่อง"},
                                    content_type="application/json").json()
        self.assertTrue(result["started_new"])
        self.assertNotEqual(result["case"]["ticket_id"], self.case.pk)
        self.assertEqual(mocked_agent.call_count, 2)
        self.assertEqual(mocked_agent.call_args.kwargs["history"], "")
        self.assertFalse(self.case.messages.exists())

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
