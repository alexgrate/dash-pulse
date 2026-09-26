from datetime import datetime

from .reasons import DEFAULT_HINT
from .reasons import HINTS as REASON_HINTS
from .reasons import NOT_RECORDED


PRODUCT_LABELS = {
    "INTER": "Transfers to other banks",
    "INTRA": "Transfers within Dash",
    "Airtime": "Airtime purchases",
    "Data Bundle": "Data purchases",
    "Betting & Lottery": "Betting top-ups",
    "Utilities": "Electricity & utilities",
    "Cable TV": "Cable TV",
    "Transport and Toll Payment": "Transport & tolls",
}

MIN_VOLUME = 20
MAP_MIN_CITIES = 3
BANK_MIN_RECENT = 10
BANK_SYSTEM_RATE = 0.25
BANK_SYSTEM_GAP = 0.2
BANK_MIN_DAY = 30
BANK_DAY_RATE = 0.15
BANK_DAY_GAP = 0.12


def pct(x, digits=0):
    return f"{x * 100:.{digits}f}%"


def fmt(n):
    return f"{round(n):,}"


def short(n):
    return f"{n / 1000:.1f}k" if n >= 1000 else fmt(n)


def naira(v):
    for size, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if v >= size:
            return f"₦{v / size:.1f}{suffix}"
    return f"₦{v:,.0f}"


def insight(key, scene, severity, icon, title, detail, score):
    return {
        "id": key,
        "scene": scene,
        "severity": severity,
        "icon": icon,
        "title": title,
        "detail": detail,
        "score": round(score, 1),
    }


def forecast(p, typical):
    if not typical:
        return None
    so_far = p["transactions"]["today"]["count"]
    if typical["fraction_median"] < 0.08 or so_far < MIN_VOLUME:
        return None
    projected = so_far / typical["fraction_median"]
    total = typical["total_median"]
    return {
        "projected": round(projected),
        "low": round(so_far / typical["fraction_high"]),
        "high": round(so_far / max(typical["fraction_low"], 0.01)),
        "typical_total": round(total),
        "vs_typical": round(projected / total - 1, 4) if total else None,
    }


def volume(p, typical, fc):
    if not typical or typical["so_far_median"] < MIN_VOLUME:
        return []
    weekday = typical["weekday"]
    so_far, expected = p["transactions"]["today"]["count"], typical["so_far_median"]
    diff = so_far / expected - 1
    detail = f"{fmt(so_far)} transactions so far vs ~{fmt(expected)} by this time on recent {weekday}s"
    out = []
    if diff >= 0.1:
        out.append(insight("volume", "pulse", "good", "trending-up", f"Busier than a typical {weekday} (+{pct(diff)})",
                           detail, 30 + min(diff * 100, 50)))
    elif diff <= -0.1:
        out.append(insight("volume", "pulse", "warn" if diff <= -0.25 else "info", "trending-down",
                           f"Quieter than a typical {weekday} ({pct(diff)})",
                           f"{detail}. Worth checking app and channel availability." if diff <= -0.25 else detail,
                           30 + min(abs(diff) * 120, 60)))
    else:
        out.append(insight("volume", "pulse", "good", "check", f"Activity is normal for a {weekday}", detail, 8))

    if fc:
        out.append(insight("forecast", "pulse", "warn" if (fc["vs_typical"] or 0) <= -0.2 else "info", "target",
                           f"On track for ~{fmt(fc['projected'])} transactions today",
                           f"Typical {weekday}: ~{fmt(fc['typical_total'])} · likely range "
                           f"{fmt(fc['low'])}–{fmt(fc['high'])}", 34))
    return out


def last_hour(p, typical):
    h = p["hour_now"] - 1
    if not typical or h < 0:
        return []
    actual = p["hourly"]["today"][h]
    low, high, mid = typical["hourly_low"][h], typical["hourly_high"][h], typical["hourly_median"][h]
    if mid < 10:
        return []
    window = f"{h:02d}:00–{h + 1:02d}:00"
    if actual > high * 1.15:
        return [insight("hour", "pulse", "good", "zap", f"{window} was unusually busy",
                        f"{fmt(actual)} transactions vs a usual {fmt(low)}–{fmt(high)}", 40)]
    if actual < low * 0.85:
        return [insight("hour", "pulse", "warn", "activity", f"{window} was unusually quiet",
                        f"{fmt(actual)} transactions vs a usual {fmt(low)}–{fmt(high)}. Check app and channel health.",
                        58)]
    return []


