"""
Read-only analytics queries against the bank database.

Every window is expressed in naive Lagos wall-clock time. Tables that store
UTC (cba-mcs, billspayment, notification) get their window shifted back by
one hour before querying. See DATA_NOTES.md.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db import connections

from . import banks as bank_names
from .geo import CITY_COORDS, NIGERIA_BOUNDS, nearest_city
from .reasons import REASON_SQL
from .reasons import classify as classify_reason
from .reasons import group as group_reasons

LAGOS = ZoneInfo("Africa/Lagos")
WAT = timedelta(hours=1)

LEGACY = "`dashmfb-mcs`.DashMFB_Transactions"
PAYMENTS = "`dashmfb-cba-mcs`.payment_transactions"
LOGINS = "`dashmfb-mcs`.UM_LOGIN_TRAIL"
ONBOARDING = "`dashmfb-mcs`.DashMFB_UM_ONBOARDING_PROCESS"
REWARDS = "`dashmfb-cba-mcs`.quest_reward_transactions"
LIVENESS = "`dashmfb-mcs`.LIVENESS_CHECK_LOG"

RECENT_MINUTES = 15
BASELINE_DAYS = 7
ALERT_MIN_SETTLED = 15
ALERT_RATIO = 1.5
ALERT_MIN_GAP = 0.10

FUNNEL_DAYS = 30
MAP_RECENT_MINUTES = 10
MAP_GRID_DEGREES = 0.1
BANK_RECENT_MINUTES = 30

PHASE_ORDER = [
    "EMAIL_VERIFICATION",
    "RESEND_EMAIL_VERIFICATION_LINK",
    "EMAIL_CONFIRMATION",
    "PHONE_VERIFICATION",
    "RESEND_PHONE_OTP",
    "PHONE_OTP_VALIDATED",
    "BVN_VALIDATION",
    "BVN_PHONE_MATCHED",
    "USER_PROFILE_CREATED",
    "LIVENESS_CHECK_DONE",
    "ACCOUNT_CREATED",
]

PHASE_LABELS = {
    "EMAIL_VERIFICATION": "Never verified email",
    "RESEND_EMAIL_VERIFICATION_LINK": "Asked for a new email link",
    "EMAIL_CONFIRMATION": "Confirming email",
    "PHONE_VERIFICATION": "Never verified phone",
    "RESEND_PHONE_OTP": "Asked for a new phone OTP",
    "PHONE_OTP_VALIDATED": "Stopped before BVN",
    "BVN_VALIDATION": "Stuck at BVN check",
    "BVN_PHONE_MATCHED": "Stopped after BVN match",
    "USER_PROFILE_CREATED": "Stopped before face check",
    "LIVENESS_CHECK_DONE": "Face check passed, no account",
}

FUNNEL_STAGES = [
    ("signed_up", "Signed up", "EMAIL_VERIFICATION"),
    ("email", "Email confirmed", "EMAIL_CONFIRMATION"),
    ("phone", "Phone verified", "PHONE_OTP_VALIDATED"),
    ("profile", "Profile created", "USER_PROFILE_CREATED"),
    ("face", "Face check passed", "LIVENESS_CHECK_DONE"),
    ("account", "Account opened", "ACCOUNT_CREATED"),
]

OUTCOME_SQL = """
    CASE
        WHEN p.status = 'REVERSED'         THEN 'REVERSED'
        WHEN p.status = 'SUCCESSFUL'       THEN 'SUCCESS'
        WHEN l.CBA_RESPONSE_CODE = 'false' THEN 'FAILED'
        ELSE 'PENDING'
    END"""

BUCKET_SQL = """
    CASE
        WHEN {col} >= %(today)s         THEN 'today'
        WHEN {col} <  %(yesterday_now)s THEN 'yesterday'
        ELSE 'yesterday_rest'
    END"""

GROUPS = {
    "INTER": "To other banks",
    "INTRA": "Within Dash",
    "Airtime": "Airtime & Data",
    "Data Bundle": "Airtime & Data",
    "Betting & Lottery": "Betting",
}  


def machine_lagos_now():
    return datetime.now(LAGOS).replace(tzinfo=None, microsecond=0)


def lagos_now():
    with connections["bank"].cursor() as cur:
        cur.execute("SELECT UTC_TIMESTAMP()")
        utc = cur.fetchone()[0]
    return (utc + WAT).replace(microsecond=0)


def windows(now):
    today = now.replace(hour=0, minute=0, second=0)
    return {
        "yesterday": today - timedelta(days=1),
        "yesterday_now": now - timedelta(days=1),
        "today": today,
        "now": now,
    }


def as_utc(w):
    return {k: v - WAT for k, v in w.items()}


def fetch(sql, params):
    with connections["bank"].cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def by_bucket(rows, field="n", cast=int):
    out = {"today": 0, "yesterday": 0}
    for r in rows:
        if r["bucket"] in out:
            out[r["bucket"]] = cast(r[field])
    return out


def transactions(w):
    rows = fetch(f"""
        SELECT {BUCKET_SQL.format(col="l.CREATED")} AS bucket,
               l.TRANSACTION_TYPE AS kind,
               {OUTCOME_SQL} AS outcome,
               HOUR(l.CREATED) AS hour,
               COUNT(*) AS n,
               COALESCE(SUM(l.AMOUNT), 0) AS value
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(yesterday)s AND l.CREATED < %(now)s
        GROUP BY bucket, kind, outcome, hour
    """, w)

    blank = {"count": 0, "value": 0.0, "success": 0, "failed": 0, "reversed": 0, "pending": 0}
    totals = {"today": dict(blank), "yesterday": dict(blank)}
    hourly = {"today": [0] * 24, "yesterday": [0] * 24}
    mix = defaultdict(lambda: {"count": 0, "value": 0.0})
    products = defaultdict(lambda: {"count": 0, "failed": 0, "reversed": 0, "pending": 0})

    for r in rows:
        n, outcome = r["n"], r["outcome"]
        hourly["today" if r["bucket"] == "today" else "yesterday"][r["hour"]] += n
        if r["bucket"] == "yesterday_rest":
            continue
        t = totals[r["bucket"]]
        t["count"] += n
        t[outcome.lower()] += n
        if outcome == "SUCCESS":
            t["value"] += float(r["value"])
        if r["bucket"] == "today":
            g = mix[GROUPS.get(r["kind"], "Bills")]
            g["count"] += n
            if outcome == "SUCCESS":
                g["value"] += float(r["value"])
            p = products[r["kind"]]
            p["count"] += n
            if outcome != "SUCCESS":
                p[outcome.lower()] += n

    for t in totals.values():
        settled = t["count"] - t["pending"]
        t["success_rate"] = round(t["success"] / settled, 4) if settled else None

    for p in products.values():
        settled = p["count"] - p["pending"]
        p["failure_rate"] = round(p["failed"] / settled, 4) if settled else None
        p["reversal_rate"] = round(p["reversed"] / settled, 4) if settled else None

    return {
        "totals": totals,
        "hourly": hourly,
        "mix": sorted(({"group": k, **v} for k, v in mix.items()), key=lambda g: -g["count"]),
        "products": sorted(({"kind": k, **v} for k, v in products.items()), key=lambda p: -p["count"]),
    }


def active_users(w):
    return by_bucket(fetch(f"""
        SELECT {BUCKET_SQL.format(col="LOGIN_TIME")} AS bucket, COUNT(DISTINCT USERNAME) AS n
        FROM {LOGINS}
        WHERE LOGIN_TIME >= %(yesterday)s AND LOGIN_TIME < %(now)s
        GROUP BY bucket
    """, w))


def new_accounts(w):
    return by_bucket(fetch(f"""
        SELECT {BUCKET_SQL.format(col="ACCOUNT_OPENED_DATE")} AS bucket, COUNT(*) AS n
        FROM {ONBOARDING}
        WHERE ACCOUNT_OPENED_DATE >= %(yesterday)s AND ACCOUNT_OPENED_DATE < %(now)s
        GROUP BY bucket
    """, w))


def rewards(w_utc):
    rows = fetch(f"""
        SELECT {BUCKET_SQL.format(col="created_at")} AS bucket,
               COUNT(*) AS n, COALESCE(SUM(amount), 0) AS value
        FROM {REWARDS}
        WHERE created_at >= %(yesterday)s AND created_at < %(now)s
        GROUP BY bucket
    """, w_utc)
    count, value = by_bucket(rows), by_bucket(rows, "value", float)
    last = fetch(f"SELECT MAX(created_at) AS last FROM {REWARDS}", {})[0]["last"]
    return {
        **{b: {"count": count[b], "value": value[b]} for b in ("today", "yesterday")},
        "last_paid_at": (last + WAT).isoformat() if last else None,
    }


def failure_rates(now):
    rows = fetch(f"""
        SELECT bucket,
               COUNT(*) AS n,
               SUM(outcome = 'FAILED') AS failed,
               SUM(outcome = 'PENDING') AS pending
        FROM (
            SELECT CASE WHEN l.CREATED >= %(recent)s THEN 'recent' ELSE 'baseline' END AS bucket,
                   {OUTCOME_SQL} AS outcome
            FROM {LEGACY} l
            LEFT JOIN {PAYMENTS} p
                   ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
            WHERE l.CREATED >= %(since)s AND l.CREATED < %(now)s
        ) t
        GROUP BY bucket
    """, {
        "since": now - timedelta(days=BASELINE_DAYS),
        "recent": now - timedelta(minutes=RECENT_MINUTES),
        "now": now,
    })

    out = {}
    for bucket in ("recent", "baseline"):
        r = next((r for r in rows if r["bucket"] == bucket), None)
        n, failed, pending = (int(r["n"]), int(r["failed"]), int(r["pending"])) if r else (0, 0, 0)
        settled = n - pending
        out[bucket] = {
            "count": n,
            "failed": failed,
            "settled": settled,
            "failure_rate": round(failed / settled, 4) if settled else None,
        }
    return out


def failure_reasons(w, now):
    rows = fetch(f"""
        SELECT {REASON_SQL} AS reason,
               COUNT(*) AS today,
               SUM(CREATED >= %(recent)s) AS recent
        FROM {LEGACY}
        WHERE CBA_RESPONSE_CODE = 'false'
          AND CREATED >= LEAST(%(today)s, %(recent)s) AND CREATED < %(now)s
        GROUP BY reason
    """, {**w, "recent": now - timedelta(minutes=RECENT_MINUTES)})
    return sorted(group_reasons(rows, ["today", "recent"]), key=lambda r: -r["today"])[:6]


def liveness(w):
    rows = fetch(f"""
        SELECT STATUS AS status, COUNT(*) AS n
        FROM {LIVENESS}
        WHERE DATE_CREATED >= %(today)s AND DATE_CREATED < %(now)s
        GROUP BY STATUS
    """, w)
    counts = {r["status"]: int(r["n"]) for r in rows}
    passed, failed = counts.get("PASSED", 0), counts.get("LOW_SCORE", 0)
    total = passed + failed
    return {"passed": passed, "failed": failed, "failure_rate": round(failed / total, 4) if total else None}


def alert_for(rates):
    recent, baseline = rates["recent"], rates["baseline"]
    rate, normal = recent["failure_rate"], baseline["failure_rate"]
    if rate is None or normal is None or recent["settled"] < ALERT_MIN_SETTLED:
        return None
    if rate < normal * ALERT_RATIO or rate - normal < ALERT_MIN_GAP:
        return None
    return {
        "title": "Transaction failures are spiking",
        "failure_rate": rate,
        "normal_rate": normal,
        "failed": recent["failed"],
        "window_minutes": RECENT_MINUTES,
    }


def health(w, now, products):
    rates = failure_rates(now)
    return {
        "window_minutes": RECENT_MINUTES,
        "min_settled": ALERT_MIN_SETTLED,
        "recent": rates["recent"],
        "baseline": rates["baseline"],
        "alert": alert_for(rates),
        "reasons": failure_reasons(w, now),
        "products": products,
        "liveness": liveness(w),
    }


def funnel(w, now):
    since = now - timedelta(days=FUNNEL_DAYS)
    rows = fetch(f"""
        SELECT ONBOARDING_PHASE AS phase, COUNT(*) AS n
        FROM {ONBOARDING}
        WHERE DATE_CREATED >= %(since)s AND DATE_CREATED < %(now)s
        GROUP BY ONBOARDING_PHASE
    """, {"since": since, "now": now})
    phases = {r["phase"]: int(r["n"]) for r in rows}
    total = sum(phases.values())
    rank = {p: i for i, p in enumerate(PHASE_ORDER)}

    def reached(phase):
        return sum(n for p, n in phases.items() if rank.get(p, -1) >= rank[phase])

    stages = []
    for i, (key, label, phase) in enumerate(FUNNEL_STAGES):
        count = total if i == 0 else reached(phase)
        stages.append({"key": key, "label": label, "count": count, "share": round(count / total, 4) if total else 0})
    for current, following in zip(stages, stages[1:]):
        current["lost"] = current["count"] - following["count"]
    stages[-1]["lost"] = 0

    today_phases = {
        r["phase"]: int(r["n"])
        for r in fetch(f"""
            SELECT ONBOARDING_PHASE AS phase, COUNT(*) AS n
            FROM {ONBOARDING}
            WHERE DATE_CREATED >= %(today)s AND DATE_CREATED < %(now)s
            GROUP BY ONBOARDING_PHASE
        """, w)
    }
    stuck = sorted(
        (
            {"phase": p, "label": label, "count": phases.get(p, 0), "today": today_phases.get(p, 0)}
            for p, label in PHASE_LABELS.items()
            if phases.get(p) or today_phases.get(p)
        ),
        key=lambda s: (-s["count"], -s["today"]),
    )

    minutes = [
        int(r["m"])
        for r in fetch(f"""
            SELECT TIMESTAMPDIFF(MINUTE, DATE_CREATED, ACCOUNT_OPENED_DATE) AS m
            FROM {ONBOARDING}
            WHERE ACCOUNT_OPENED_DATE >= %(since)s AND ACCOUNT_OPENED_DATE < %(now)s
              AND ACCOUNT_OPENED_DATE >= DATE_CREATED
        """, {"since": since, "now": now})
    ]
    minutes.sort()

    signups = by_bucket(fetch(f"""
        SELECT {BUCKET_SQL.format(col="DATE_CREATED")} AS bucket, COUNT(*) AS n
        FROM {ONBOARDING}
        WHERE DATE_CREATED >= %(yesterday)s AND DATE_CREATED < %(now)s
        GROUP BY bucket
    """, w))

    return {
        "days": FUNNEL_DAYS,
        "stages": stages,
        "conversion": stages[-1]["share"],
        "stuck": stuck,
        "median_minutes_to_account": minutes[len(minutes) // 2] if minutes else None,
        "signups": signups,
    }


def geography(w, now):
    b = NIGERIA_BOUNDS
    rows = fetch(f"""
        SELECT ROUND(lat / %(grid)s) * %(grid)s AS lat,
               ROUND(lon / %(grid)s) * %(grid)s AS lon,
               COUNT(*) AS n,
               SUM(created >= %(recent)s) AS recent
        FROM (
            SELECT CAST(LOCATION_LAT AS DECIMAL(9, 6)) AS lat,
                   CAST(LOCATION_LON AS DECIMAL(9, 6)) AS lon,
                   CREATED AS created
            FROM {LEGACY}
            WHERE CREATED >= %(today)s AND CREATED < %(now)s
              AND LOCATION_LAT REGEXP '^-?[0-9]+(\\\\.[0-9]+)?$'
              AND LOCATION_LON REGEXP '^-?[0-9]+(\\\\.[0-9]+)?$'
        ) t
        WHERE lat BETWEEN %(lat_min)s AND %(lat_max)s
          AND lon BETWEEN %(lon_min)s AND %(lon_max)s
        GROUP BY 1, 2
    """, {**w, **b, "grid": MAP_GRID_DEGREES, "recent": now - timedelta(minutes=MAP_RECENT_MINUTES)})

    points, cities = [], defaultdict(lambda: {"count": 0, "recent": 0})
    for r in rows:
        lat, lon, n, recent = float(r["lat"]), float(r["lon"]), int(r["n"]), int(r["recent"])
        points.append({"lat": round(lat, 2), "lon": round(lon, 2), "count": n, "recent": recent})
        c = cities[nearest_city(lat, lon) or "Elsewhere"]
        c["count"] += n
        c["recent"] += recent

    located = sum(p["count"] for p in points)
    ranked = sorted(
        (
            {"city": k, "lat": CITY_COORDS[k][0], "lon": CITY_COORDS[k][1], **v}
            for k, v in cities.items()
            if k != "Elsewhere"
        ),
        key=lambda c: -c["count"],
    )
    return {
        "recent_minutes": MAP_RECENT_MINUTES,
        "located": located,
        "points": sorted(points, key=lambda p: -p["count"]),
        "cities": ranked[:8],
        "city_count": len(ranked),
    }



def summarise_banks(rows):
    banks = {}
    for r in rows:
        key = bank_names.key(r["bank"])
        b = banks.setdefault(key, {
            "key": key,
            "bank": bank_names.canonical(r["bank"]),
            "count": 0, "success": 0, "failed": 0, "system_failed": 0, "pending": 0, "value": 0.0,
            "recent": {"count": 0, "failed": 0, "system_failed": 0, "pending": 0},
        })
        n = int(r["n"])
        system = r["outcome"] == "FAILED" and classify_reason(r.get("reason"))[1] == "system"
        b["count"] += n
        if r["outcome"] == "SUCCESS":
            b["success"] += n
            b["value"] += float(r["value"] or 0)
        elif r["outcome"] == "FAILED":
            b["failed"] += n
            b["system_failed"] += n if system else 0
        elif r["outcome"] == "PENDING":
            b["pending"] += n
        if r.get("recent"):
            rs = b["recent"]
            rs["count"] += n
            if r["outcome"] in ("FAILED", "PENDING"):
                rs[r["outcome"].lower()] += n
            rs["system_failed"] += n if system else 0
    for b in banks.values():
        for part in (b, b["recent"]):
            part["settled"] = part["count"] - part["pending"]
            part["failure_rate"] = round(part["failed"] / part["settled"], 4) if part["settled"] else None
            part["system_rate"] = round(part["system_failed"] / part["settled"], 4) if part["settled"] else None
    return banks


BANKS_SQL = f"""
    SELECT l.BENEFICIARY_BANK_NAME AS bank,
           {OUTCOME_SQL} AS outcome,
           {REASON_SQL} AS reason,
           l.CREATED >= %(recent)s AS recent,
           COUNT(*) AS n,
           COALESCE(SUM(l.AMOUNT), 0) AS value
    FROM {LEGACY} l
    LEFT JOIN {PAYMENTS} p
           ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
    WHERE l.TRANSACTION_TYPE = 'INTER'
      AND l.CREATED >= %(since)s AND l.CREATED < %(until)s
    GROUP BY bank, outcome, reason, recent
