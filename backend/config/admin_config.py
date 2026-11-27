from django.contrib.admin.apps import AdminConfig


class BemAdminConfig(AdminConfig):
    default_site = "config.admin_site.BemAdminSite"
