from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median

from django.db import DatabaseError

from . import banks as bank_names
from .queries import (
    ACCOUNT_IDS_SQL,
    ACCOUNTS,
    FUNNEL_STAGES,
    LOGIN_ID_SQL,
    LEGACY,
    LOGINS,
    ONBOARDING,
    OUTCOME_SQL,
    PAYMENTS,
    PHASE_LABELS,
    PHASE_ORDER,
    REWARDS,
    WAT,
    WEBHOOKS,
    fetch,
    lagos_now,
)
from .reasons import HINTS, REASON_SQL, classify

PRESETS = {"7": 7, "30": 30, "90": 90}
MAX_SENSIBLE_AMOUNT = 100_000_000
SMALL_BASE = 0.25
MAX_DAYS = 370
DAILY_CHART_MAX_DAYS = 35

PRODUCTS = {
    "INTER": "Transfers to other banks",
    "INTRA": "Transfers within Dash",
    "Airtime": "Airtime",
    "Data Bundle": "Data",
    "Betting & Lottery": "Betting",
    "Utilities": "Electricity & utilities",
    "Cable TV": "Cable TV",
    "Transport and Toll Payment": "Transport & tolls",
}

SIDES = {
    "customer": "Customer",
    "account": "Account restriction",
    "system": "Bank or partner",
    "unknown": "Not recorded",
    "other": "Other",
}

REWARD_LABELS = {
    "ONBOARDING_BONUS": "Welcome bonus",
    "REFERRAL": "Referral reward",
    "DAILY_TRANSFER": "Daily transfer reward",
    "DAILY_AIRTIME_DATA": "Daily airtime & data reward",
    "DAILY_BILLS": "Daily bills reward",
}


class Period:
    def __init__(self, start, end):
        self.start, self.end = start, end
        self.days = (end - start).days + 1
        self.since = datetime.combine(start, datetime.min.time())
        self.until = datetime.combine(end, datetime.min.time()) + timedelta(days=1)

    @property
    def params(self):
        return {"since": self.since, "until": self.until}

    @property
    def params_utc(self):
        return {"since": self.since - WAT, "until": self.until - WAT}

    def dates(self):
        return [self.start + timedelta(days=i) for i in range(self.days)]

    def previous(self):
        end = self.start - timedelta(days=1)
        return Period(end - timedelta(days=self.days - 1), end)

    def label(self):
        return f"{self.start:%d %b %Y} – {self.end:%d %b %Y}"


def resolve(preset=None, start=None, end=None, today=None):
    today = today or lagos_now().date()
    if preset in PRESETS:
        last = today - timedelta(days=1)
        return Period(last - timedelta(days=PRESETS[preset] - 1), last)
    start, end = date.fromisoformat(str(start)), date.fromisoformat(str(end))
    if end < start:
        start, end = end, start
    end = min(end, today)
    if (end - start).days + 1 > MAX_DAYS:
        raise ValueError(f"Choose a range of {MAX_DAYS} days or fewer.")
    return Period(start, end)


def safe(fn, default=None):
    try:
        return fn()
    except DatabaseError:
        return default


def ratio(part, whole):
    return part / whole if whole else None


def transactions(p):
    rows = fetch(f"""
        SELECT DATE(l.CREATED) AS d, l.TRANSACTION_TYPE AS kind, {OUTCOME_SQL} AS outcome,
               COUNT(*) AS n, COALESCE(SUM(l.AMOUNT), 0) AS value
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(since)s AND l.CREATED < %(until)s
        GROUP BY d, kind, outcome
    """, p.params)
    daily = defaultdict(lambda: defaultdict(float))
    products = defaultdict(lambda: defaultdict(float))
    for r in rows:
        n, value, outcome = int(r["n"]), float(r["value"]), r["outcome"].lower()
        for bucket in (daily[r["d"]], products[r["kind"] or "Other"]):
            bucket["count"] += n
            bucket[outcome] += n
            if outcome == "success":
                bucket["value"] += value
    return daily, products


