from datetime import date, datetime, timedelta
from math import ceil

from django.core.cache import cache
from django.db import DatabaseError
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_GET

from . import banks as bank_names
from .auth import explorer_required
from .export import MAX_ROWS, excel_response, wants_excel
from .live import KINDS
from .report_data import SIDES
from .queries import (FUNNEL_DAYS, LEGACY, ONBOARDING, OUTCOME_SQL, PAYMENTS, PHASE_LABELS, WAT, WEBHOOKS, fetch,
                      lagos_now, machine_lagos_now)
from .reasons import REASON_SQL, classify

ACCOUNTS = "`dashmfb-cba-mcs`.accounts"
PAGE_SIZE = 50
RANGE_DAYS = {"transactions": 31, "money_in": 31, "people": 366}
RANGE_CACHE_SECONDS = 300
STATUSES = {"SUCCESS", "FAILED", "REVERSED", "PENDING"}
OUTCOME_LABELS = {"SUCCESS": "Successful", "FAILED": "Failed", "REVERSED": "Reversed", "PENDING": "Pending"}
TX_COLUMNS = [
    ("Time", "at"),
    ("Last updated", "updated"),
    ("Type", "type"),
    ("Amount (NGN)", "amount"),
    ("Status", "status"),
    ("Failure reason", "reason"),
    ("Who caused it", "side"),
    ("Customer name", "customer_name"),
    ("Customer account", "account"),
    ("Customer phone", "customer_phone"),
    ("Customer email", "customer_email"),
    ("Beneficiary name", "beneficiary"),
    ("Beneficiary account", "beneficiary_account"),
    ("Receiving bank", "bank"),
    ("Bank code", "bank_code"),
    ("Narration", "narration"),
    ("Payment reference", "reference"),
    ("Core banking reference", "cba_reference"),
    ("Provider reference", "provider_reference"),
    ("NIP session ID", "session_id"),
    ("Provider", "provider"),
    ("Payment status (core banking)", "payment_status"),
    ("Payment response code", "payment_code"),
    ("Requery count", "requery_count"),
    ("Core banking response", "cba_ok"),
    ("Core banking message", "cba_message"),
    ("Provider response code", "provider_code"),
    ("Provider message", "provider_message"),
    ("Reversal message", "reversal_message"),
    ("Reversed at", "reversed_at"),
]
PEOPLE_COLUMNS = [
    ("Name", "name"),
    ("Account number", "account"),
    ("Account status", "status"),
    ("Email", "email"),
    ("Phone", "phone"),
    ("Started signing up", "started"),
    ("Account opened", "opened"),
    ("Minutes to open", "minutes_to_open"),
    ("Where they are", "stage"),
]
MONEY_IN_COLUMNS = [
    ("Time", "at"),
    ("Account number", "account"),
    ("Account name", "name"),
    ("Amount (NGN)", "amount"),
    ("Narration", "narration"),
    ("Provider reference", "ref"),
]
ONBOARDING_COLUMNS = [
    ("Name", "name"),
    ("Email", "email"),
    ("Phone", "phone"),
    ("Started", "started"),
    ("Last activity", "last_activity"),
    ("Waiting (hours)", "waiting_hours"),
    ("Next step", "next_step"),
]
HISTORY_COLUMNS = [
    ("Period start", "start"),
    ("Period end", "end"),
    ("Started signing up", "signups"),
    ("Of those, have an account", "finished"),
    ("Accounts opened", "opened"),
    ("Share finished", "finished_share"),
]


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return lagos_now().date()


class RangeTooLong(Exception):
    pass


def parse_span(g, max_days):
    day = parse_day(g.get("date"))
    try:
        until = max(date.fromisoformat(g.get("until")), day)
    except (TypeError, ValueError):
        return day, day
    if (until - day).days >= max_days:
        raise RangeTooLong(max_days)
    return day, until


def span_name(day, until):
    return f"{day}" if until == day else f"{day}_to_{until}"


def too_many_rows(total):
    return HttpResponse(f"This list has {total:,} rows, more than the {MAX_ROWS:,} an Excel download can hold. "
                        "Pick a shorter date range or add a filter, then download again.",
                        status=400, content_type="text/plain; charset=utf-8")


def parse_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def iso(value):
    return value.isoformat() if value else None


