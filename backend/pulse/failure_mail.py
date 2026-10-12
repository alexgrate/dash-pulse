import logging
from datetime import timedelta
from html import escape

from django.conf import settings
from django.utils import timezone

from . import banks as bank_names
from . import mailer
from .models import FailureNotice
from .queries import LEGACY, OUTCOME_SQL, PAYMENTS, fetch, lagos_now
from .reasons import REASON_SQL, classify

logger = logging.getLogger("pulse.mail")

LOOKBACK = timedelta(hours=2)
KEEP_DAYS = 7
MAX_ROWS = 200

KINDS = {
    "INTER": "Transfer to other bank",
    "INTRA": "Transfer within Dash",
    "Data Bundle": "Data",
    "Betting & Lottery": "Betting",
    "Utilities": "Electricity & utilities",
    "Transport and Toll Payment": "Transport & tolls",
}


def recent_failures(now):
    return fetch(f"""
        SELECT l.ID AS id, l.CREATED AS at, l.TRANSACTION_TYPE AS kind, l.AMOUNT AS amount,
               l.ACCOUNT_NUMBER AS account, p.source_account_name AS sender,
               l.BENEFICIARY_NAME AS beneficiary, l.BENEFICIARY_ACCOUNT AS beneficiary_account,
               l.BENEFICIARY_BANK_NAME AS bank, l.BENEFICIARY_BANK_CODE AS bank_code,
               l.PAYMENT_REFERENCE AS reference, COALESCE(l.CBA_REFERENCE, p.cba_reference) AS cba_reference,
               l.PROVIDER_REFERENCE AS provider_reference, p.session_id AS session_id,
               COALESCE(l.PROVIDER, p.provider) AS provider, l.PROVIDER_RESPONSE_CODE AS provider_code,
               l.PROVIDER_RESPONSE_MESSAGE AS provider_message, l.CBA_MESSAGE AS cba_message,
               p.status AS payment_status, p.response_code AS payment_code,
               {REASON_SQL} AS message
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(since)s AND l.CREATED < %(now)s
          AND {OUTCOME_SQL} = 'FAILED'
        ORDER BY l.CREATED, l.ID
    """, {"since": now - LOOKBACK, "now": now + timedelta(minutes=1)})


SKIP_REASONS = {"Insufficient funds"}


def worth_mailing(row):
    return classify(row["message"])[0] not in SKIP_REASONS


def new_failures(now):
    rows = recent_failures(now)
    seen = set(FailureNotice.objects.filter(tx_id__in=[r["id"] for r in rows]).values_list("tx_id", flat=True))
    return [r for r in rows if r["id"] not in seen]


def split(rows):
    return [r for r in rows if worth_mailing(r)], [r for r in rows if not worth_mailing(r)]


def remember(rows):
    FailureNotice.objects.bulk_create([FailureNotice(tx_id=r["id"]) for r in rows], ignore_conflicts=True)
    FailureNotice.objects.filter(sent_at__lt=timezone.now() - timedelta(days=KEEP_DAYS)).delete()


def naira(value):
    return f"₦{float(value or 0):,.2f}"


SIDES = {
    "customer": "customer side",
    "account": "account restriction",
    "system": "bank or partner side",
    "unknown": "cause not recorded",
}


def field(label, value, mono=False):
    if value in (None, ""):
        return ""
    style = "font-family:Consolas,monospace;font-size:13px" if mono else ""
    return (f'<tr><td style="padding:3px 16px 3px 0;color:#6b6880;font-size:13px;white-space:nowrap;vertical-align:top">'
            f'{label}</td><td style="padding:3px 0;font-size:14px;{style}">{escape(str(value))}</td></tr>')