def failures(p):
    rows = fetch(f"""
        SELECT DATE(l.CREATED) AS d, {REASON_SQL} AS message, COUNT(*) AS n,
               COALESCE(SUM(CASE WHEN l.AMOUNT <= {MAX_SENSIBLE_AMOUNT} THEN l.AMOUNT ELSE 0 END), 0) AS value,
               SUM(l.AMOUNT > {MAX_SENSIBLE_AMOUNT}) AS absurd
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(since)s AND l.CREATED < %(until)s AND {OUTCOME_SQL} = 'FAILED'
        GROUP BY d, message
    """, p.params)
    reasons = {}
    for r in rows:
        label, kind = classify(r["message"])
        item = reasons.setdefault(label, {"reason": label, "side": SIDES.get(kind, "Other"), "count": 0,
                                          "value": 0.0, "absurd": 0, "days": defaultdict(int)})
        item["count"] += int(r["n"])
        item["absurd"] += int(r["absurd"] or 0)
        item["value"] += float(r["value"])
        item["days"][r["d"]] += int(r["n"])
    return reasons


def destination_banks(p):
    rows = fetch(f"""
        SELECT l.BENEFICIARY_BANK_NAME AS bank, {OUTCOME_SQL} AS outcome,
               COUNT(*) AS n, COALESCE(SUM(l.AMOUNT), 0) AS value
        FROM {LEGACY} l
        LEFT JOIN {PAYMENTS} p
               ON p.payment_reference = l.PAYMENT_REFERENCE COLLATE utf8mb4_unicode_ci
        WHERE l.CREATED >= %(since)s AND l.CREATED < %(until)s AND l.TRANSACTION_TYPE = 'INTER'
        GROUP BY bank, outcome
    """, p.params)
    out = defaultdict(lambda: defaultdict(float))
    for r in rows:
        b = out[bank_names.canonical(r["bank"]) if r["bank"] else "Unknown bank"]
        outcome = r["outcome"].lower()
        b["count"] += int(r["n"])
        b[outcome] += int(r["n"])
        if outcome == "success":
            b["value"] += float(r["value"])
    return out


def money_in(p):
    rows = fetch(f"""
        SELECT DATE(c.at) AS d,
               SUM(a.account_number IS NOT NULL) AS n,
               COALESCE(SUM(CASE WHEN a.account_number IS NOT NULL THEN c.amount END), 0) AS value,
               SUM(a.account_number IS NULL) AS other_n,
               COALESCE(SUM(CASE WHEN a.account_number IS NULL THEN c.amount END), 0) AS other_value
        FROM (
            SELECT MIN(created_at) + INTERVAL 1 HOUR AS at, MAX(account_number) AS account_number,
                   MAX(CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.amount')) AS DECIMAL(18,2))) AS amount
            FROM {WEBHOOKS}
            WHERE created_at >= %(since)s AND created_at < %(until)s
              AND JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.drCr')) = 'CR'
              AND JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.service')) = 'INWARD'
            GROUP BY provider_ref
        ) c
        LEFT JOIN (SELECT DISTINCT account_number FROM {ACCOUNTS}) a ON a.account_number = c.account_number
        GROUP BY d
    """, p.params_utc)
    return {r["d"]: {"count": int(r["n"] or 0), "value": float(r["value"]),
                     "other_count": int(r["other_n"] or 0), "other_value": float(r["other_value"])}
            for r in rows}


def onboarding(p):
    started = fetch(f"""
        SELECT DATE(DATE_CREATED) AS d, COUNT(*) AS n,
               SUM(ACCOUNT_OPENED_DATE IS NOT NULL OR ONBOARDING_PHASE = 'ACCOUNT_CREATED') AS finished
        FROM {ONBOARDING}
        WHERE DATE_CREATED >= %(since)s AND DATE_CREATED < %(until)s
        GROUP BY d
    """, p.params)
    opened = fetch(f"""
        SELECT DATE(ACCOUNT_OPENED_DATE) AS d, COUNT(*) AS n
        FROM {ONBOARDING}
        WHERE ACCOUNT_OPENED_DATE >= %(since)s AND ACCOUNT_OPENED_DATE < %(until)s
        GROUP BY d
    """, p.params)
    phases = fetch(f"""
        SELECT ONBOARDING_PHASE AS phase, COUNT(*) AS n
        FROM {ONBOARDING}
        WHERE DATE_CREATED >= %(since)s AND DATE_CREATED < %(until)s
        GROUP BY phase
    """, p.params)
    return (
        {r["d"]: {"signups": int(r["n"]), "finished": int(r["finished"] or 0)} for r in started},
        {r["d"]: int(r["n"]) for r in opened},
        {r["phase"]: int(r["n"]) for r in phases},
    )