def failures(p):
    h = p["health"]
    alert, recent, normal = h["alert"], h["recent"], h["baseline"]["failure_rate"]
    today = p["transactions"]["today"]
    out = []
    if alert:
        out.append(insight("alert", "health", "bad", "siren", alert["title"],
                           f"{pct(alert['failure_rate'], 1)} failing in the last {alert['window_minutes']} min "
                           f"vs {pct(alert['normal_rate'], 1)} normally", 100))
    elif recent["failure_rate"] is not None and normal and recent["settled"] >= 15 \
            and recent["failure_rate"] >= normal * 1.25:
        out.append(insight("failures-rising", "health", "warn", "trending-up", "Failure rate is creeping up",
                           f"{pct(recent['failure_rate'], 1)} in the last {h['window_minutes']} min "
                           f"vs {pct(normal, 1)} normally", 50))

    settled = today["count"] - today["pending"]
    if normal and settled >= MIN_VOLUME:
        rate = today["failed"] / settled
        if rate <= normal - 0.02:
            out.append(insight("failures-low", "health", "good", "shield-check", "Fewer failures than usual today",
                               f"{pct(rate, 1)} of transactions failed vs {pct(normal, 1)} over the last week", 24))
    return out


def reasons(p, b):
    rows = p["health"]["reasons"]
    total = sum(r["today"] for r in rows)
    if total < 10:
        return []
    out = []
    for r in rows:
        share, base = r["today"] / total, b["reasons"].get(r["reason"], 0)
        if r["today"] >= 5 and base > 0 and share / base >= 1.6 and share - base >= 0.08:
            hint = REASON_HINTS.get(r["reason"], DEFAULT_HINT)
            out.append(insight(f"reason-{r['reason']}", "health", "warn", "zap",
                               f"“{r['reason']}” is {share / base:.1f}× its usual share of failures",
                               f"{pct(share)} of today's failures vs {pct(base)} last week. {hint}",
                               55 + min((share - base) * 100, 30)))

    by_kind = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + r["today"]
    known = total - by_kind.get("unknown", 0)
    if known >= 10:
        system = by_kind.get("system", 0) / known
        top_system = next((r for r in rows if r["kind"] == "system"), None)
        if system >= 0.4 and top_system:
            out.append(insight("reasons-mix", "health", "warn", "server", f"{pct(system)} of failures are system-side",
                               f"Led by “{top_system['reason']}”. {REASON_HINTS.get(top_system['reason'], DEFAULT_HINT)}",
                               52))
        else:
            top = next(r for r in rows if r["kind"] != "unknown")
            out.append(insight("reasons-mix", "health", "good", "user",
                               f"Only {pct(system)} of failures are system-side",
                               f"Mostly “{top['reason']}”. The platform itself is holding up.", 18))

    account = by_kind.get("account", 0) / total
    if account >= 0.15:
        out.append(insight("reasons-pnd", "health", "info", "lock", f"{pct(account)} of failures hit restricted (PND) accounts",
                           f"{fmt(by_kind['account'])} attempts today from accounts on Post-No-Debit. "
                           f"Usually KYC or compliance holds that ops can review.", 30))

    missing = by_kind.get("unknown", 0) / total
    if missing >= 0.1:
        out.append(insight("reasons-missing", "health", "info", "help-circle",
                           f"{pct(missing)} of failures have no reason recorded",
                           f"“{NOT_RECORDED}” on {fmt(by_kind['unknown'])} failed transactions today. "
                           f"A logging gap worth raising with the backend team.", 16))
    return out


def products(p, b):
    out, chronic = [], None
    for prod in p["health"]["products"]:
        base = b["products"].get(prod["kind"])
        label = PRODUCT_LABELS.get(prod["kind"], prod["kind"])
        if not base or prod["count"] < 10 or prod["failure_rate"] is None:
            continue
        if prod["reversal_rate"] - base["reversal_rate"] >= 0.05 and prod["reversal_rate"] >= base["reversal_rate"] * 1.5:
            out.append(insight(f"reversal-{prod['kind']}", "health", "warn", "rotate-ccw",
                               f"{label} reversals jumped to {pct(prod['reversal_rate'])}",
                               f"Usually {pct(base['reversal_rate'])}. Customers are being debited then refunded; "
                               f"check the vendor.", 54))
        if prod["failure_rate"] - base["failure_rate"] >= 0.08 and prod["failure_rate"] >= base["failure_rate"] * 1.5:
            out.append(insight(f"failure-{prod['kind']}", "health", "warn", "x-circle",
                               f"{label} failures at {pct(prod['failure_rate'])}",
                               f"Usually {pct(base['failure_rate'])} over the last week.", 54))
        if base["count"] >= 50 and base["reversal_rate"] >= 0.15 and (
                not chronic or base["reversal_rate"] > chronic[1]["reversal_rate"]):
            chronic = (label, base)
    if chronic:
        label, base = chronic
        out.append(insight("chronic-reversals", "health", "info", "rotate-ccw",
                           f"{pct(base['reversal_rate'])} of {label[0].lower() + label[1:]} get reversed",
                           "Consistently, across the last 7 days. A vendor issue worth raising.", 22))
    return out


