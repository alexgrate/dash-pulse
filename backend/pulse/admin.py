from django.contrib import admin
from django.contrib.auth.models import Group
from django.shortcuts import redirect

admin.site.site_header = "Dash Pulse · Users"
admin.site.site_title = "Dash Pulse"
admin.site.index_title = "Manage who can sign in"
admin.site.site_url = "/"
admin.site.unregister(Group)


def dashboard_login(request, extra_context=None):
    return redirect("/")


admin.site.login = dashboard_login