def active_users(p):
    return int(fetch(f"""
        SELECT COUNT(DISTINCT t.login_id) AS n
        FROM (
            SELECT {LOGIN_ID_SQL} AS login_id FROM {LOGINS}
            WHERE LOGIN_TIME >= %(since)s AND LOGIN_TIME < %(until)s
        ) t
        JOIN {ACCOUNT_IDS_SQL} a ON a.id = t.login_id COLLATE utf8mb4_unicode_ci
    """, p.params)[0]["n"])


def rewards(p):
    rows = fetch(f"""
        SELECT reward_type AS kind, COUNT(*) AS n, COALESCE(SUM(amount), 0) AS value
        FROM {REWARDS}
        WHERE created_at >= %(since)s AND created_at < %(until)s
        GROUP BY kind
    """, p.params_utc)
    return sorted(
        ({"type": REWARD_LABELS.get(r["kind"], r["kind"] or "Other"), "count": int(r["n"]),
          "value": float(r["value"])} for r in rows),
        key=lambda r: -r["value"],
    )


def funnel(phases):
    total = sum(phases.values())
    rank = {ph: i for i, ph in enumerate(PHASE_ORDER)}

    def reached(phase):
        return sum(n for ph, n in phases.items() if rank.get(ph, -1) >= rank[phase])

    stages = []
    for i, (_, label, phase) in enumerate(FUNNEL_STAGES):
        count = total if i == 0 else reached(phase)
        stages.append({"stage": label, "count": count, "share": ratio(count, total)})
    for current, following in zip(stages, stages[1:]):
        current["lost"] = current["count"] - following["count"]
    if stages:
        stages[-1]["lost"] = 0
    stuck = sorted(
        ({"step": label, "count": phases.get(ph, 0), "share": ratio(phases.get(ph, 0), total)}
         for ph, label in PHASE_LABELS.items() if phases.get(ph)),
        key=lambda s: -s["count"],
    )
    return stages, stuck


