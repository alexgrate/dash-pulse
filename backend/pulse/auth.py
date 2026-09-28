import json
import logging
from functools import wraps

from django.contrib.auth import authenticate, login, logout
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

logger = logging.getLogger("pulse.auth")

MAX_USER_FAILURES = 5
MAX_IP_FAILURES = 20
LOCK_SECONDS = 15 * 60
SESSION_SECONDS = 12 * 60 * 60
REMEMBER_SECONDS = 30 * 24 * 60 * 60


def client_ip(request):
    return request.META.get("REMOTE_ADDR", "")


def failure_keys(ip, username):
    return f"auth:fail:{ip}:{username.lower()}", f"auth:fail-ip:{ip}"


def is_locked(ip, username):
    user_key, ip_key = failure_keys(ip, username)
    return cache.get(user_key, 0) >= MAX_USER_FAILURES or cache.get(ip_key, 0) >= MAX_IP_FAILURES


def record_failure(ip, username):
    for key in failure_keys(ip, username):
        if not cache.add(key, 1, LOCK_SECONDS):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, LOCK_SECONDS)


def session_payload(request):
    user = request.user
    signed_in = user.is_authenticated
    return {"authenticated": signed_in, "username": user.get_username() if signed_in else None}


def login_required_json(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"error": "login_required"}, status=401)
        return view(request, *args, **kwargs)

    return wrapped


@require_GET
@ensure_csrf_cookie
def session(request):
    return JsonResponse(session_payload(request))


@require_POST
def sign_in(request):
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    username = str(body.get("username", "")).strip()[:150]
    password = str(body.get("password", ""))[:256]
    remember = body.get("remember") is True
    ip = client_ip(request)

    if not username or not password:
        return JsonResponse({"error": "Enter your username and password."}, status=400)
    if is_locked(ip, username):
        logger.warning("Login blocked, too many failures: user=%s ip=%s", username, ip)
        return JsonResponse({"error": "Too many failed attempts. Try again in 15 minutes."}, status=429)

    user = authenticate(request, username=username, password=password)
    if user is None:
        record_failure(ip, username)
        logger.warning("Login failed: user=%s ip=%s", username, ip)
        return JsonResponse({"error": "Incorrect username or password."}, status=401)

    cache.delete(failure_keys(ip, username)[0])
    login(request, user)
    request.session.set_expiry(REMEMBER_SECONDS if remember else SESSION_SECONDS)
    logger.info("Login succeeded: user=%s ip=%s remember=%s", user.get_username(), ip, remember)
    return JsonResponse(session_payload(request))


@require_POST
def sign_out(request):
    if request.user.is_authenticated:
        logger.info("Logout: user=%s ip=%s", request.user.get_username(), client_ip(request))
    logout(request)
    return JsonResponse({"authenticated": False, "username": None})