def utc_to_lagos(value):
    return (value + WAT).isoformat() if value else None


def paged(rows, request):
    pages = max(ceil(len(rows) / PAGE_SIZE), 1)
    page = min(max(parse_int(request.GET.get("page"), 1), 1), pages)
    first = (page - 1) * PAGE_SIZE
    return {"total": len(rows), "page": page, "pages": pages, "items": rows[first:first + PAGE_SIZE]}


def unavailable(view):
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except DatabaseError:
            return JsonResponse({"error": "unavailable"}, status=503)
        except RangeTooLong as e:
            days = e.args[0]
            return JsonResponse({"error": f"Pick {days} days or fewer.", "max_days": days}, status=400)

    return wrapped


DETAIL_SQL = """,
               l.UPDATED AS updated, l.NARRATION AS narration, l.BENEFICIARY_BANK_CODE AS bank_code,
               COALESCE(l.CBA_REFERENCE, p.cba_reference) AS cba_reference,
               l.PROVIDER_REFERENCE AS provider_reference, p.session_id AS session_id,
               COALESCE(l.PROVIDER, p.provider) AS provider, p.status AS payment_status,
               p.response_code AS payment_code, p.requery_count AS requery_count,
               l.CBA_RESPONSE_CODE AS cba_ok, l.CBA_MESSAGE AS cba_message,
               l.PROVIDER_RESPONSE_CODE AS provider_code, l.PROVIDER_RESPONSE_MESSAGE AS provider_message,
               l.REVERSAL_RESPONSE_MESSAGE AS reversal_message, l.REVERSAL_DATETIME AS reversed_at"""
DETAIL_KEYS = ["narration", "bank_code", "cba_reference", "provider_reference", "session_id", "provider",
               "payment_status", "payment_code", "requery_count", "cba_ok", "cba_message", "provider_code",
               "provider_message", "reversal_message"]


def span_rows(day, until, detail=False):
    key = f"explore:tx:{day}:{until}"
    keep = not detail and until < machine_lagos_now().date()
    if keep and (found := cache.get(key)) is not None:
        return found
    start = datetime.combine(day, datetime.min.time())
    end = datetime.combine(until, datetime.min.time()) + timedelta(days=1)
    rows = fetch(f"""
        SELECT l.ID AS id, l.CREATED AS created, l.TRANSACTION_TYPE AS kind, l.AMOUNT AS amount,
               l.ACCOUNT_NUMBER AS account, l.BENEFICIARY_BANK_NAME AS bank, l.BENEFICIARY_NAME AS beneficiary,
               l.PAYMENT_REFERENCE AS reference, l.BENEFICIARY_ACCOUNT AS beneficiary_account,
               p.source_account_name AS sender,
               {OUTCOME_SQL} AS outcome, {REASON_SQL} AS message{DETAIL_SQL if detail else ""}
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(start)s AND l.CREATED < %(end)s
    """, {"start": start, "end": end})
    out = []
    for r in rows:
        reason, reason_kind = classify(r["message"]) if r["outcome"] == "FAILED" else (None, None)
        row = {
            "id": int(r["id"]),
            "at": iso(r["created"]),
            "kind": r["kind"],
            "amount": float(r["amount"] or 0),
            "account": r["account"],
            "beneficiary": r["beneficiary"],
            "beneficiary_account": r["beneficiary_account"],
            "sender": r["sender"],
            "bank": bank_names.canonical(r["bank"]) if r["bank"] else None,
            "reference": r["reference"],
            "outcome": r["outcome"],
            "reason": reason,
            "reason_kind": reason_kind,
            "words": words(" ".join(str(v) for v in (
                r["reference"], r["account"], r["beneficiary"], r["beneficiary_account"], r["sender"]) if v)),
        }
        if detail:
            row.update({k: r[k] for k in DETAIL_KEYS})
            row["updated"] = iso(r["updated"])
            row["reversed_at"] = iso(r["reversed_at"])
        out.append(row)
    if keep:
        cache.set(key, out, RANGE_CACHE_SECONDS)
    return out


def words(text):
    return " ".join(text.lower().split())