def collect(p):
    tx_daily, products = transactions(p)
    reasons = failures(p)
    banks = destination_banks(p)
    inflow = safe(lambda: money_in(p))
    started, opened, phases = onboarding(p)
    users = safe(lambda: active_users(p))
    paid = safe(lambda: rewards(p), [])

    series = []
    for d in p.dates():
        t = tx_daily.get(d, {})
        settled = t.get("count", 0) - t.get("pending", 0)
        series.append({
            "date": d,
            "transactions": int(t.get("count", 0)),
            "success": int(t.get("success", 0)),
            "failed": int(t.get("failed", 0)),
            "reversed": int(t.get("reversed", 0)),
            "pending": int(t.get("pending", 0)),
            "settled": int(settled),
            "success_rate": ratio(t.get("success", 0), settled),
            "value": round(t.get("value", 0.0), 2),
            "money_in": None if inflow is None else inflow.get(d, {}).get("value", 0.0),
            "money_in_count": None if inflow is None else inflow.get(d, {}).get("count", 0),
            "money_in_other": None if inflow is None else inflow.get(d, {}).get("other_value", 0.0),
            "money_in_other_count": None if inflow is None else inflow.get(d, {}).get("other_count", 0),
            "signups": started.get(d, {}).get("signups", 0),
            "finished": started.get(d, {}).get("finished", 0),
            "accounts": opened.get(d, 0),
        })

    def total(key):
        return sum(s[key] for s in series if s[key] is not None)

    settled = total("settled")
    signups = total("signups")
    totals = {
        "transactions": total("transactions"),
        "success": total("success"),
        "failed": total("failed"),
        "reversed": total("reversed"),
        "pending": total("pending"),
        "settled": settled,
        "success_rate": ratio(total("success"), settled),
        "failure_rate": ratio(total("failed"), settled),
        "value": total("value"),
        "average_value": ratio(total("value"), total("success")),
        "money_in": None if inflow is None else total("money_in"),
        "money_in_count": None if inflow is None else total("money_in_count"),
        "money_in_other": None if inflow is None else total("money_in_other"),
        "money_in_other_count": None if inflow is None else total("money_in_other_count"),
        "signups": signups,
        "accounts": total("accounts"),
        "finish_rate": ratio(total("finished"), signups),
        "active_users": users,
        "rewards_count": sum(r["count"] for r in paid),
        "rewards_value": sum(r["value"] for r in paid),
    }

    product_rows = []
    for kind, v in products.items():
        settled_k = v.get("count", 0) - v.get("pending", 0)
        product_rows.append({
            "product": PRODUCTS.get(kind, kind),
            "count": int(v.get("count", 0)),
            "success": int(v.get("success", 0)),
            "failed": int(v.get("failed", 0)),
            "reversed": int(v.get("reversed", 0)),
            "value": round(v.get("value", 0.0), 2),
            "failure_rate": ratio(v.get("failed", 0), settled_k),
            "share": ratio(v.get("count", 0), totals["transactions"]),
        })
    product_rows.sort(key=lambda r: -r["count"])

    bank_rows = []
    for name, v in banks.items():
        settled_b = v.get("count", 0) - v.get("pending", 0)
        bank_rows.append({
            "bank": name,
            "count": int(v.get("count", 0)),
            "success": int(v.get("success", 0)),
            "failed": int(v.get("failed", 0)),
            "value": round(v.get("value", 0.0), 2),
            "failure_rate": ratio(v.get("failed", 0), settled_b),
        })
    bank_rows.sort(key=lambda r: -r["count"])

    reason_rows = sorted(reasons.values(), key=lambda r: -r["count"])
    for r in reason_rows:
        r["share"] = ratio(r["count"], totals["failed"])
        r["hint"] = HINTS.get(r["reason"], "")
        r["worst_day"] = max(r["days"].items(), key=lambda kv: kv[1])[0] if r["days"] else None

    stages, stuck = funnel(phases)
    return {
        "period": p,
        "series": series,
        "totals": totals,
        "products": product_rows,
        "banks": bank_rows,
        "reasons": reason_rows,
        "funnel": stages,
        "stuck": stuck,
        "rewards": paid,
    }


def weekly(series):
    weeks = {}
    for s in series:
        start = s["date"] - timedelta(days=s["date"].weekday())
        w = weeks.setdefault(start, {"date": start, "end": s["date"], "days": 0, **{
            k: 0 for k in ("transactions", "success", "failed", "settled", "value", "signups", "accounts")}})
        w["end"] = s["date"]
        w["days"] += 1
        for k in ("transactions", "success", "failed", "settled", "value", "signups", "accounts"):
            w[k] += s[k]
        if s["money_in"] is not None:
            w["money_in"] = w.get("money_in", 0) + s["money_in"]
    for w in weeks.values():
        w["success_rate"] = ratio(w["success"], w["settled"])
        w.setdefault("money_in", None)
    return list(weeks.values())


def change(now, before, points=False):
    if now is None or before is None:
        return None
    if points:
        return now - before
    return (now / before - 1) if before else None


COMPARE = [
    ("Transactions", "transactions", "count", False, True),
    ("Successful transactions", "success", "count", False, True),
    ("Success rate", "success_rate", "pct", True, True),
    ("Failed transactions", "failed", "count", False, False),
    ("Reversed transactions", "reversed", "count", False, False),
    ("Money sent by customers", "value", "money", False, True),
    ("Average successful transaction", "average_value", "money", False, True),
    ("Money in from other banks", "money_in", "money", False, True),
    ("Received into other Dash accounts", "money_in_other", "money", False, None),
    ("Sign-ups started", "signups", "count", False, True),
    ("Accounts opened", "accounts", "count", False, True),
    ("Sign-ups that finished", "finish_rate", "pct", True, True),
    ("Customers who signed in", "active_users", "count", False, True),
    ("Rewards paid", "rewards_value", "money", False, None),
]