"""


def others_rate(items, bank, part, field):
    failed = sum((x if part is None else x[part])[field] for x in items if x is not bank)
    settled = sum((x if part is None else x[part])["settled"] for x in items if x is not bank)
    return round(failed / settled, 4) if settled else None


def banks(w):
    recent = max(w["today"], w["now"] - timedelta(minutes=BANK_RECENT_MINUTES))
    summary = summarise_banks(fetch(BANKS_SQL, {"since": w["today"], "until": w["now"], "recent": recent}))
    items = sorted(summary.values(), key=lambda b: -b["count"])
    for b in items:
        b["others_system_rate"] = others_rate(items, b, None, "system_failed")
        b["recent"]["others_rate"] = others_rate(items, b, "recent", "failed")
        b["recent"]["others_system_rate"] = others_rate(items, b, "recent", "system_failed")
        b["failing_now"] = False
    count = sum(b["count"] for b in items)
    failed = sum(b["failed"] for b in items)
    settled = sum(b["settled"] for b in items)
    return {
        "items": items[:8],
        "all": items,
        "bank_count": len(items),
        "recent_minutes": BANK_RECENT_MINUTES,
        "total": {
            "count": count,
            "value": sum(b["value"] for b in items),
            "failure_rate": round(failed / settled, 4) if settled else None,
            "system_rate": round(sum(b["system_failed"] for b in items) / settled, 4) if settled else None,
        },
    }


def devices(w):
    rows = fetch(f"""
        SELECT UPPER(TRIM(DEVICE_OS)) AS os, COUNT(DISTINCT USERNAME) AS users
        FROM {LOGINS}
        WHERE LOGIN_TIME >= %(today)s AND LOGIN_TIME < %(now)s
        GROUP BY os
    """, w)
    out = {"android": 0, "ios": 0, "other": 0}
    for r in rows:
        os_name = (r["os"] or "").lower()
        out[os_name if os_name in ("android", "ios") else "other"] += int(r["users"])
    return out


def build_pulse(now=None):
    now = now or lagos_now()
    w = windows(now)
    tx = transactions(w)
    return {
        "generated_at": now.isoformat(),
        "timezone": "Africa/Lagos",
        "hour_now": now.hour,
        "transactions": tx["totals"],
        "hourly": tx["hourly"],
        "mix": tx["mix"],
        "active_users": active_users(w),
        "new_accounts": new_accounts(w),
        "rewards": rewards(as_utc(w)),
        "health": health(w, now, tx["products"]),
        "funnel": funnel(w, now),
        "geography": geography(w, now),
        "banks": banks(w),
        "devices": devices(w),
    }
