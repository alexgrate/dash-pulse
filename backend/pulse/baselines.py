from datetime import timedelta
from statistics import median

from django.core.cache import cache

from .queries import LEGACY, LIVENESS, ONBOARDING, OUTCOME_SQL, PAYMENTS, REWARDS, WAT, fetch
from .reasons import REASON_SQL
from .reasons import group as group_reasons

TYPICAL_WEEKS = 4
COMPARE_DAYS = 7
CACHE_SECONDS = 15 * 60


def cached(key, build):
    value = cache.get(key)
    if value is None:
        value = build()
        cache.set(key, value, CACHE_SECONDS)
    return value


def typical_day(now):
    today = now.replace(hour=0, minute=0, second=0)
    since = today - timedelta(weeks=TYPICAL_WEEKS)
    params = {"since": since, "today": today, "t": now.time()}

    hourly = fetch(f"""
        SELECT DATE(CREATED) AS d, HOUR(CREATED) AS h, COUNT(*) AS n
        FROM {LEGACY}
        WHERE CREATED >= %(since)s AND CREATED < %(today)s
          AND DAYOFWEEK(CREATED) = DAYOFWEEK(%(today)s)
        GROUP BY d, h
    """, params)
    days = fetch(f"""
        SELECT DATE(CREATED) AS d, COUNT(*) AS total, SUM(TIME(CREATED) < %(t)s) AS so_far
        FROM {LEGACY}
        WHERE CREATED >= %(since)s AND CREATED < %(today)s
          AND DAYOFWEEK(CREATED) = DAYOFWEEK(%(today)s)
        GROUP BY d
    """, params)

    days = [d for d in days if int(d["total"]) > 0]
    if len(days) < 2:
        return None

    by_hour = {h: [] for h in range(24)}
    dates = {d["d"] for d in days}
    counts = {(r["d"], int(r["h"])): int(r["n"]) for r in hourly}
    for d in dates:
        for h in range(24):
            by_hour[h].append(counts.get((d, h), 0))

    fractions = [int(d["so_far"]) / int(d["total"]) for d in days]
    return {
        "weekday": today.strftime("%A"),
        "days": len(days),
        "hourly_median": [median(v) for v in by_hour.values()],
        "hourly_low": [min(v) for v in by_hour.values()],
        "hourly_high": [max(v) for v in by_hour.values()],
        "so_far_median": median(int(d["so_far"]) for d in days),
        "total_median": median(int(d["total"]) for d in days),
        "fraction_median": median(fractions),
        "fraction_low": min(fractions),
        "fraction_high": max(fractions),
    }


def reason_shares(today):
    rows = fetch(f"""
        SELECT {REASON_SQL} AS reason, COUNT(*) AS n
        FROM {LEGACY}
        WHERE CBA_RESPONSE_CODE = 'false'
          AND CREATED >= %(since)s AND CREATED < %(today)s
        GROUP BY reason
    """, {"since": today - timedelta(days=COMPARE_DAYS), "today": today})
    grouped = group_reasons(rows, ["n"])
    total = sum(r["n"] for r in grouped) or 1
    return {r["reason"]: r["n"] / total for r in grouped}


def typical_signups(now):
    today = now.replace(hour=0, minute=0, second=0)
    rows = fetch(f"""
        SELECT DATE(DATE_CREATED) AS d, SUM(TIME(DATE_CREATED) < %(t)s) AS so_far
        FROM {ONBOARDING}
        WHERE DATE_CREATED >= %(since)s AND DATE_CREATED < %(today)s
          AND DAYOFWEEK(DATE_CREATED) = DAYOFWEEK(%(today)s)
        GROUP BY d
    """, {"since": today - timedelta(weeks=TYPICAL_WEEKS), "today": today, "t": now.time()})
    values = [int(r["so_far"] or 0) for r in rows]
    return median(values) if len(values) >= 2 else None


def product_rates(today):
    rows = fetch(f"""
        SELECT kind,
               COUNT(*) AS n,
               SUM(outcome = 'FAILED') AS failed,
               SUM(outcome = 'REVERSED') AS reversed,
               SUM(outcome = 'PENDING') AS pending
        FROM (
            SELECT l.TRANSACTION_TYPE AS kind, {OUTCOME_SQL} AS outcome
            FROM {LEGACY} l
            LEFT JOIN {PAYMENTS} p
                   ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
            WHERE l.CREATED >= %(since)s AND l.CREATED < %(today)s
        ) t
        GROUP BY kind
    """, {"since": today - timedelta(days=COMPARE_DAYS), "today": today})
    out = {}
    for r in rows:
        settled = int(r["n"]) - int(r["pending"])
        if settled:
            out[r["kind"]] = {
                "count": int(r["n"]),
                "failure_rate": int(r["failed"]) / settled,
                "reversal_rate": int(r["reversed"]) / settled,
            }
    return out


def liveness_rate(today):
    rows = fetch(f"""
        SELECT SUM(STATUS = 'LOW_SCORE') AS failed, COUNT(*) AS n
        FROM {LIVENESS}
        WHERE DATE_CREATED >= %(since)s AND DATE_CREATED < %(today)s
    """, {"since": today - timedelta(days=COMPARE_DAYS), "today": today})
    n = int(rows[0]["n"] or 0) if rows else 0
    return int(rows[0]["failed"] or 0) / n if n else None


def rewards_per_transaction(today):
    since = today - timedelta(days=COMPARE_DAYS)
    rewards = fetch(f"""
        SELECT COUNT(*) AS n, COALESCE(SUM(amount), 0) AS value
        FROM {REWARDS}
        WHERE created_at >= %(since)s AND created_at < %(today)s
    """, {"since": since - WAT, "today": today - WAT})[0]
    tx = fetch(f"""
        SELECT COUNT(*) AS n FROM {LEGACY} WHERE CREATED >= %(since)s AND CREATED < %(today)s
    """, {"since": since, "today": today})[0]
    n = int(tx["n"])
    return {"per_tx": int(rewards["n"]) / n, "value_per_tx": float(rewards["value"]) / n} if n else None


def build(now):
    today = now.replace(hour=0, minute=0, second=0)
    day = today.date().isoformat()
    quarter = f"{day}T{now.hour:02d}{now.minute // 15}"
    return {
        "typical": cached(f"pulse:typical:{quarter}", lambda: typical_day(now)),
        "signups": cached(f"pulse:signups:{quarter}", lambda: typical_signups(now)),
        "reasons": cached(f"pulse:reasons:{day}", lambda: reason_shares(today)),
        "products": cached(f"pulse:products:{day}", lambda: product_rates(today)),
        "liveness": cached(f"pulse:liveness:{day}", lambda: liveness_rate(today)),
        "rewards": cached(f"pulse:rewards:{day}", lambda: rewards_per_transaction(today)),
    }
