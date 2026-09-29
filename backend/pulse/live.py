from datetime import timedelta

from . import banks as bank_names
from .queries import LEGACY, OUTCOME_SQL, PAYMENTS, fetch, lagos_now
from .reasons import REASON_SQL
from .reasons import classify as classify_reason

FETCH_ROWS = 200
FEED_ROWS = 14
WINDOW_MINUTES = 15

KINDS = {
    "INTER": "Transfer",
    "INTRA": "Transfer within Dash",
    "Airtime": "Airtime",
    "Data Bundle": "Data",
    "Betting & Lottery": "Betting",
    "Utilities": "Electricity & utilities",
    "Cable TV": "Cable TV",
    "Transport and Toll Payment": "Transport & tolls",
}


def build_live():
    now = lagos_now()
    rows = fetch(f"""
        SELECT l.ID AS id,
               l.TRANSACTION_TYPE AS kind,
               l.AMOUNT AS amount,
               l.CREATED AS created,
               l.BENEFICIARY_BANK_NAME AS bank,
               {OUTCOME_SQL} AS outcome,
               {REASON_SQL} AS reason
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        ORDER BY l.ID DESC
        LIMIT {FETCH_ROWS}
    """, {})

    since = now - timedelta(minutes=WINDOW_MINUTES)
    window = {"count": 0, "success": 0, "failed": 0, "reversed": 0, "pending": 0}
    feed = []
    for r in rows:
        created = r["created"]
        outcome = r["outcome"]
        if created and since <= created <= now:
            window["count"] += 1
            window[outcome.lower()] += 1
        if len(feed) < FEED_ROWS:
            kind = r["kind"] or ""
            feed.append({
                "id": int(r["id"]),
                "kind": KINDS.get(kind, kind or "Transaction"),
                "bank": bank_names.canonical(r["bank"]) if kind == "INTER" else None,
                "amount": float(r["amount"] or 0),
                "outcome": outcome,
                "reason": classify_reason(r["reason"])[0] if outcome == "FAILED" else None,
                "at": created.isoformat() if created else None,
            })

    last = next((r["created"] for r in rows if r["created"]), None)
    return {
        "now": now.isoformat(),
        "last_at": last.isoformat() if last else None,
        "window_minutes": WINDOW_MINUTES,
        "window": window,
        "feed": feed,
    }
