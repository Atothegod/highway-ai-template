from django import forms

from .models import IncidentReport


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