PARTIAL_KEYS = {"accounts": ("accounts",), "money_in": ("money_in", "money_in_other")}


def partial_keys(since, prev):
    return {k for source, keys in PARTIAL_KEYS.items()
            if since.get(source) and since[source] > prev["period"].start for k in keys}


def comparison(cur, prev, partial=()):
    rows = []
    for label, key, kind, points, up_is_good in COMPARE:
        now, before = cur["totals"].get(key), prev["totals"].get(key)
        if key == "money_in_other" and not now and not before:
            continue
        comparable = key not in partial
        rows.append({"metric": label, "key": key, "kind": kind, "now": now, "before": before,
                     "change": change(now, before, points) if comparable else None, "points": points,
                     "up_is_good": up_is_good, "comparable": comparable})
    return rows


def money(v):
    return f"NGN {v:,.0f}" if v is not None else "n/a"


def pct(v, digits=1):
    return f"{v * 100:.{digits}f}%" if v is not None else "n/a"


def findings(cur, prev, partial=()):
    t, b = cur["totals"], prev["totals"]
    out = []

    def moved(label, now, before, fmt, key=None):
        if key in partial:
            out.append(f"{label}: {fmt(now)}. There is no fair comparison with the previous period because "
                       f"it was not fully recorded then.")
            return
        c = change(now, before)
        if c is None:
            return
        direction = "rose" if c > 0 else "fell"
        if abs(c) < 0.02:
            out.append(f"{label} was steady at {fmt(now)}.")
        else:
            out.append(f"{label} {direction} {abs(c) * 100:.0f}% to {fmt(now)} (previous period {fmt(before)}).")

    moved("Transactions", t["transactions"], b["transactions"], lambda v: f"{v:,}")
    moved("Money sent by customers", t["value"], b["value"], money)
    if t["success_rate"] is not None and b["success_rate"] is not None:
        diff = (t["success_rate"] - b["success_rate"]) * 100
        if abs(diff) < 0.5:
            out.append(f"Success rate held at {pct(t['success_rate'])}.")
        else:
            out.append(f"Success rate {'rose' if diff > 0 else 'fell'} to {pct(t['success_rate'])} "
                       f"({abs(diff):.1f} points {'up' if diff > 0 else 'down'} from {pct(b['success_rate'])}).")
    if cur["reasons"]:
        top = cur["reasons"][0]
        out.append(f"The main failure reason was \"{top['reason']}\" ({pct(top['share'], 0)} of failures, "
                   f"{top['count']:,} transactions).")
        system = sum(r["count"] for r in cur["reasons"] if r["side"] == "Bank or partner")
        if t["failed"]:
            out.append(f"{pct(system / t['failed'], 0)} of failures were on the bank or partner side; "
                       f"the rest were customer-side, account restrictions or unrecorded.")
    moved("Accounts opened", t["accounts"], b["accounts"], lambda v: f"{v:,}", "accounts")
    if t["money_in"] is not None:
        line = (f"Customers received {money(t['money_in'])} from other banks in {t['money_in_count']:,} "
                f"transfers.")
        if t["money_in_other"]:
            line += (f" A further {money(t['money_in_other'])} arrived into Dash accounts that are not app "
                     f"customers and is shown separately.")
        out.append(line)
    return out


