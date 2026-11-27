from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError


class BemAdminLoginForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise ValidationError("บัญชีนี้ไม่มีสิทธิ์เข้าหน้าผู้ดูแลระบบ", code="admin_forbidden")


class BemAdminSite(AdminSite):
    login_form = BemAdminLoginForm

    def has_permission(self, request):
        return super().has_permission(request) and request.user.is_superuser