def block(r):
    reason, kind = classify(r["message"])
    bank = bank_names.canonical(r["bank"]) if r["bank"] else None
    to = " · ".join(x for x in (r.get("beneficiary"), r.get("beneficiary_account"), bank) if x)
    rows = "".join((
        field("Time (Lagos)", f"{r['at']:%d %b %Y, %H:%M:%S}"),
        field("Type", KINDS.get(r["kind"], r["kind"])),
        field("Amount", naira(r["amount"])),
        field("From account", " · ".join(x for x in (r.get("account"), r.get("sender")) if x)),
        field("To", to),
        field("Bank code", r.get("bank_code"), True),
        field("Payment reference", r.get("reference"), True),
        field("Core banking reference", r.get("cba_reference"), True),
        field("Partner reference", r.get("provider_reference"), True),
        field("NIP session ID", r.get("session_id"), True),
        field("Payment partner", r.get("provider")),
        field("Partner response", " · ".join(x for x in (r.get("provider_code"), r.get("provider_message")) if x)),
        field("Core banking message", r.get("cba_message")),
        field("Payment record", " · ".join(x for x in (r.get("payment_status"), r.get("payment_code")) if x)),
        field("Dashboard ID", r["id"], True),
    ))
    return f"""<div style="border:1px solid #e6e2ef;border-left:4px solid #b42318;border-radius:8px;padding:14px 16px;margin:0 0 14px">
<div style="font-size:16px;font-weight:600;color:#b42318">{escape(reason)}
<span style="font-size:12px;font-weight:400;color:#6b6880"> · {escape(SIDES.get(kind, kind or ''))}</span></div>
<table cellspacing="0" style="border-collapse:collapse;margin-top:8px">{rows}</table></div>"""


def email(rows, skipped=0):
    shown = rows[:MAX_ROWS]
    more = len(rows) - len(shown)
    total = sum(float(r["amount"] or 0) for r in rows)
    link = settings.PULSE_PUBLIC_URL or ""
    note = (f'<p style="font-size:13px;color:#6b6880">{skipped} other failure{"s" if skipped != 1 else ""} '
            f'for insufficient funds in the same period {"were" if skipped != 1 else "was"} not included.</p>'
            if skipped else "")
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;color:#1e1b2e;max-width:760px">
<div style="font-size:20px;font-weight:600;color:#4a1a6b">Dash Pulse · failed transactions</div>
<p style="font-size:15px;margin:12px 0 18px">{len(rows)} new failed transaction{'s' if len(rows) != 1 else ''}
worth {naira(total)} in total.</p>
{''.join(block(r) for r in shown)}
{f'<p style="color:#6b6880">…and {more} more. Open the dashboard to see all of them.</p>' if more else ''}
{note}
{f'<p style="font-size:13px;color:#6b6880;margin-top:16px">Dashboard: <a href="{escape(link)}">{escape(link)}</a></p>' if link else ''}
</div>"""


def subject(rows):
    if len(rows) == 1:
        r = rows[0]
        reason, _ = classify(r["message"])
        return f"Failed: {KINDS.get(r['kind'], r['kind'])} {naira(r['amount'])} · {reason}"
    return f"{len(rows)} failed transactions · {naira(sum(float(r['amount'] or 0) for r in rows))}"


def run_once(dry_run=False):
    recipients = settings.PULSE_FAILURE_EMAILS
    now = lagos_now()
    if not FailureNotice.objects.exists():
        rows = recent_failures(now)
        remember(rows)
        logger.info("Failure mail started: %s earlier failures marked as already seen", len(rows))
        return 0
    fresh = new_failures(now)
    rows, skipped = split(fresh)
    if not rows:
        remember(skipped)
        return 0
    if dry_run:
        print(subject(rows))
        for r in rows:
            print(f"  {r['at']:%H:%M:%S} {r['kind']} {naira(r['amount'])} {classify(r['message'])[0]}")
        return len(rows)
    if not recipients:
        raise mailer.MailError("No recipients. Set PULSE_FAILURE_EMAILS in backend/.env.")
    mailer.send(recipients, subject(rows), email(rows, len(skipped)))
    remember(fresh)
    logger.info("Failure mail sent: %s failures to %s", len(rows), ", ".join(recipients))
    return len(rows)
