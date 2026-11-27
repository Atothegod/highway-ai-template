from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .models import IncidentReport
from .routing import CATEGORY_CHOICES



class ChatLoginForm(forms.Form):
    username = forms.CharField(
        label="ชื่อผู้ใช้",
        max_length=150,
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
        error_messages={"required": "กรุณากรอกชื่อผู้ใช้"},
    )
    pdpa_consent = forms.BooleanField(
        label="ฉันยินยอมให้ BEM ใช้ชื่อผู้ใช้และข้อมูลที่ฉันส่งในแชตเพื่อรับแจ้งเหตุ ดำเนินการ และแจ้งความคืบหน้า",
        error_messages={"required": "กรุณาให้ความยินยอมก่อนเข้าแชต"},
    )


class OperationsLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise forms.ValidationError("บัญชีนี้ไม่มีสิทธิ์เข้า Operations", code="operations_forbidden")


class OperationsCaseForm(forms.ModelForm):
    routing_category = forms.ChoiceField(required=False, choices=[("", "รอตรวจหมวด"), *CATEGORY_CHOICES])

    def clean(self):
        data = super().clean()
        if data.get("grc_handoff_status") == "ACCEPTED" and not data.get("grc_case_id"):
            self.add_error("grc_case_id", "กรุณาระบุเลขเคส GRC เมื่อ GRC รับเรื่องแล้ว")
        return data
    urgency = forms.ChoiceField(
        required=False,
        choices=[("", "ไม่ระบุ"), ("HIGH", "สูง"), ("MEDIUM", "ปานกลาง"), ("LOW", "ต่ำ")],
    )

    class Meta:
        model = IncidentReport
        fields = (
            "status", "urgency", "location", "latitude", "longitude",
            "routing_category", "assigned_team", "resolution_summary", "grc_case_id", "grc_handoff_status",
        )


class OperationsMoveForm(forms.ModelForm):
    class Meta:
        model = IncidentReport
        fields = ("status",)
