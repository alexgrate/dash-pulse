from datetime import date, datetime, timedelta
from math import ceil

from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from . import banks as bank_names
from .auth import explorer_required
from .queries import FUNNEL_DAYS, LEGACY, ONBOARDING, OUTCOME_SQL, PAYMENTS, PHASE_LABELS, WAT, fetch, lagos_now
from .reasons import REASON_SQL, classify

ACCOUNTS = "`dashmfb-cba-mcs`.accounts"
PAGE_SIZE = 50
STATUSES = {"SUCCESS", "FAILED", "REVERSED", "PENDING"}


def parse_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return lagos_now().date()


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

    return wrapped


def day_rows(day):
    start = datetime.combine(day, datetime.min.time())
    rows = fetch(f"""
        SELECT l.ID AS id, l.CREATED AS created, l.TRANSACTION_TYPE AS kind, l.AMOUNT AS amount,
               l.ACCOUNT_NUMBER AS account, l.BENEFICIARY_BANK_NAME AS bank, l.BENEFICIARY_NAME AS beneficiary,
               l.PAYMENT_REFERENCE AS reference,
               {OUTCOME_SQL} AS outcome, {REASON_SQL} AS message
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(start)s AND l.CREATED < %(end)s
    """, {"start": start, "end": start + timedelta(days=1)})
    out = []
    for r in rows:
        reason, reason_kind = classify(r["message"]) if r["outcome"] == "FAILED" else (None, None)
        out.append({
            "id": int(r["id"]),
            "at": iso(r["created"]),
            "kind": r["kind"],
            "amount": float(r["amount"] or 0),
            "account": r["account"],
            "beneficiary": r["beneficiary"],
            "bank": bank_names.canonical(r["bank"]) if r["bank"] else None,
            "reference": r["reference"],
            "outcome": r["outcome"],
            "reason": reason,
            "reason_kind": reason_kind,
        })
    return out


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
    if q["search"]:
        haystack = f"{row['reference']} {row['account']} {row['beneficiary']}".lower()
        if q["search"] not in haystack:
            return False
    return True


@require_GET
@explorer_required
@unavailable
def transactions(request):
    g = request.GET
    day = parse_day(g.get("date"))
    status = (g.get("status") or "").upper()
    q = {
        "status": status if status in STATUSES else None,
        "kinds": {k for k in (g.get("kinds") or "").split(",") if k},
        "bank": g.get("bank") or None,
        "reason": g.get("reason") or None,
        "hour": parse_int(g.get("hour")),
        "search": (g.get("search") or "").strip().lower(),
    }
    all_rows = day_rows(day)
    rows = sorted((r for r in all_rows if matches(r, q)), key=lambda r: (r["at"], r["id"]), reverse=True)

    summary = {s.lower(): 0 for s in STATUSES}
    reasons = {}
    for r in rows:
        summary[r["outcome"].lower()] += 1
        if r["reason"]:
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
    summary["value"] = round(sum(r["amount"] for r in rows if r["outcome"] == "SUCCESS"), 2)

    return JsonResponse({
        "date": day.isoformat(),
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
               p.id AS p_id, p.status AS p_status, p.transfer_type AS p_transfer_type,
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
            "provider": r.get("PROVIDER"),
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
    return JsonResponse({"phase": phase, "label": PHASE_LABELS[phase], "scope": scope, **paged(items, request)})