def onboarding(p, b):
    f, out = p["funnel"], []
    stages = f["stages"]
    worst = max(range(len(stages) - 1), key=lambda i: stages[i]["lost"], default=None)
    if worst is not None and stages[worst]["lost"] > 0 and stages[worst]["count"]:
        s, nxt = stages[worst], stages[worst + 1]
        out.append(insight("funnel-leak", "funnel", "info", "filter",
                           f"Biggest leak: {short(s['lost'])} reach “{s['label']}” but not “{nxt['label']}”",
                           f"{pct(s['lost'] / s['count'])} drop-off at this step over the last {f['days']} days. "
                           f"Fixing it moves conversion the most.", 32))

    today, base = p["health"]["liveness"]["failure_rate"], b["liveness"]
    if today is not None and base is not None and today >= base + 0.08:
        out.append(insight("liveness", "funnel", "warn", "scan-face", "Face checks are failing more than usual",
                           f"{pct(today)} low-score today vs {pct(base)} last week. This blocks sign-ups "
                           f"and password resets.", 50))

    s, usual = f["signups"], b.get("signups")
    weekday = b["typical"]["weekday"] if b.get("typical") else None
    compare, label = (usual, f"a typical {weekday}") if usual and weekday else (s["yesterday"], "yesterday")
    if compare and compare >= MIN_VOLUME:
        diff = s["today"] / compare - 1
        if abs(diff) >= 0.25:
            out.append(insight("signups", "funnel", "good" if diff > 0 else "warn",
                               "user-plus", f"Sign-ups {'up' if diff > 0 else 'down'} {pct(abs(diff))} vs {label}",
                               f"{fmt(s['today'])} so far vs ~{fmt(compare)} by this time on {label}",
                               28 + min(abs(diff) * 40, 20)))
    return out


def geography(p):
    g, out = p["geography"], []
    located, cities = g["located"], g["cities"]
    recent_total = sum(c["recent"] for c in cities)
    if not located or len(cities) < MAP_MIN_CITIES:
        return out
    if recent_total >= 20:
        for c in cities:
            share_recent, share_today = c["recent"] / recent_total, c["count"] / located
            if c["recent"] >= 8 and share_recent >= share_today * 1.6 and share_recent - share_today >= 0.08:
                out.append(insight(f"city-{c['city']}", "map", "info", "map-pin", f"{c['city']} is unusually busy right now",
                                   f"{pct(share_recent)} of activity in the last {g['recent_minutes']} min "
                                   f"vs {pct(share_today)} across today", 36))
                break
    top = cities[0]
    share = top["count"] / located
    if share >= 0.35:
        out.append(insight("city-top", "map", "info", "map-pin", f"{top['city']} drives {pct(share)} of activity",
                           f"{fmt(top['count'])} of {fmt(located)} located transactions today", 14))
    return out


def rewards(p, b):
    tx = p["transactions"]["today"]["count"]
    r = p["rewards"]["today"]
    last = p["rewards"].get("last_paid_at")
    if r["count"] == 0:
        if not last:
            return []
        last_at = datetime.fromisoformat(last)
        days = (datetime.fromisoformat(p["generated_at"]).date() - last_at.date()).days
        if days < 1:
            return []
        return [insight("rewards-paused", "flow", "info", "gift", "No reward payouts today",
                        f"Last payout was {last_at.day} {last_at:%b} ({days} day{'s' if days != 1 else ''} ago). "
                        f"The quest rewards programme looks paused.", 20)]
    base = b["rewards"]
    if tx < 50 or not base or not base["per_tx"]:
        return []
    per_tx = r["count"] / tx
    change = per_tx / base["per_tx"] - 1
    cost = f"{naira(r['value'])} paid so far, about {naira(r['value'] / tx)} per transaction"
    if change >= 0.2:
        return [insight("rewards", "flow", "warn", "gift", f"Rewards per transaction up {pct(change)} on last week",
                        f"{per_tx:.2f} payouts per transaction vs {base['per_tx']:.2f}. {cost}.", 46)]
    return [insight("rewards", "flow", "info", "gift", f"{naira(r['value'])} paid in rewards today",
                    f"{per_tx:.2f} payouts per transaction, about {naira(r['value'] / tx)} each", 12)]


