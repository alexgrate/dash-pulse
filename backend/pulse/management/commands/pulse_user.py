from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Manage Dash Pulse logins: add, password, disable, enable, list"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["add", "password", "disable", "enable", "list"])
        parser.add_argument("username", nargs="?")

    def handle(self, *args, action, username=None, **options):
        users = get_user_model()
        if action == "list":
            for user in users.objects.order_by("username"):
                state = "active" if user.is_active else "disabled"
                last = user.last_login.strftime("%Y-%m-%d %H:%M") if user.last_login else "never"
                self.stdout.write(f"{user.username:<24} {state:<9} last login: {last}")
            return

        if not username:
            raise CommandError("A username is required.")

        if action == "add":
            if users.objects.filter(username__iexact=username).exists():
                raise CommandError(f"User '{username}' already exists.")
            user = users(username=username)
            user.set_password(self.ask_password(user))
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created '{username}'."))
            return

        try:
            user = users.objects.get(username__iexact=username)
        except users.DoesNotExist:
            raise CommandError(f"No user '{username}'.")

        if action == "password":
            user.set_password(self.ask_password(user))
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Password changed for '{user.username}'."))
        else:
            user.is_active = action == "enable"
            user.save()
            self.stdout.write(self.style.SUCCESS(f"'{user.username}' is now {'active' if user.is_active else 'disabled'}."))

    def ask_password(self, user):
        while True:
            first = getpass("Password: ")
            if first != getpass("Password (again): "):
                self.stderr.write("Passwords do not match.")
                continue
            try:
                validate_password(first, user)
            except ValidationError as e:
                self.stderr.write(" ".join(e.messages))
                continue
            return first
