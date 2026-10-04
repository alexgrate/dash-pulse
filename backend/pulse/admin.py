from django.contrib import admin
from django.contrib.auth.models import Group
from django.shortcuts import redirect

from .models import ExploreLog

admin.site.site_header = "Dash Pulse · Users"
admin.site.site_title = "Dash Pulse"
admin.site.index_title = "Manage who can sign in"
admin.site.site_url = "/"
admin.site.unregister(Group)


def dashboard_login(request, extra_context=None):
    return redirect("/")


admin.site.login = dashboard_login


@admin.register(ExploreLog)
class ExploreLogAdmin(admin.ModelAdmin):
    list_display = ("at", "user", "path", "query", "ip")
    list_filter = ("user",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