def notable_events(cur):
    s = cur["series"]
    out = []
    active = [d for d in s if d["transactions"]]
    if active:
        busiest = max(active, key=lambda d: d["transactions"])
        quietest = min(active, key=lambda d: d["transactions"])
        out.append(("Busiest day", busiest["date"], f"{busiest['transactions']:,} transactions, "
                                                    f"{money(busiest['value'])} sent"))
        out.append(("Quietest day", quietest["date"], f"{quietest['transactions']:,} transactions"))
        top_value = max(active, key=lambda d: d["value"])
        out.append(("Highest value day", top_value["date"], f"{money(top_value['value'])} sent by customers"))
    for d in s:
        if d["settled"] >= 50 and d["success_rate"] is not None and d["success_rate"] < 0.75:
            out.append(("High failure day", d["date"], f"only {pct(d['success_rate'])} succeeded "
                                                       f"({d['failed']:,} failed of {d['settled']:,})"))
        if d["transactions"] == 0:
            out.append(("No transactions", d["date"], "nothing recorded all day; check for an outage"))
        if d["signups"] >= 50 and d["accounts"] == 0:
            out.append(("No accounts opened", d["date"], f"{d['signups']:,} people started signing up "
                                                         f"but no account was opened"))
    signups = [d["signups"] for d in s if d["signups"]]
    if len(signups) >= 7:
        typical = median(signups)
        for d in s:
            if typical and d["signups"] >= typical * 2 and d["signups"] >= 100:
                out.append(("Sign-up spike", d["date"], f"{d['signups']:,} sign-ups, "
                                                        f"{d['signups'] / typical:.1f}x a typical day"))
    for r in cur["reasons"][:8]:
        if r["count"] >= 30 and r["days"]:
            worst = max(r["days"].values())
            if worst >= max(20, r["count"] * 0.4) and len(r["days"]) > 1:
                out.append(("Failure burst", r["worst_day"], f"{worst:,} \"{r['reason']}\" failures in one day"))
    out.sort(key=lambda e: e[1])
    return out


def recorded_from():
    out = {}
    first_open = safe(lambda: fetch(f"SELECT MIN(ACCOUNT_OPENED_DATE) AS d FROM {ONBOARDING}", {})[0]["d"])
    if first_open:
        out["accounts"] = first_open.date()
    first_in = safe(lambda: fetch(f"SELECT MIN(created_at) AS d FROM {WEBHOOKS}", {})[0]["d"])
    if first_in:
        out["money_in"] = (first_in + WAT).date()
    return out


def availability(cur, prev, since):
    notes = []
    earliest = prev["period"].start
    if since.get("accounts") and since["accounts"] > earliest:
        notes.append(f"Account opening dates are only recorded from {since['accounts']:%d %B %Y}, so the "
                     f"previous period's accounts opened is incomplete and the change is shown as not comparable.")
    if cur["totals"]["money_in"] is None:
        notes.append("Money in could not be read for this report.")
    elif since.get("money_in") and since["money_in"] > earliest:
        notes.append(f"Money in from other banks is only recorded from {since['money_in']:%d %B %Y}, so the "
                     f"previous period's figure is incomplete and the change is shown as not comparable.")
    if cur["totals"].get("money_in_other"):
        notes.append(f"Money in counts only transfers into app customers' accounts. A further "
                     f"{money(cur['totals']['money_in_other'])} ({cur['totals']['money_in_other_count']:,} "
                     f"transfers) arrived into Dash accounts that are not app customers, such as treasury or "
                     f"fixed-deposit accounts, and is shown separately.")
    before, now = prev["totals"]["transactions"], cur["totals"]["transactions"]
    if now and before < now * SMALL_BASE:
        notes.append(f"The previous period had far less activity ({before:,} transactions against {now:,}), "
                     f"so the percentage changes mostly reflect growth from a small starting point and should "
                     f"not be read as like-for-like performance.")
    absurd = sum(r["absurd"] for r in cur["reasons"])
    if absurd:
        notes.append(f"{absurd:,} failed attempts had impossible amounts (over NGN {MAX_SENSIBLE_AMOUNT:,}), "
                     f"usually mistyped; they are counted as failures but left out of failure values.")
    if cur["totals"]["active_users"] is None:
        notes.append("Active users could not be counted for this period (the query took too long).")
    if cur["period"].end >= lagos_now().date():
        notes.append("The period includes today, so today's figures are incomplete.")
    return notes


def build(period, generated_by=""):
    cur = collect(period)
    prev = collect(period.previous())
    since = recorded_from()
    partial = partial_keys(since, prev)
    return {
        "period": period,
        "previous": period.previous(),
        "current": cur,
        "prior": prev,
        "comparison": comparison(cur, prev, partial),
        "findings": findings(cur, prev, partial),
        "events": notable_events(cur),
        "notes": availability(cur, prev, since),
        "weekly": weekly(cur["series"]),
        "generated_at": lagos_now(),
        "generated_by": generated_by,
    }
