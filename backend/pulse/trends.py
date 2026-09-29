from datetime import timedelta
from statistics import median

from .queries import LEGACY, ONBOARDING, OUTCOME_SQL, PAYMENTS, fetch

DAYS = 90


def daily(sql, params, fields):
    return {r["d"]: {f: float(r[f] or 0) for f in fields} for r in fetch(sql, params)}


def week_days(series, start, end):
    return series[-end:len(series) - start] if start else series[-end:]


def week(series, key, start, end):
    return sum(d[key] for d in week_days(series, start, end))


def typical_day(series, key, start, end):
    days = week_days(series, start, end)
    return median(d[key] for d in days) if days else 0


def compare(series, key, ratio_of=None):
    def value(start, end):
        if ratio_of:
            total = week(series, ratio_of, start, end)
            return week(series, key, start, end) / total if total else None
        return typical_day(series, key, start, end)

    now, last_week, month_ago = value(0, 7), value(7, 14), value(28, 35)

    def change(base):
        if now is None or not base:
            return None
        return round(now - base, 4) if ratio_of else round(now / base - 1, 4)

    return {
        "this_week": round(now, 4) if now is not None else None,
        "last_week": round(last_week, 4) if last_week is not None else None,
        "month_ago": round(month_ago, 4) if month_ago is not None else None,
        "vs_last_week": change(last_week),
        "vs_month_ago": change(month_ago),
    }


def build_trends(now):
    today = now.replace(hour=0, minute=0, second=0)
    since = today - timedelta(days=DAYS)
    params = {"since": since, "today": today}

    tx = daily(f"""
        SELECT DATE(l.CREATED) AS d,
               COUNT(*) AS transactions,
               SUM(CASE WHEN {OUTCOME_SQL} = 'SUCCESS' THEN l.AMOUNT ELSE 0 END) AS value,
               SUM({OUTCOME_SQL} = 'FAILED') AS failed,
               SUM({OUTCOME_SQL} <> 'PENDING') AS settled
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(since)s AND l.CREATED < %(today)s
        GROUP BY d
    """, params, ["transactions", "value", "failed", "settled"])
    signups = daily(f"""
        SELECT DATE(DATE_CREATED) AS d, COUNT(*) AS signups
        FROM {ONBOARDING}
        WHERE DATE_CREATED >= %(since)s AND DATE_CREATED < %(today)s
        GROUP BY d
    """, params, ["signups"])
    accounts = daily(f"""
        SELECT DATE(ACCOUNT_OPENED_DATE) AS d, COUNT(*) AS accounts
        FROM {ONBOARDING}
        WHERE ACCOUNT_OPENED_DATE >= %(since)s AND ACCOUNT_OPENED_DATE < %(today)s
        GROUP BY d
    """, params, ["accounts"])

    series = []
    for i in range(DAYS, 0, -1):
        d = (today - timedelta(days=i)).date()
        t = tx.get(d, {})
        settled = t.get("settled", 0)
        series.append({
            "date": d.isoformat(),
            "transactions": int(t.get("transactions", 0)),
            "value": round(t.get("value", 0), 2),
            "failed": int(t.get("failed", 0)),
            "settled": int(settled),
            "failure_rate": round(t.get("failed", 0) / settled, 4) if settled else None,
            "signups": int(signups.get(d, {}).get("signups", 0)),
            "accounts": int(accounts.get(d, {}).get("accounts", 0)),
        })

    return {
        "days": DAYS,
        "series": series,
        "summary": {
            "transactions": compare(series, "transactions"),
            "value": compare(series, "value"),
            "signups": compare(series, "signups"),
            "accounts": compare(series, "accounts"),
            "failure_rate": compare(series, "failed", ratio_of="settled"),
        },
    }
