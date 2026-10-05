import json
import logging
import time
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger("pulse.mail")

TIMEOUT = 15
_token = {"value": None, "expires": 0}
_lock = Lock()


class MailError(Exception):
    pass


def configured():
    return all(
        (
            settings.MS_GRAPH_TENANT_ID,
            settings.MS_GRAPH_CLIENT_ID,
            settings.MS_GRAPH_CLIENT_SECRET,
            settings.MS_GRAPH_SENDER,
        )
    )


def call(request):
    try:
        with urlopen(request, timeout=TIMEOUT) as res:
            raw = res.read()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        raise MailError(f"Graph returned {e.code}: {detail}") from e
    except (URLError, TimeoutError) as e:
        raise MailError(f"Cannot reach Microsoft: {e}") from e


def access_token():
    with _lock:
        if _token["value"] and _token["expires"] > time.time() + 60:
            return _token["value"]
        body = urlencode(
            {
                "client_id": settings.MS_GRAPH_CLIENT_ID,
                "client_secret": settings.MS_GRAPH_CLIENT_SECRET,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            }
        ).encode()
        url = f"https://login.microsoftonline.com/{quote(settings.MS_GRAPH_TENANT_ID)}/oauth2/v2.0/token"
        data = call(Request(url, data=body, method="POST"))
        _token["value"] = data["access_token"]
        _token["expires"] = time.time() + int(data.get("expires_in", 3600))
        return _token["value"]


def send(to, subject, html):
    if not configured():
        raise MailError("Email is not configured. Set the MS_GRAPH_* values in backend/.env.")
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": html},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": False,
    }
    request = Request(
        f"https://graph.microsoft.com/v1.0/users/{quote(settings.MS_GRAPH_SENDER)}/sendMail",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {access_token()}", "Content-Type": "application/json"},
    )
    call(request)
    logger.info("Mail sent: to=%s subject=%s", to, subject)