def matches(row, q):
    if q["status"] and row["outcome"] != q["status"]:
        return False
    if q["kinds"] and row["kind"] not in q["kinds"]:
        return False
    if q["bank"] and bank_names.key(row["bank"]) != bank_names.key(q["bank"]):
        return False
    if q["reason"] and row["reason"] != q["reason"]:
        return False
    if q["hour"] is not None and datetime.fromisoformat(row["at"]).hour != q["hour"]:
        return False
    if q["search"] and not all(w in row["words"] for w in q["search"].split()):
        return False
    return True


@require_GET
@explorer_required
@unavailable
def transactions(request):
    g = request.GET
    day, until = parse_span(g, RANGE_DAYS["transactions"])
    status = (g.get("status") or "").upper()
    q = {
        "status": status if status in STATUSES else None,
        "kinds": {k for k in (g.get("kinds") or "").split(",") if k},
        "bank": g.get("bank") or None,
        "reason": g.get("reason") or None,
        "hour": parse_int(g.get("hour")),
        "search": words(g.get("search") or ""),
    }
    all_rows = span_rows(day, until, detail=wants_excel(request))
    rows = sorted((r for r in all_rows if matches(r, q)), key=lambda r: (r["at"], r["id"]), reverse=True)
    rows = [{k: v for k, v in r.items() if k != "words"} for r in rows]

    if wants_excel(request):
        if len(rows) > MAX_ROWS:
            return too_many_rows(len(rows))
        numbers = sorted({r["account"] for r in rows if r["account"]})
        contacts = {}
        for i in range(0, len(numbers), 1000):
            for a in fetch(f"""
                SELECT account_number, account_name, customer_phone_number AS phone, customer_email_address AS email
                FROM {ACCOUNTS} WHERE account_number IN %(n)s
            """, {"n": numbers[i:i + 1000]}):
                contacts[a["account_number"]] = a
        return excel_response(f"Transactions_{span_name(day, until)}", TX_COLUMNS, [{
            **r,
            "type": KINDS.get(r["kind"], r["kind"]),
            "status": OUTCOME_LABELS[r["outcome"]],
            "side": SIDES.get(r["reason_kind"]),
            "customer_name": r["sender"] or contacts.get(r["account"], {}).get("account_name"),
            "customer_phone": contacts.get(r["account"], {}).get("phone"),
            "customer_email": contacts.get(r["account"], {}).get("email"),
        } for r in rows])
    summary = {s.lower(): 0 for s in STATUSES}
    reasons = {}
    for r in rows:
        summary[r["outcome"].lower()] += 1
        if r["reason"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    summary["value"] = round(sum(r["amount"] for r in rows if r["outcome"] == "SUCCESS"), 2)

    return JsonResponse({
        "date": day.isoformat(),
        "until": until.isoformat() if until != day else None,
        "filters": {k: sorted(v) if isinstance(v, set) else v for k, v in q.items() if v not in (None, "", set())},
        "summary": summary,
        "reasons": sorted(({"reason": k, "count": v} for k, v in reasons.items()), key=lambda r: -r["count"]),
        "kinds": sorted({r["kind"] for r in all_rows if r["kind"]}),
        **paged(rows, request),
    })


@require_GET
@explorer_required
@unavailable
def transaction(request, tx_id):
    rows = fetch(f"""
        SELECT l.*, {OUTCOME_SQL} AS outcome,
               p.id AS p_id, p.status AS p_status, p.transfer_type AS p_transfer_type, p.provider AS p_provider,
               p.response_code AS p_response_code, p.requery_count AS p_requery_count,
               p.cba_reference AS p_cba_reference, p.session_id AS p_session_id,
               p.source_account_name AS p_source_account_name, p.beneficiary_name AS p_beneficiary_name,
               p.narration AS p_narration, p.created_at AS p_created_at, p.updated_at AS p_updated_at
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.ID = %(id)s
    """, {"id": tx_id})
    if not rows:
        return JsonResponse({"error": "not_found"}, status=404)
    r = rows[0]
    message = r.get("PROVIDER_RESPONSE_MESSAGE") or r.get("CBA_MESSAGE")
    reason, reason_kind = classify(message) if r["outcome"] == "FAILED" else (None, None)

    customer = None
    if r.get("ACCOUNT_NUMBER"):
        found = fetch(f"""
            SELECT account_name, customer_email_address, customer_phone_number, account_kyc_tier_code,
                   status, created_at
            FROM {ACCOUNTS} WHERE account_number = %(acct)s LIMIT 1
        """, {"acct": r["ACCOUNT_NUMBER"]})
        if found:
            a = found[0]
            customer = {
                "name": a["account_name"],
                "email": a["customer_email_address"],
                "phone": a["customer_phone_number"],
                "kyc_tier": a["account_kyc_tier_code"],
                "status": a["status"],
                "opened": utc_to_lagos(a["created_at"]),
            }

    created = r.get("CREATED")
    history = []
    if r.get("ACCOUNT_NUMBER") and created:
        start = datetime.combine(created.date(), datetime.min.time())
        for h in fetch(f"""
            SELECT l.ID AS id, l.CREATED AS created, l.TRANSACTION_TYPE AS kind, l.AMOUNT AS amount,
                   {OUTCOME_SQL} AS outcome, {REASON_SQL} AS message
            FROM {LEGACY} l
            LEFT JOIN {PAYMENTS} p
                   ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
            WHERE l.ACCOUNT_NUMBER = %(acct)s AND l.CREATED >= %(start)s AND l.CREATED < %(end)s
            ORDER BY l.CREATED DESC, l.ID DESC
            LIMIT 30
        """, {"acct": r["ACCOUNT_NUMBER"], "start": start, "end": start + timedelta(days=1)}):
            history.append({
                "id": int(h["id"]),
                "at": iso(h["created"]),
                "kind": h["kind"],
                "amount": float(h["amount"] or 0),
                "outcome": h["outcome"],
                "reason": classify(h["message"])[0] if h["outcome"] == "FAILED" else None,
            })

    timeline = [{"at": iso(created), "label": "Customer started the transaction in the app"}]
    if r.get("p_created_at"):
        timeline.append({"at": utc_to_lagos(r["p_created_at"]), "label": "Sent to core banking for payment"})
    if r["outcome"] == "FAILED":
        timeline.append({"at": iso(r.get("UPDATED")), "label": f"Failed: {reason}"})
    elif r["outcome"] == "PENDING":
        timeline.append({"at": iso(r.get("UPDATED")), "label": "No final answer recorded yet"})
    elif r["outcome"] == "REVERSED":
        timeline.append({"at": utc_to_lagos(r.get("p_updated_at")), "label": "Debited, then reversed (refunded)"})
    else:
        timeline.append({"at": utc_to_lagos(r.get("p_updated_at")) or iso(r.get("UPDATED")), "label": "Completed successfully"})
    if r.get("REVERSAL_DATETIME"):
        timeline.append({"at": iso(r["REVERSAL_DATETIME"]), "label": "Reversal recorded"})

    return JsonResponse({
        "id": int(r["ID"]),
        "outcome": r["outcome"],
        "reason": reason,
        "reason_kind": reason_kind,
        "kind": r.get("TRANSACTION_TYPE"),
        "amount": float(r.get("AMOUNT") or 0),
        "narration": r.get("NARRATION") or r.get("p_narration"),
        "created": iso(created),
        "updated": iso(r.get("UPDATED")),
        "sender": {
            "account": r.get("ACCOUNT_NUMBER"),
            "name": r.get("p_source_account_name") or (customer or {}).get("name"),
        },
        "beneficiary": {
            "name": r.get("BENEFICIARY_NAME") or r.get("p_beneficiary_name"),
            "account": r.get("BENEFICIARY_ACCOUNT"),
            "bank": bank_names.canonical(r["BENEFICIARY_BANK_NAME"]) if r.get("BENEFICIARY_BANK_NAME") else None,
            "bank_code": r.get("BENEFICIARY_BANK_CODE"),
        },
        "references": {
            "payment": r.get("PAYMENT_REFERENCE"),
            "core_banking": r.get("CBA_REFERENCE") or r.get("p_cba_reference"),
            "provider": r.get("PROVIDER_REFERENCE"),
            "nip_session": r.get("p_session_id"),
        },
        "responses": {
            "provider": r.get("PROVIDER") or r.get("p_provider"),
            "core_banking_ok": r.get("CBA_RESPONSE_CODE"),
            "core_banking_message": r.get("CBA_MESSAGE"),
            "provider_code": r.get("PROVIDER_RESPONSE_CODE"),
            "provider_message": r.get("PROVIDER_RESPONSE_MESSAGE"),
            "payment_status": r.get("p_status"),
            "payment_code": r.get("p_response_code"),
            "requery_count": r.get("p_requery_count"),
            "reversal": r.get("REVERSAL_RESPONSE"),
            "reversal_message": r.get("REVERSAL_RESPONSE_MESSAGE"),
        },
        "timeline": [t for t in timeline if t["at"]],
        "customer": customer,
        "same_day": history,
    })


@require_GET
@explorer_required
@unavailable
def onboarding(request):
    g = request.GET
    phase = g.get("phase") if g.get("phase") in PHASE_LABELS else None
    if not phase:
        return JsonResponse({"error": "unknown_phase"}, status=400)
    now = lagos_now()
    scope = "today" if g.get("scope") == "today" else "30d"
    since = now.replace(hour=0, minute=0, second=0) if scope == "today" else now - timedelta(days=FUNNEL_DAYS)
    search = (g.get("search") or "").strip().lower()
    rows = fetch(f"""
        SELECT ID AS id, FIRSTNAME AS first, LASTNAME AS last, EMAIL AS email, PHONE_NUMBER AS phone,
               DATE_CREATED AS started, DATE_UPDATED AS updated, NEXT_ONBOARDING_PHASE AS next_phase
        FROM {ONBOARDING}
        WHERE ONBOARDING_PHASE = %(phase)s AND DATE_CREATED >= %(since)s AND DATE_CREATED < %(now)s
        ORDER BY ID DESC
    """, {"phase": phase, "since": since, "now": now})
    items = []
    for r in rows:
        name = " ".join(x for x in (r["first"], r["last"]) if x) or None
        item = {
            "id": int(r["id"]),
            "name": name,
            "email": r["email"],
            "phone": r["phone"],
            "started": iso(r["started"]),
            "last_activity": iso(r["updated"]),
            "waiting_hours": round(max((now - (r["updated"] or r["started"])).total_seconds(), 0) / 3600, 1),
            "next_step": r["next_phase"],
        }
        if search and search not in f"{name} {r['email']} {r['phone']}".lower():
            continue
        items.append(item)
    if wants_excel(request):
        return excel_response(f"Stuck_{phase}_{scope}", ONBOARDING_COLUMNS, items)
    return JsonResponse({"phase": phase, "label": PHASE_LABELS[phase], "scope": scope, **paged(items, request)})


STAGE_FILTERS = {
    "opened": "o.ACCOUNT_OPENED_DATE IS NOT NULL",
    "not_opened": "o.ACCOUNT_OPENED_DATE IS NULL",
}


def stage_label(phase, opened):
    if opened or phase == "ACCOUNT_CREATED":
        return "Account opened"
    return PHASE_LABELS.get(phase, phase or "Unknown")


@require_GET
@explorer_required
@unavailable
def people(request):
    g = request.GET
    mode = "signups" if g.get("mode") == "signups" else "opened"
    all_time = mode == "opened" and g.get("date") == "all"
    day, until = (None, None) if all_time else parse_span(g, RANGE_DAYS["people"])
    column = "o.DATE_CREATED" if mode == "signups" else "o.ACCOUNT_OPENED_DATE"

    where, params = [], {}
    if all_time:
        where.append("(o.ONBOARDING_PHASE = 'ACCOUNT_CREATED' OR o.ACCOUNT_OPENED_DATE IS NOT NULL)")
        column = "COALESCE(o.ACCOUNT_OPENED_DATE, o.DATE_UPDATED, o.DATE_CREATED)"
    else:
        start = datetime.combine(day, datetime.min.time())
        where.append(f"{column} >= %(start)s AND {column} < %(end)s")
        params.update(start=start, end=datetime.combine(until, datetime.min.time()) + timedelta(days=1))
    stage = g.get("stage") if mode == "signups" and g.get("stage") in STAGE_FILTERS else None
    if stage:
        where.append(STAGE_FILTERS[stage])

    for n, word in enumerate((g.get("search") or "").lower().split()[:5]):
        params[f"w{n}"] = f"%{word}%"
        clause = (f"LOWER(CONCAT_WS(' ', o.FIRSTNAME, o.LASTNAME, o.EMAIL, o.PHONE_NUMBER)) LIKE %(w{n})s")
        if word.isdigit() and len(word) >= 4:
            emails = [r["email"] for r in fetch(f"""
                SELECT LOWER(TRIM(customer_email_address)) AS email FROM {ACCOUNTS}
                WHERE account_number LIKE %(w)s LIMIT 200
            """, {"w": f"%{word}%"}) if r["email"]]
            if emails:
                params[f"e{n}"] = emails
                clause = f"({clause} OR LOWER(TRIM(o.EMAIL)) IN %(e{n})s)"
        where.append(clause)

    sql_where = " AND ".join(where)
    total = int(fetch(f"SELECT COUNT(*) AS n FROM {ONBOARDING} o WHERE {sql_where}", params)[0]["n"])
    pages = max(ceil(total / PAGE_SIZE), 1)
    page = min(max(parse_int(g.get("page"), 1), 1), pages)
    download = wants_excel(request)
    if download and total > MAX_ROWS:
        return too_many_rows(total)
    limit, offset = (MAX_ROWS, 0) if download else (PAGE_SIZE, (page - 1) * PAGE_SIZE)
    rows = fetch(f"""
        SELECT o.ID AS id, o.FIRSTNAME AS first, o.LASTNAME AS last, o.EMAIL AS email, o.PHONE_NUMBER AS phone,
               o.DATE_CREATED AS started, o.ACCOUNT_OPENED_DATE AS opened, o.ONBOARDING_PHASE AS phase
        FROM {ONBOARDING} o
        WHERE {sql_where}
        ORDER BY {column} DESC, o.ID DESC
        LIMIT {limit} OFFSET {offset}
    """, params)

    emails = sorted({r["email"].strip().lower() for r in rows if r["email"]})
    found = {}
    for i in range(0, len(emails), 1000):
        for a in fetch(f"""
            SELECT LOWER(TRIM(customer_email_address)) AS email, account_number, status
            FROM {ACCOUNTS}
            WHERE LOWER(TRIM(customer_email_address)) IN %(emails)s
            ORDER BY created_at
        """, {"emails": emails[i:i + 1000]}):
            found[a["email"]] = a

    items = []
    for r in rows:
        a = found.get((r["email"] or "").strip().lower(), {})
        minutes = None
        if r["started"] and r["opened"] and r["opened"] >= r["started"]:
            minutes = round((r["opened"] - r["started"]).total_seconds() / 60)
        items.append({
            "id": int(r["id"]),
            "name": " ".join(x for x in (r["first"], r["last"]) if x) or None,
            "account": a.get("account_number"),
            "status": a.get("status"),
            "email": r["email"],
            "phone": r["phone"],
            "started": iso(r["started"]),
            "opened": iso(r["opened"]),
            "minutes_to_open": minutes,
            "stage": stage_label(r["phase"], r["opened"]),
            "done": bool(r["opened"]),
        })
    if download:
        span = "All-accounts" if all_time else span_name(day, until)
        what = "Sign-ups" if mode == "signups" else "Accounts-opened"
        return excel_response(f"{what}_{span}", PEOPLE_COLUMNS, items)
    return JsonResponse({
        "mode": mode,
        "date": "all" if all_time else day.isoformat(),
        "until": until.isoformat() if until and until != day else None,
        "stage": stage,
        "total": total,
        "page": page,
        "pages": pages,
        "items": items,
    })


@require_GET
@explorer_required
@unavailable
def money_in(request):
    g = request.GET
    day, until = parse_span(g, RANGE_DAYS["money_in"])
    start = datetime.combine(day, datetime.min.time()) - WAT
    params = {"start": start, "end": datetime.combine(until, datetime.min.time()) - WAT + timedelta(days=1)}
    where = ["created_at >= %(start)s", "created_at < %(end)s",
             "JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.drCr')) = 'CR'",
             "JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.service')) = 'INWARD'",
             f"account_number IN (SELECT account_number FROM {ACCOUNTS})"]
    for n, word in enumerate((g.get("search") or "").lower().split()[:5]):
        params[f"w{n}"] = f"%{word}%"
        where.append(f"LOWER(CONCAT_WS(' ', account_number, provider_ref, "
                     f"JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.narration')))) LIKE %(w{n})s")
    sql_where = " AND ".join(where)
    base = f"""
        SELECT provider_ref, MIN(created_at) AS at, MAX(account_number) AS account,
               MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.amount')) AS DECIMAL(18,2))) AS amount,
               MAX(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.narration'))) AS narration
        FROM {WEBHOOKS} WHERE {sql_where} GROUP BY provider_ref
    """
    summary = fetch(f"SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS value FROM ({base}) t", params)[0]
    total = int(summary["n"])
    pages = max(ceil(total / PAGE_SIZE), 1)
    page = min(max(parse_int(g.get("page"), 1), 1), pages)
    download = wants_excel(request)
    if download and total > MAX_ROWS:
        return too_many_rows(total)
    limit, offset = (MAX_ROWS, 0) if download else (PAGE_SIZE, (page - 1) * PAGE_SIZE)
    rows = fetch(f"{base} ORDER BY at DESC LIMIT {limit} OFFSET {offset}", params)
    numbers = sorted({r["account"] for r in rows if r["account"]})
    names = {}
    for i in range(0, len(numbers), 1000):
        names.update({a["account_number"]: a["account_name"] for a in fetch(
            f"SELECT account_number, account_name FROM {ACCOUNTS} WHERE account_number IN %(n)s",
            {"n": numbers[i:i + 1000]})})
    items = [{
        "ref": r["provider_ref"],
        "at": utc_to_lagos(r["at"]),
        "account": r["account"],
        "name": names.get(r["account"]),
        "amount": float(r["amount"] or 0),
        "narration": r["narration"],
    } for r in rows]
    if download:
        return excel_response(f"Money-in_{span_name(day, until)}", MONEY_IN_COLUMNS, items)
    return JsonResponse({
        "date": day.isoformat(),
        "until": until.isoformat() if until != day else None,
        "total": total,
        "value": float(summary["value"]),
        "page": page,
        "pages": pages,
        "items": items,
    })


HISTORY = {"day": 30, "week": 12, "month": 12}


def period_start(d, by):
    if by == "week":
        return d - timedelta(days=d.weekday())
    if by == "month":
        return d.replace(day=1)
    return d


def period_end(start, by):
    if by == "week":
        return start + timedelta(days=6)
    if by == "month":
        following = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return following - timedelta(days=1)
    return start


def history_periods(today, by):
    periods, cursor = [], period_start(today, by)
    for _ in range(HISTORY[by]):
        periods.append(cursor)
        cursor = period_start(cursor - timedelta(days=1), by)
    return periods


def build_signup_history(today, by):
    periods = history_periods(today, by)
    since = datetime.combine(periods[-1], datetime.min.time())
    started = fetch(f"""
        SELECT DATE(DATE_CREATED) AS d, COUNT(*) AS n, SUM(ACCOUNT_OPENED_DATE IS NOT NULL) AS finished
        FROM {ONBOARDING} WHERE DATE_CREATED >= %(since)s GROUP BY d
    """, {"since": since})
    opened = fetch(f"""
        SELECT DATE(ACCOUNT_OPENED_DATE) AS d, COUNT(*) AS n
        FROM {ONBOARDING} WHERE ACCOUNT_OPENED_DATE >= %(since)s GROUP BY d
    """, {"since": since})
    rows = {p: {"signups": 0, "finished": 0, "opened": 0} for p in periods}
    for r in started:
        key = period_start(r["d"], by)
        if key in rows:
            rows[key]["signups"] += int(r["n"])
            rows[key]["finished"] += int(r["finished"] or 0)
    for r in opened:
        key = period_start(r["d"], by)
        if key in rows:
            rows[key]["opened"] += int(r["n"])
    return [{
        "start": p.isoformat(),
        "end": min(period_end(p, by), today).isoformat(),
        "current": period_end(p, by) >= today,
        **rows[p],
        "finished_share": round(rows[p]["finished"] / rows[p]["signups"], 4) if rows[p]["signups"] else None,
    } for p in periods]


@require_GET
@explorer_required
@unavailable
def signup_history(request):
    by = request.GET.get("by") if request.GET.get("by") in HISTORY else "day"
    items = build_signup_history(lagos_now().date(), by)
    if wants_excel(request):
        return excel_response(f"Sign-up-history_by_{by}", HISTORY_COLUMNS, items)
    return JsonResponse({"by": by, "items": items})
