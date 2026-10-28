import base64
import hashlib
import json
import logging
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core import signing
from django.core.cache import cache
from django.http import HttpResponseRedirect
from django.views.decorators.http import require_GET

from .auth import SESSION_SECONDS, client_ip

logger = logging.getLogger("pulse.auth")

COOKIE = "pulse_sso"
COOKIE_SECONDS = 600
TIMEOUT = 15


class SsoError(Exception):
    pass


def http_json(url, data=None, headers=None):
    request = Request(url, data=urlencode(data).encode() if data else None, headers=headers or {})
    try:
        with urlopen(request, timeout=TIMEOUT) as res:
            return json.loads(res.read())
    except HTTPError as e:
        raise SsoError(f"OCI returned {e.code}: {e.read().decode('utf-8', 'replace')[:300]}") from e
    except (URLError, TimeoutError, ValueError) as e:
        raise SsoError(f"Cannot reach OCI: {e}") from e


def discovery():
    found = cache.get("oci:discovery")
    if not found:
        found = http_json(f"{settings.OCI_ISSUER_URL}/.well-known/openid-configuration")
        cache.set("oci:discovery", found, 3600)
    return found


def challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def signing_key(jwks_uri, token):
    return jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(token).key


def back_to_login(reason):
    response = HttpResponseRedirect(f"/?sso_error={reason}")
    response.delete_cookie(COOKIE)
    return response


@require_GET
def start(request):
    if not settings.OCI_ENABLED:
        return back_to_login("not_configured")
    try:
        endpoint = discovery()["authorization_endpoint"]
    except (SsoError, KeyError):
        logger.exception("OCI sign-in could not start")
        return back_to_login("unavailable")
    attempt = {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "verifier": secrets.token_urlsafe(64),
    }
    params = urlencode({
        "client_id": settings.OCI_CLIENT_ID,
        "response_type": "code",
        "scope": "openid email profile",
        "redirect_uri": settings.OCI_REDIRECT_URI,
        "state": attempt["state"],
        "nonce": attempt["nonce"],
        "code_challenge": challenge(attempt["verifier"]),
        "code_challenge_method": "S256",
    })
    response = HttpResponseRedirect(f"{endpoint}?{params}")
    response.set_signed_cookie(COOKIE, json.dumps(attempt), salt=COOKIE, max_age=COOKIE_SECONDS,
                               httponly=True, secure=settings.SESSION_COOKIE_SECURE, samesite="Lax")
    return response


def verified_claims(code, attempt):
    found = discovery()
    basic = base64.b64encode(f"{settings.OCI_CLIENT_ID}:{settings.OCI_CLIENT_SECRET}".encode()).decode()
    tokens = http_json(found["token_endpoint"], {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.OCI_REDIRECT_URI,
        "code_verifier": attempt["verifier"],
    }, {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    claims = jwt.decode(
        tokens["id_token"],
        signing_key(found["jwks_uri"], tokens["id_token"]),
        algorithms=["RS256"],
        audience=settings.OCI_CLIENT_ID,
        issuer=found["issuer"],
        leeway=60,
        options={"require": ["exp", "iat", "iss", "aud", "sub"]},
    )
    if not secrets.compare_digest(str(claims.get("nonce", "")), attempt["nonce"]):
        raise SsoError("The sign-in reply does not match this attempt")
    profile = http_json(found["userinfo_endpoint"], headers={"Authorization": f"Bearer {tokens['access_token']}"})
    return {**claims, **profile}


def find_user(claims):
    email = str(claims.get("email") or claims.get("sub") or "").strip().lower()
    if "@" not in email:
        return None
    users = list(get_user_model().objects.filter(email__iexact=email, is_active=True)[:2])
    return users[0] if len(users) == 1 else None


@require_GET
def callback(request):
    try:
        attempt = json.loads(request.get_signed_cookie(COOKIE, salt=COOKIE, max_age=COOKIE_SECONDS))
    except (KeyError, ValueError, signing.BadSignature):
        return back_to_login("expired")
    if request.GET.get("error"):
        logger.warning("OCI sign-in refused: %s ip=%s", request.GET.get("error"), client_ip(request))
        return back_to_login("refused")
    code = request.GET.get("code")
    if not code or not secrets.compare_digest(request.GET.get("state", ""), attempt["state"]):
        return back_to_login("expired")
    try:
        claims = verified_claims(code, attempt)
    except (SsoError, jwt.PyJWTError, KeyError) as e:
        logger.warning("OCI sign-in failed: %s ip=%s", e, client_ip(request))
        return back_to_login("failed")
    user = find_user(claims)
    if user is None:
        logger.warning("OCI sign-in has no Pulse user: email=%s ip=%s", claims.get("email"), client_ip(request))
        return back_to_login("no_access")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session.set_expiry(SESSION_SECONDS)
    logger.info("OCI sign-in succeeded: user=%s ip=%s", user.get_username(), client_ip(request))
    response = HttpResponseRedirect("/")
    response.delete_cookie(COOKIE)
    return response
