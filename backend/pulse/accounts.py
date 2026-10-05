import json
import logging
from html import escape

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.http import require_POST

from . import mailer
from .auth import client_ip

logger = logging.getLogger("pulse.auth")

FORGOT_PER_IP = 5
FORGOT_PER_EMAIL = 3
FORGOT_WINDOW = 60 * 60
LINK_HOURS = settings.PASSWORD_RESET_TIMEOUT // 3600


def body(request):
    try:
        data = json.loads(request.body or b"{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def site_url(request):
    return settings.PULSE_PUBLIC_URL or request.build_absolute_uri("/").rstrip("/")


def setup_link(user, request):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{site_url(request)}/#/set-password/{uid}/{token}"


def email_html(name, intro, link, action):
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:0 auto;padding:32px 24px;color:#1e1b2e">
<div style="font-size:20px;font-weight:600;color:#4a1a6b">Dash Pulse</div>
<p style="font-size:15px;line-height:1.6;margin:24px 0 8px">Hello {escape(name)},</p>
<p style="font-size:15px;line-height:1.6;margin:0 0 24px">{intro}</p>
<a href="{escape(link)}" style="display:inline-block;background:#4a1a6b;color:#ffffff;text-decoration:none;padding:12px 24px;border-radius:10px;font-weight:600">{action}</a>
<p style="font-size:13px;line-height:1.6;color:#6b6880;margin:24px 0 0">This link works once and expires in {LINK_HOURS} hours. If the button does not work, copy this address into your browser:<br><span style="word-break:break-all">{escape(link)}</span></p>
<p style="font-size:13px;line-height:1.6;color:#6b6880;margin:16px 0 0">If you did not expect this email, you can ignore it. Nothing changes until the link is used.</p>
</div>"""


def send_invite(user, request):
    link = setup_link(user, request)
    intro = (
        f"An account has been created for you on Dash Pulse, the Dash MFB operations dashboard. "
        f"Your username is <b>{escape(user.get_username())}</b>. Choose a password to finish setting it up."
    )
    mailer.send(user.email, "Set up your Dash Pulse account", email_html(display_name(user), intro, link, "Set my password"))
    logger.info("Invite sent: user=%s", user.get_username())


def send_reset(user, request):
    link = setup_link(user, request)
    intro = (
        f"Someone asked to reset the password for the Dash Pulse account <b>{escape(user.get_username())}</b>. "
        f"If that was you, choose a new password below."
    )
    mailer.send(user.email, "Reset your Dash Pulse password", email_html(display_name(user), intro, link, "Choose a new password"))
    logger.info("Reset sent: user=%s", user.get_username())


def display_name(user):
    return user.get_short_name() or user.get_username()


def over_limit(key, limit):
    if cache.add(key, 1, FORGOT_WINDOW):
        return False
    try:
        return cache.incr(key) > limit
    except ValueError:
        cache.set(key, 1, FORGOT_WINDOW)
        return False


def user_from_link(uid, token):
    try:
        pk = force_str(urlsafe_base64_decode(str(uid)))
        user = get_user_model().objects.get(pk=pk)
    except (ValueError, TypeError, OverflowError, get_user_model().DoesNotExist):
        return None
    if not user.is_active or not default_token_generator.check_token(user, str(token)):
        return None
    return user


@require_POST
def forgot(request):
    email = str(body(request).get("email", "")).strip()[:254]
    done = JsonResponse({"ok": True})
    if "@" not in email:
        return JsonResponse({"error": "Enter the email address on your account."}, status=400)
    ip = client_ip(request)
    if over_limit(f"forgot:ip:{ip}", FORGOT_PER_IP) or over_limit(f"forgot:email:{email.lower()}", FORGOT_PER_EMAIL):
        logger.warning("Reset throttled: email=%s ip=%s", email, ip)
        return done
    for user in get_user_model().objects.filter(email__iexact=email, is_active=True):
        try:
            send_reset(user, request)
        except mailer.MailError as e:
            logger.error("Reset email failed: user=%s error=%s", user.get_username(), e)
    return done


@require_POST
def check_link(request):
    data = body(request)
    user = user_from_link(data.get("uid", ""), data.get("token", ""))
    if user is None:
        return JsonResponse({"valid": False})
    return JsonResponse({"valid": True, "username": user.get_username()})


@require_POST
def set_password(request):
    data = body(request)
    user = user_from_link(data.get("uid", ""), data.get("token", ""))
    if user is None:
        return JsonResponse({"error": "This link has expired or was already used. Ask for a new one."}, status=400)
    password = str(data.get("password", ""))[:256]
    try:
        validate_password(password, user)
    except ValidationError as e:
        return JsonResponse({"error": " ".join(e.messages)}, status=400)
    user.set_password(password)
    user.save()
    logger.info("Password set from email link: user=%s ip=%s", user.get_username(), client_ip(request))
    return JsonResponse({"ok": True, "username": user.get_username()})
