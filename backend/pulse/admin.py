from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth.models import Group
from django.shortcuts import redirect

from . import accounts, mailer
from .auth import EXPLORER_GROUP
from .models import ExploreLog

admin.site.site_header = "Dash Pulse · Users"
admin.site.site_title = "Dash Pulse"
admin.site.index_title = "Manage who can sign in"
admin.site.site_url = "/"
admin.site.unregister(Group)


def dashboard_login(request, extra_context=None):
    return redirect("/")


admin.site.login = dashboard_login

User = get_user_model()


class InviteForm(forms.ModelForm):
    explore = forms.BooleanField(
        required=False,
        label="Explore access",
        help_text="Lets this person click into individual transactions and customers.",
    )

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].help_text = "The link to set a password is sent here."

    def clean_email(self):
        email = self.cleaned_data["email"].strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Another user already has this email address.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_unusable_password()
        if commit:
            user.save()
        return user


def explorer_group():
    return Group.objects.get_or_create(name=EXPLORER_GROUP)[0]


class EditForm(UserChangeForm):
    explore = forms.BooleanField(
        required=False,
        label="Explore access",
        help_text="Lets this person click into individual transactions and customers. Every view is logged.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["is_staff"].label = "Can manage users"
        self.fields["is_staff"].help_text = "Shows the Manage users link and opens this page."
        if self.instance.pk:
            self.fields["explore"].initial = self.instance.groups.filter(name=EXPLORER_GROUP).exists()


@admin.action(description="Send password setup email")
def send_setup_email(modeladmin, request, queryset):
    sent = 0
    for user in queryset:
        if not user.email:
            modeladmin.message_user(request, f"'{user.username}' has no email address.", messages.WARNING)
            continue
        try:
            accounts.send_invite(user, request)
            sent += 1
        except mailer.MailError as e:
            modeladmin.message_user(request, f"Could not email '{user.username}': {e}", messages.ERROR)
    if sent:
        modeladmin.message_user(request, f"Setup email sent to {sent} user(s).", messages.SUCCESS)


admin.site.unregister(User)


@admin.register(User)
class PulseUserAdmin(UserAdmin):
    add_form = InviteForm
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "description": "The person gets an email with a link to choose their own password.",
                "fields": ("username", "email", "first_name", "last_name", "explore"),
            },
        ),
    )
    form = EditForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Access", {"fields": ("is_active", "explore", "is_staff")}),
        ("History", {"fields": ("last_login", "date_joined")}),
    )
    readonly_fields = ("last_login", "date_joined")
    list_display = ("username", "email", "first_name", "last_name", "is_active", "can_explore", "is_staff", "last_login")
    list_filter = ("is_active", "is_staff")
    actions = [send_setup_email]

    @admin.display(boolean=True, description="Explore")
    def can_explore(self, obj):
        return obj.groups.filter(name=EXPLORER_GROUP).exists()

    def save_model(self, request, obj, form, change):
        if change:
            obj.is_superuser = obj.is_staff
        super().save_model(request, obj, form, change)
        if "explore" in form.cleaned_data:
            if form.cleaned_data["explore"]:
                obj.groups.add(explorer_group())
            else:
                obj.groups.remove(explorer_group())
        if change:
            return
        try:
            accounts.send_invite(obj, request)
            self.message_user(request, f"Setup email sent to {obj.email}.", messages.SUCCESS)
        except mailer.MailError as e:
            self.message_user(
                request,
                f"User created, but the email failed: {e} Fix it, then use 'Send password setup email'.",
                messages.ERROR,
            )


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
