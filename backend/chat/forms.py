from django import forms

from .models import IncidentReport


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


class OperationsCaseForm(forms.ModelForm):
    urgency = forms.ChoiceField(
        required=False,
        choices=[("", "ไม่ระบุ"), ("HIGH", "สูง"), ("MEDIUM", "ปานกลาง"), ("LOW", "ต่ำ")],
    )

    class Meta:
        model = IncidentReport
        fields = ("status", "urgency", "location", "latitude", "longitude")


class OperationsMoveForm(forms.ModelForm):
    class Meta:
        model = IncidentReport
        fields = ("status",)