def flag_banks(p, b):
    data, base = p.get("banks"), b.get("banks") or {}
    if not data:
        return
    for bank in data.get("all", data["items"]):
        r = bank["recent"]
        usual = base.get(bank["key"]) or {}
        bank["usual_rate"] = usual.get("failure_rate")
        bank["usual_system_rate"] = usual.get("system_rate")
        bank["failing_now"] = bool(
            r["settled"] >= BANK_MIN_RECENT
            and r["system_rate"] is not None
            and r.get("others_system_rate") is not None
            and r["system_rate"] >= BANK_SYSTEM_RATE
            and r["system_rate"] - r["others_system_rate"] >= BANK_SYSTEM_GAP
            and (bank["usual_system_rate"] is None or r["system_rate"] - bank["usual_system_rate"] >= BANK_SYSTEM_GAP)
        )


def bank_health(p, b):
    data = p.get("banks")
    if not data or not data["items"]:
        return []
    out = []
    everyone = data.get("all", data["items"])

    flagged = max((x for x in everyone if x.get("failing_now")), key=lambda x: x["recent"]["system_rate"], default=None)
    if flagged:
        r = flagged["recent"]
        out.append(insight(
            f"bank-{flagged['key']}", "banks", "bad" if r["system_rate"] >= 0.5 else "warn", "landmark",
            f"Transfers to {flagged['bank']} failing at {pct(r['system_rate'])} right now",
            f"{fmt(r['system_failed'])} of {fmt(r['settled'])} in the last {data['recent_minutes']} min failed with "
            f"bank-side errors (bank unavailable, timeouts); other banks at {pct(r['others_system_rate'])}. "
            f"Points to {flagged['bank']} or its NIP link.",
            70 + min((r["system_rate"] - r["others_system_rate"]) * 60, 25)))
    else:
        for bank in everyone:
            rate, usual, others = bank["system_rate"], bank.get("usual_system_rate"), bank.get("others_system_rate")
            if rate is None or others is None or bank["settled"] < BANK_MIN_DAY:
                continue
            if rate >= BANK_DAY_RATE and rate - others >= BANK_DAY_GAP and (usual is None or rate - usual >= BANK_DAY_GAP):
                was = f"Usually {pct(usual)}" if usual is not None else "No history for this bank"
                out.append(insight(f"bank-{bank['key']}", "banks", "warn", "landmark",
                                   f"Transfers to {bank['bank']} hitting bank-side errors today",
                                   f"{pct(rate)} of {fmt(bank['settled'])} transfers failed on the bank's side. {was}; "
                                   f"other banks at {pct(others)}. Points to {bank['bank']} or its NIP link.", 60))
                break

    top = data["items"][0]
    if data["total"]["count"] >= MIN_VOLUME:
        share = top["count"] / data["total"]["count"]
        out.append(insight("bank-top", "banks", "info", "landmark", f"{pct(share)} of transfers go to {top['bank']}",
                           f"{fmt(top['count'])} of {fmt(data['total']['count'])} transfers to other banks today, "
                           f"worth {naira(top['value'])}", 14))
    return out


RULES = 10


def build(p, b):
    flag_banks(p, b)
    typical = b["typical"]
    fc = forecast(p, typical)
    items = [
        *volume(p, typical, fc),
        *last_hour(p, typical),
        *failures(p),
        *reasons(p, b),
        *products(p, b),
        *onboarding(p, b),
        *geography(p),
        *rewards(p, b),
        *bank_health(p, b),
    ]
    items.sort(key=lambda i: -i["score"])
    return {
        "forecast": fc,
        "typical": {
            **{k: typical[k] for k in ("weekday", "days", "hourly_median", "hourly_low", "hourly_high", "so_far_median")},
            "signups_so_far": b.get("signups"),
            "accounts_so_far": b.get("accounts"),
        }
        if typical
        else None,
        "signals": RULES,
        "items": items[:10],
    }
