from calendar import monthrange
from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from .queries import LEGACY, fetch, lagos_now
from .report_data import (
    COMPARE,
    PARTIAL_KEYS,
    SMALL_BASE,
    Period,
    change,
    collect,
    notable_events,
    pct,
    ratio,
    recorded_from,
    safe,
    weekly,
)
from .report_pdf import (
    AQUA,
    BAD,
    BLUE,
    DEFINITIONS,
    GOOD,
    GREY,
    MARGIN,
    MUTED,
    ORANGE,
    S,
    SERIES,
    WIDTH,
    NumberedCanvas,
    bar_chart,
    callout,
    hbar_chart,
    hexcolor,
    kpi_cards,
    labels_for,
    line_chart,
    p,
    section,
    table,
)

UNITS = {"month": ("month", "months"), "quarter": ("quarter", "quarters")}
MAX_PERIODS = 6
MAX_OPTIONS = 24
RATE_KEYS = {"success_rate", "finish_rate", "average_value"}
MIN_BANK_TRANSFERS = 30
EVENTS_PER_PERIOD = 6
SUMS = ("transactions", "success", "failed", "settled", "value", "signups", "accounts")
EVENT_ORDER = ["Busiest day", "Highest value day", "Quietest day", "High failure day", "No transactions",
               "No accounts opened", "Failure burst", "Sign-up spike"]

DAILY = [
    ("Transactions", "transactions", "count", True),
    ("Successful transactions", "success", "count", True),
    ("Failed transactions", "failed", "count", False),
    ("Money sent by customers", "value", "money", True),
    ("Money in from other banks", "money_in", "money", True),
    ("Sign-ups started", "signups", "count", True),
    ("Accounts opened", "accounts", "count", True),
    ("Rewards paid", "rewards_value", "money", None),
]

EXTRA_DEFINITIONS = [
    ("Daily average", "a period's total divided by its number of days, so months of different lengths and a "
                      "period still in progress can be compared fairly."),
    ("So far", "a month or quarter that has not finished; it runs to the end of yesterday. Its totals are not "
               "compared with finished periods."),
    ("Incomplete (*)", "a figure that was only partly recorded in that period, so it is left out of comparisons."),
    ("Banks needing attention", "receiving banks with at least 30 transfers whose failure rate was well above the "
                                "average for all transfers to other banks in that period."),
]


class Slot(Period):
    def __init__(self, unit, start, end, today):
        last = today - timedelta(days=1)
        super().__init__(start, min(end, last))
        self.unit = unit
        self.partial = end > last
        self.key = f"{start:%Y-%m}" if unit == "month" else f"{start.year}-Q{(start.month - 1) // 3 + 1}"

    def name(self, so_far=True):
        base = f"{self.start:%b %Y}" if self.unit == "month" else f"Q{(self.start.month - 1) // 3 + 1} {self.start.year}"
        return f"{base} (so far)" if so_far and self.partial else base


def bounds(unit, day):
    if unit == "month":
        return date(day.year, day.month, 1), date(day.year, day.month, monthrange(day.year, day.month)[1])
    first = 3 * ((day.month - 1) // 3) + 1
    last = first + 2
    return date(day.year, first, 1), date(day.year, last, monthrange(day.year, last)[1])


def first_day():
    rows = safe(lambda: fetch(f"SELECT CREATED AS d FROM {LEGACY} ORDER BY ID LIMIT 1", {}))
    return rows[0]["d"].date() if rows and rows[0]["d"] else None


def available(unit, today=None, first=None):
    today = today or lagos_now().date()
    yesterday = today - timedelta(days=1)
    first = first or first_day() or yesterday - timedelta(days=365)
    out = []
    start, end = bounds(unit, yesterday)
    while end >= first and len(out) < MAX_OPTIONS:
        out.append(Slot(unit, start, end, today))
        start, end = bounds(unit, start - timedelta(days=1))
    return out


def choose(unit, span, keys=(), include_current=False, today=None, first=None):
    options = available(unit, today, first)
    word = UNITS[unit][1]
    if span == "pick":
        chosen = [s for s in options if s.key in set(keys)]
    else:
        pool = options if include_current else [s for s in options if not s.partial]
        chosen = pool[:int(span)]
    if len(chosen) < 2:
        raise ValueError(f"Choose at least two {word} to compare.")
    if len(chosen) > MAX_PERIODS:
        raise ValueError(f"Choose up to {MAX_PERIODS} {word}.")
    return sorted(chosen, key=lambda s: s.start)


TOTAL_KEYS = {key for _, key, _, _, _ in COMPARE} - RATE_KEYS


def incomplete_keys(slot, since):
    if since.get("transactions") and since["transactions"] > slot.start:
        return set(TOTAL_KEYS)
    return {k for source, keys in PARTIAL_KEYS.items()
            if since.get(source) and since[source] > slot.start for k in keys}


def measure_rows(slots, cols, gaps):
    rows = []
    for label, key, kind, points, up_is_good in COMPARE:
        values = [c["totals"].get(key) for c in cols]
        if key == "money_in_other" and not any(values):
            continue
        cells = []
        for i, v in enumerate(values):
            cell = {"value": v, "incomplete": key in gaps[i], "change": None, "why": None}
            if i:
                if key in gaps[i] or key in gaps[i - 1]:
                    cell["why"] = "incomplete"
                elif key not in RATE_KEYS and (slots[i].partial or slots[i - 1].partial):
                    cell["why"] = "so far"
                else:
                    cell["change"] = change(v, values[i - 1], points)
            cells.append(cell)
        rows.append({"metric": label, "key": key, "kind": kind, "points": points, "up_is_good": up_is_good,
                     "cells": cells})
    return rows


def daily_rows(slots, cols, gaps):
    rows = []
    for label, key, kind, up_is_good in DAILY:
        values = [None if c["totals"].get(key) is None else c["totals"][key] / s.days for s, c in zip(slots, cols)]
        cells = []
        for i, v in enumerate(values):
            cell = {"value": v, "incomplete": key in gaps[i], "change": None, "why": None}
            if i:
                if key in gaps[i] or key in gaps[i - 1]:
                    cell["why"] = "incomplete"
                else:
                    cell["change"] = change(v, values[i - 1])
            cells.append(cell)
        rows.append({"metric": label, "key": key, "kind": kind, "points": False, "up_is_good": up_is_good,
                     "cells": cells})
    return rows


def reason_rows(cols, limit=10):
    totals, info, per = {}, {}, []
    for c in cols:
        here = {r["reason"]: r for r in c["reasons"]}
        per.append(here)
        for k, r in here.items():
            totals[k] = totals.get(k, 0) + r["count"]
            info[k] = r
    top = sorted(totals, key=lambda k: -totals[k])[:limit]
    return [{
        "reason": k,
        "side": info[k]["side"],
        "hint": info[k].get("hint", ""),
        "counts": [h[k]["count"] if k in h else 0 for h in per],
        "values": [h[k]["value"] if k in h else 0.0 for h in per],
        "worst": [h[k].get("worst_day") if k in h else None for h in per],
    } for k in top]


def side_rows(cols):
    out = {}
    for i, c in enumerate(cols):
        for r in c["reasons"]:
            out.setdefault(r["side"], [0] * len(cols))[i] += r["count"]
    return sorted(out.items(), key=lambda kv: -sum(kv[1]))


def product_rows(cols):
    names, by = {}, []
    for c in cols:
        here = {r["product"]: r for r in c["products"]}
        by.append(here)
        for k, r in here.items():
            names[k] = names.get(k, 0) + r["count"]
    return [{"product": k, "cells": [b.get(k) for b in by]} for k in sorted(names, key=lambda k: -names[k])]


def bank_rows(cols, limit=10):
    names, by = {}, []
    for c in cols:
        here = {b["bank"]: b for b in c["banks"]}
        by.append(here)
        for k, b in here.items():
            names[k] = names.get(k, 0) + b["count"]
    return [{"bank": k, "cells": [b.get(k) for b in by]} for k in sorted(names, key=lambda k: -names[k])[:limit]]


def inter_rate(col):
    settled = sum(b["success"] + b["failed"] for b in col["banks"])
    return ratio(sum(b["failed"] for b in col["banks"]), settled)


def watch_list(col):
    normal = inter_rate(col)
    if normal is None:
        return []
    found = [b for b in col["banks"] if b["count"] >= MIN_BANK_TRANSFERS and b["failure_rate"] is not None
             and b["failure_rate"] >= max(normal * 1.25, normal + 0.03)]
    return [{**b, "above": b["failure_rate"] - normal} for b in sorted(found, key=lambda b: -b["failure_rate"])[:5]]


def stage_rows(cols):
    order = [s["stage"] for s in cols[-1]["funnel"]] or [s["stage"] for c in cols for s in c["funnel"]]
    by = [{s["stage"]: s for s in c["funnel"]} for c in cols]
    return [{"stage": k, "cells": [b.get(k) for b in by]} for k in dict.fromkeys(order)]


def stuck_rows(cols):
    totals, by = {}, []
    for c in cols:
        here = {s["step"]: s for s in c["stuck"]}
        by.append(here)
        for k, s in here.items():
            totals[k] = totals.get(k, 0) + s["count"]
    return [{"step": k, "cells": [b.get(k) for b in by]} for k in sorted(totals, key=lambda k: -totals[k])]


def reward_rows(cols):
    totals, by = {}, []
    for c in cols:
        here = {r["type"]: r for r in c["rewards"]}
        by.append(here)
        for k, r in here.items():
            totals[k] = totals.get(k, 0) + r["value"]
    return [{"type": k, "cells": [b.get(k) for b in by]} for k in sorted(totals, key=lambda k: -totals[k])]


def by_month(series):
    out = {}
    for s in series:
        key = s["date"].replace(day=1)
        m = out.setdefault(key, {"date": key, "days": 0, "money_in": None, **dict.fromkeys(SUMS, 0)})
        m["days"] += 1
        for k in SUMS:
            m[k] += s[k]
        if s["money_in"] is not None:
            m["money_in"] = (m["money_in"] or 0) + s["money_in"]
    for m in out.values():
        m["success_rate"] = ratio(m["success"], m["settled"])
    return [out[k] for k in sorted(out)]


def top_events(col):
    events = notable_events(col)
    rank = {kind: i for i, kind in enumerate(EVENT_ORDER)}
    keep = sorted(events, key=lambda e: (rank.get(e[0], len(EVENT_ORDER)), e[1]))[:EVENTS_PER_PERIOD]
    return sorted(keep, key=lambda e: e[1])


def words_money(v):
    if v is None:
        return "n/a"
    if abs(v) >= 1e9:
        return f"NGN {v / 1e9:,.2f} billion"
    if abs(v) >= 1e6:
        return f"NGN {v / 1e6:,.1f} million"
    return f"NGN {v:,.0f}"


def count(v):
    return "n/a" if v is None else f"{v:,.0f}"


def moved(c, points=False):
    if points:
        if abs(c) < 0.005:
            return "about the same as"
        return f"{abs(c) * 100:.1f} points {'up' if c > 0 else 'down'} from"
    if abs(c) < 0.02:
        return "about the same as"
    return f"{'up' if c > 0 else 'down'} {abs(c) * 100:.0f}% from"


def versus(report, key, lead, fmt):
    slots = report["slots"]
    r = report["by_key"][key]
    a, b = r["cells"][-2], r["cells"][-1]
    last, prev = slots[-1], slots[-2]
    if b["change"] is not None:
        return f"{lead} {fmt(b['value'])} in {last.name()}, {moved(b['change'], r['points'])} {prev.name()} " \
               f"({fmt(a['value'])})."
    if b["why"] == "so far":
        d = report["daily_by_key"].get(key)
        if d and d["cells"][-1]["change"] is not None:
            return f"{lead} {fmt(b['value'])} so far in {last.name(False)}, about {fmt(d['cells'][-1]['value'])} " \
                   f"a day, {moved(d['cells'][-1]['change'])} {prev.name()}'s daily average."
        return f"{lead} {fmt(b['value'])} so far in {last.name(False)}."
    return f"{lead} {fmt(b['value'])} in {last.name()}. {prev.name()} was not fully recorded, so there is no fair " \
           f"comparison."


def across(report, key, label, fmt):
    slots = report["slots"]
    if len(slots) < 3:
        return ""
    cells = report["by_key"][key]["cells"]
    usable = [i for i, c in enumerate(cells) if not c["incomplete"] and not slots[i].partial and c["value"] is not None]
    if len(usable) < 3:
        return ""
    a, b = usable[0], usable[-1]
    c = change(cells[b]["value"], cells[a]["value"])
    if c is None:
        return ""
    return f" Across the {len(usable)} full {UNITS[slots[0].unit][1]}, {label} went from {fmt(cells[a]['value'])} in " \
           f"{slots[a].name()} to {fmt(cells[b]['value'])} in {slots[b].name()} ({'+' if c >= 0 else '−'}" \
           f"{abs(c) * 100:.0f}%)."


def findings(slots, cols, rows, daily):
    out = []
    names = [s.name() for s in slots]
    by_key = {r["key"]: r for r in rows}
    per_day = {r["key"]: r for r in daily}
    word = UNITS[slots[0].unit]
    out.append(f"This report compares {len(slots)} {word[1]}, from {names[0]} to {names[-1]}.")
    last, prev = slots[-1], slots[-2]

    def change_line(label, key, fmt):
        cell = by_key[key]["cells"][-1]
        if cell["change"] is not None:
            c = cell["change"]
            before, now = by_key[key]["cells"][-2]["value"], cell["value"]
            if abs(c) < 0.02:
                out.append(f"{label} was steady between {prev.name()} and {last.name()} at {fmt(now)}.")
            else:
                out.append(f"{label} {'rose' if c > 0 else 'fell'} {abs(c) * 100:.0f}% from {prev.name()} to "
                           f"{last.name()} ({fmt(before)} to {fmt(now)}).")
        elif cell["why"] == "so far" and key in per_day:
            a, b = per_day[key]["cells"][-2]["value"], per_day[key]["cells"][-1]["value"]
            if a is not None and b is not None:
                out.append(f"So far in {last.name(False)}, {label[0].lower()}{label[1:]}: {fmt(b)} a day on "
                           f"average, against {fmt(a)} a day in {prev.name()}.")

    change_line("Transactions", "transactions", lambda v: f"{v:,.0f}")
    change_line("Money sent by customers", "value", words_money)
    change_line("Accounts opened", "accounts", lambda v: f"{v:,.0f}")
    rate = by_key["success_rate"]["cells"]
    if rate[-1]["value"] is not None and rate[-2]["value"] is not None:
        diff = (rate[-1]["value"] - rate[-2]["value"]) * 100
        if abs(diff) < 0.5:
            out.append(f"Success rate held at {pct(rate[-1]['value'])} in {last.name()}.")
        else:
            out.append(f"Success rate {'rose' if diff > 0 else 'fell'} to {pct(rate[-1]['value'])} in {last.name()} "
                       f"({abs(diff):.1f} points {'up' if diff > 0 else 'down'} from {prev.name()}).")

    full = [i for i, s in enumerate(slots) if not s.partial]
    if len(full) >= 3:
        def best(key, pick=max, skip_gaps=False):
            pool = [i for i in full if by_key[key]["cells"][i]["value"] is not None
                    and not (skip_gaps and by_key[key]["cells"][i]["incomplete"])]
            return pick(pool, key=lambda i: by_key[key]["cells"][i]["value"]) if pool else None

        i = best("transactions", skip_gaps=True)
        if i is not None:
            out.append(f"The busiest {word[0]} was {names[i]} with {by_key['transactions']['cells'][i]['value']:,} "
                       f"transactions.")
        i = best("value", skip_gaps=True)
        if i is not None:
            out.append(f"Customers sent the most money in {names[i]}: "
                       f"{words_money(by_key['value']['cells'][i]['value'])}.")
        hi, lo = best("success_rate"), best("success_rate", min)
        if hi is not None and hi != lo:
            out.append(f"Success rate was best in {names[hi]} ({pct(rate[hi]['value'])}) and worst in {names[lo]} "
                       f"({pct(rate[lo]['value'])}).")
        i = best("accounts", skip_gaps=True)
        if i is not None:
            out.append(f"The most accounts were opened in {names[i]} "
                       f"({by_key['accounts']['cells'][i]['value']:,}).")

    if not last.partial:
        growth = []
        for r in reason_rows(cols, limit=20):
            before, now = r["counts"][-2], r["counts"][-1]
            if now >= 30 and now > before:
                growth.append((now - before, r["reason"], before, now))
        if growth:
            _, reason, before, now = max(growth)
            out.append(f"The failure reason that grew most in {last.name()} was \"{reason}\" "
                       f"({before:,} to {now:,}).")
    return out


def notes(slots, cols, gaps, since):
    out = []
    began = since.get("transactions")
    early = [s.name(False) for s in slots if began and began > s.start]
    if early:
        out.append(f"Records begin on {began:%d %B %Y}, so {', '.join(early)} is only partly covered. Its totals "
                   f"are marked * and left out of comparisons; rates such as the success rate still apply.")
    for source, label in (("accounts", "Account opening dates"), ("money_in", "Money in from other banks")):
        hit = [s.name(False) for s, g in zip(slots, gaps)
               if PARTIAL_KEYS[source][0] in g and not (began and began > s.start)]
        if hit:
            out.append(f"{label} {'are' if source == 'accounts' else 'is'} only recorded from "
                       f"{since[source]:%d %B %Y}, so {', '.join(hit)} {'is' if len(hit) == 1 else 'are'} incomplete "
                       f"for that figure. These are marked * and left out of comparisons.")
    full = [(s, c) for s, c, g in zip(slots, cols, gaps) if not s.partial and "transactions" not in g]
    if len(full) >= 2:
        (first, a), (last, b) = full[0], full[-1]
        before, now = a["totals"]["transactions"], b["totals"]["transactions"]
        if now and before < now * SMALL_BASE:
            out.append(f"{first.name()} had far less activity than {last.name()} ({before:,} transactions against "
                       f"{now:,}), so large percentage changes mostly reflect growth from a small starting point.")
    for s in slots:
        if s.partial:
            out.append(f"{s.name(False)} is not finished; its figures run to {s.end:%d %B %Y}. Its totals are not "
                       f"compared with finished {UNITS[s.unit][1]}; use the daily averages instead.")
    lengths = {s.days for s in slots if not s.partial}
    if len(lengths) > 1:
        out.append(f"The {UNITS[slots[0].unit][1]} compared have different numbers of days "
                   f"({min(lengths)} to {max(lengths)}), so the daily averages give the fairest comparison.")
    absurd = sum(r["absurd"] for c in cols for r in c["reasons"])
    if absurd:
        out.append(f"{absurd:,} failed attempts had impossible amounts (over NGN 100,000,000), usually mistyped; "
                   f"they are counted as failures but left out of failure values.")
    if any(c["totals"].get("money_in_other") for c in cols):
        out.append("Money in counts only transfers into app customers' accounts. Transfers into other Dash accounts, "
                   "such as treasury or fixed-deposit accounts, are shown on their own line.")
    if any(c["totals"].get("active_users") is None for c in cols):
        out.append("Customers who signed in could not be counted for every period (the query took too long).")
    return out


def build(unit, slots, generated_by=""):
    cols = [collect(s) for s in slots]
    since = {**recorded_from(), "transactions": first_day()}
    gaps = [incomplete_keys(s, since) for s in slots]
    rows = measure_rows(slots, cols, gaps)
    daily = daily_rows(slots, cols, gaps)
    per_day = {r["key"]: r["cells"][-1] for r in daily}
    comparison = []
    for r in rows:
        a, b = r["cells"][-2], r["cells"][-1]
        item = {"metric": r["metric"], "key": r["key"], "kind": r["kind"], "now": b["value"],
                "before": a["value"], "change": b["change"], "points": r["points"],
                "up_is_good": r["up_is_good"], "comparable": b["why"] is None}
        if b["why"] == "so far" and per_day.get(r["key"], {}).get("change") is not None:
            item.update(change=per_day[r["key"]]["change"], comparable=True, suffix=" a day vs previous")
        comparison.append(item)
    series = [s for c in cols for s in c["series"]]
    weeks = weekly(series)
    for w in weeks:
        w["failure_rate"] = ratio(w["failed"], w["settled"])
    return {
        "unit": unit,
        "slots": slots,
        "columns": cols,
        "gaps": gaps,
        "period": Period(slots[0].start, slots[-1].end),
        "header": "Dash MFB · Period Comparison",
        "rows": rows,
        "daily": daily,
        "by_key": {r["key"]: r for r in rows},
        "daily_by_key": {r["key"]: r for r in daily},
        "comparison": comparison,
        "reasons": reason_rows(cols),
        "sides": side_rows(cols),
        "products": product_rows(cols),
        "banks": bank_rows(cols),
        "watch": [watch_list(c) for c in cols],
        "stages": stage_rows(cols),
        "stuck": stuck_rows(cols),
        "rewards": reward_rows(cols),
        "events": [top_events(c) for c in cols],
        "weeks": weeks,
        "months": by_month(series) if unit == "quarter" else [],
        "findings": findings(slots, cols, rows, daily),
        "notes": notes(slots, cols, gaps, since),
        "generated_at": lagos_now(),
        "generated_by": generated_by,
    }


def compact(kind, v):
    if v is None:
        return "n/a"
    if kind == "pct":
        return pct(v)
    if kind == "money":
        if abs(v) >= 1e9:
            return f"NGN {v / 1e9:,.2f}bn"
        if abs(v) >= 1e6:
            return f"NGN {v / 1e6:,.1f}m"
        return f"NGN {v:,.0f}"
    return f"{v:,.0f}" if abs(v) >= 100 or float(v).is_integer() else f"{v:,.1f}"


CHART_PERIODS = 3


def cash(v, many):
    if v is not None and many and 1e4 <= abs(v) < 1e6:
        return f"NGN {v / 1e3:,.0f}k"
    return compact("money", v)


def quiet(text):
    return f"<font size='6.5' color='{hexcolor(MUTED)}'>{text}</font>"


def stacked(main, sub):
    return f"{main}<br/>{quiet(sub)}" if sub else main


def change_html(row, cell):
    if cell["why"]:
        return f'<font color="{hexcolor(MUTED)}">{cell["why"]}</font>'
    c = cell["change"]
    if c is None:
        return ""
    if row["points"]:
        text, flat = f"{'+' if c >= 0 else '−'}{abs(c) * 100:.1f} pts", abs(c) < 0.005
    else:
        text, flat = f"{'+' if c >= 0 else '−'}{abs(c) * 100:.1f}%", abs(c) < 0.01
    if flat or row["up_is_good"] is None:
        color = MUTED
    else:
        color = GOOD if (c > 0) == row["up_is_good"] else BAD
    return f'<font color="{hexcolor(color)}">{text}</font>'


def numeric(n):
    return tuple(range(1, n + 1))


def grid(slots, rows):
    if len(slots) == 2:
        data = []
        for r in rows:
            a, b = r["cells"]
            data.append([escape(r["metric"]),
                         compact(r["kind"], a["value"]) + ("*" if a["incomplete"] else ""),
                         compact(r["kind"], b["value"]) + ("*" if b["incomplete"] else ""),
                         Paragraph(change_html(r, b) or "", S["cell_r"])])
        return table(["Measure", slots[0].name(), slots[1].name(), "Change"], data,
                     [WIDTH * 0.40, WIDTH * 0.21, WIDTH * 0.21, WIDTH * 0.18], numeric=numeric(3))
    width = 0.72 / len(slots)
    data = []
    for r in rows:
        line = [escape(r["metric"])]
        for cell in r["cells"]:
            value = compact(r["kind"], cell["value"]) + ("*" if cell["incomplete"] else "")
            extra = change_html(r, cell)
            line.append(Paragraph(f"{value}<br/><font size='6.5'>{extra}</font>" if extra else value, S["cell_r"]))
        data.append(line)
    return table(["Measure"] + [s.name() for s in slots], data, [WIDTH * 0.28] + [WIDTH * width] * len(slots),
                 numeric=numeric(len(slots)))


def per_period_table(slots, label, rows, first=0.34):
    width = (1 - first) / len(slots)
    return table([label] + [s.name() for s in slots], rows, [WIDTH * first] + [WIDTH * width] * len(slots),
                 numeric=numeric(len(slots)))


def chart_block(*items):
    return KeepTogether([Spacer(1, 3 * mm), *items])


def short_names(slots):
    return [s.name(False) for s in slots]


def counts_label(v):
    return f"{v:,.0f}"


def millions_label(v):
    return f"{v:,.0f}m" if v >= 10 else f"{v:,.1f}m"


def transactions_part(report, n):
    slots, cols = report["slots"], report["columns"]
    t = [c["totals"] for c in cols]
    last = slots[-1]
    out = section(f"{n}. Transactions")
    text = versus(report, "transactions", "Customers made", lambda v: f"{count(v)} transactions")
    text += " " + versus(report, "success_rate", "The success rate was", pct)
    text += across(report, "transactions", "transactions", count)
    out.append(p(escape(text)))
    products = [r for r in report["products"] if r["cells"][-1]]
    if products:
        worst = max((r for r in products if r["cells"][-1]["count"] >= 30),
                    key=lambda r: r["cells"][-1]["failure_rate"] or 0, default=None)
        biggest = max(products, key=lambda r: r["cells"][-1]["count"])
        line = (f"<b>Key point:</b> {escape(biggest['product'])} made up "
                f"{pct(biggest['cells'][-1]['share'], 0)} of transactions in {escape(last.name())}.")
        if worst:
            line += (f" The product with the highest failure rate was {escape(worst['product'])} "
                     f"({pct(worst['cells'][-1]['failure_rate'])}).")
        out += [Spacer(1, 2 * mm), callout(line)]
    out.append(chart_block(bar_chart(
        f"Transactions per {UNITS[report['unit']][0]}", slots,
        [("Successful", [x["success"] for x in t], BLUE),
         ("Failed", [x["failed"] for x in t], ORANGE),
         ("Reversed or pending", [x["transactions"] - x["success"] - x["failed"] for x in t], GREY)],
        stacked=True, labels=short_names(slots))))
    weeks = [w for w in report["weeks"] if w["success_rate"] is not None]
    if len(weeks) >= 3:
        rates = [w["success_rate"] * 100 for w in weeks]
        out.append(chart_block(line_chart(
            "Success rate, week by week (dated by week start)", labels_for([w["date"] for w in weeks]),
            [("Success rate", rates, BLUE)], lambda v: f"{v:.0f}%",
            value_min=max(0, int(min(rates) // 5 * 5) - 5), value_max=100)))
    out += [Spacer(1, 2 * mm), p("By product", "h2"),
            p("Each cell shows the number of transactions, the value successfully sent, and the failure rate.")]
    out.append(Spacer(1, 2 * mm))
    out.append(per_period_table(slots, "Product", [
        [escape(r["product"])] + [
            "—" if c is None else
            f"{c['count']:,}<br/>{quiet(cash(c['value'], len(slots) > 3))}<br/>"
            f"{quiet(pct(c['failure_rate']) + ' failed')}"
            for c in r["cells"]]
        for r in report["products"]], first=0.28))
    return out


def money_part(report, n):
    slots, cols = report["slots"], report["columns"]
    t = [c["totals"] for c in cols]
    word = UNITS[report["unit"]][0]
    out = section(f"{n}. Money movement")
    text = versus(report, "value", "Customers sent", words_money)
    if all(x["money_in"] is not None for x in t):
        text += " " + versus(report, "money_in", "Money in from other banks was", words_money)
    text += across(report, "value", "money sent", words_money)
    out.append(p(escape(text)))
    a = report["by_key"]["average_value"]["cells"]
    if a[-1]["value"] is not None and a[-2]["value"] is not None:
        out += [Spacer(1, 2 * mm), callout(
            f"<b>Key point:</b> the average successful transaction was {escape(words_money(a[-1]['value']))} in "
            f"{escape(slots[-1].name())}, against {escape(words_money(a[-2]['value']))} in {escape(slots[-2].name())}. "
            f"Money sent covers only the app; customers can also move money through internet banking or the branch, "
            f"so money in and money sent should not be netted.")]
    series = [("Money sent", [x["value"] / 1e6 for x in t], BLUE)]
    if all(x["money_in"] is not None for x in t):
        series.append(("Money in", [x["money_in"] / 1e6 for x in t], AQUA))
    out.append(chart_block(bar_chart(f"Money per {word} (NGN millions)", slots, series, unit="m",
                                     labels=short_names(slots), value_labels=millions_label)))
    weeks = report["weeks"]
    if len(weeks) >= 3:
        series = [("Money sent", [w["value"] / 1e6 for w in weeks], BLUE)]
        if all(w["money_in"] is not None for w in weeks):
            series.append(("Money in", [w["money_in"] / 1e6 for w in weeks], AQUA))
        out.append(chart_block(bar_chart("Money week by week (NGN millions, dated by week start)", weeks, series,
                                         unit="m")))
    rows = [
        ["Money sent by customers"] + [compact("money", x["value"]) for x in t],
        ["Successful transactions"] + [count(x["success"]) for x in t],
        ["Average successful transaction"] + [compact("money", x["average_value"]) for x in t],
    ]
    if all(x["money_in"] is not None for x in t):
        gaps = report["gaps"]
        mark = lambda i: "*" if "money_in" in gaps[i] else ""
        rows += [
            ["Money in from other banks"] + [compact("money", x["money_in"]) + mark(i) for i, x in enumerate(t)],
            ["Transfers received"] + [count(x["money_in_count"]) + mark(i) for i, x in enumerate(t)],
            ["Average transfer received"] + [compact("money", ratio(x["money_in"], x["money_in_count"])) + mark(i)
                                             for i, x in enumerate(t)],
        ]
        if any(x.get("money_in_other") for x in t):
            rows.append(["Received into other Dash accounts"] +
                        [compact("money", x.get("money_in_other")) + mark(i) for i, x in enumerate(t)])
    out += [Spacer(1, 2 * mm), per_period_table(slots, "Measure", rows, first=0.30)]
    return out


def failures_part(report, n):
    slots, cols = report["slots"], report["columns"]
    t = [c["totals"] for c in cols]
    word = UNITS[report["unit"]][0]
    out = section(f"{n}. Failed transactions")
    text = versus(report, "failed", "There were", lambda v: f"{count(v)} failed transactions")
    rate = [x["failure_rate"] for x in t]
    if rate[-1] is not None:
        text += f" That is {pct(rate[-1])} of transactions with a final outcome"
        text += f", against {pct(rate[-2])} in {slots[-2].name()}." if rate[-2] is not None else "."
    out.append(p(escape(text)))
    reasons = report["reasons"]
    if reasons and not slots[-1].partial:
        growth = max(reasons, key=lambda r: r["counts"][-1] - r["counts"][-2])
        bank_side = sum(v[-1] for side, v in report["sides"] if side == "Bank or partner")
        line = (f"<b>Key point:</b> \"{escape(growth['reason'])}\" changed the most, from "
                f"{growth['counts'][-2]:,} to {growth['counts'][-1]:,}.")
        if t[-1]["failed"]:
            line += (f" {pct(bank_side / t[-1]['failed'], 0)} of {escape(slots[-1].name())}'s failures were on the "
                     f"bank or partner side, which Dash and its partners can act on.")
        out += [Spacer(1, 2 * mm), callout(line)]
    sides = report["sides"]
    colors = {"Customer": BLUE, "Bank or partner": ORANGE, "Account restriction": AQUA}
    series = [(side, values, colors.get(side, GREY)) for side, values in sides if side in colors]
    rest = [sum(v[i] for side, v in sides if side not in colors) for i in range(len(slots))]
    if any(rest):
        series.append(("Other or not recorded", rest, GREY))
    out.append(chart_block(bar_chart(f"Failures per {word}, by who caused them", slots, series, stacked=True,
                                     labels=short_names(slots))))
    top = reasons[:6]
    if top:
        shown = list(enumerate(slots))[-CHART_PERIODS:]
        title = f"Main failure reasons per {word}"
        if len(slots) > CHART_PERIODS:
            title += f" (latest {CHART_PERIODS} {UNITS[report['unit']][1]}; all are in the table below)"
        out.append(chart_block(hbar_chart(
            title, [r["reason"] for r in top],
            [(s.name(False), [r["counts"][i] for r in top], SERIES[k]) for k, (i, s) in enumerate(shown)],
            counts_label)))
    weeks = [w for w in report["weeks"] if w["failure_rate"] is not None]
    if len(weeks) >= 3:
        rates = [w["failure_rate"] * 100 for w in weeks]
        out.append(chart_block(line_chart(
            "Failure rate, week by week (dated by week start)", labels_for([w["date"] for w in weeks]),
            [("Failure rate", rates, ORANGE)], lambda v: f"{v:.0f}%", value_min=0,
            value_max=max(10, int(max(rates) // 5 * 5) + 5))))
    out += [Spacer(1, 2 * mm), p("Failure reasons in detail", "h2"),
            p("What each reason means, and how many failures it caused in each period, with the value of those "
              "transactions underneath.")]
    out.append(Spacer(1, 2 * mm))
    out.append(per_period_table(slots, "Reason", [
        [Paragraph(f"<b>{escape(r['reason'])}</b> · {escape(r['side'])}<br/>"
                   f"<font color='{hexcolor(MUTED)}'>{escape(r['hint'])}</font>", S["cell"])] +
        [stacked(f"{c:,}", cash(v, len(slots) > 3)) for c, v in zip(r["counts"], r["values"])]
        for r in reasons], first=0.40))
    return out


def banks_part(report, n):
    slots, cols = report["slots"], report["columns"]
    out = section(f"{n}. Transfers to other banks")
    rates = [inter_rate(c) for c in cols]
    text = (f"Transfers to other banks failed {pct(rates[-1])} of the time in {slots[-1].name()}"
            + (f", against {pct(rates[-2])} in {slots[-2].name()}." if rates[-2] is not None else ".")
            + " A high failure rate at one bank usually points to that bank or the NIP network rather than to Dash.")
    out.append(p(escape(text)))
    watch = report["watch"][-1]
    if watch:
        b = watch[0]
        out += [Spacer(1, 2 * mm), callout(
            f"<b>Key point:</b> in {escape(slots[-1].name())}, {escape(b['bank'])} had the worst failure rate at "
            f"{pct(b['failure_rate'])} across {b['count']:,} transfers, {b['above'] * 100:.1f} points above "
            f"the average.")]
    out += [Spacer(1, 3 * mm), per_period_table(slots, "Receiving bank", [
        [escape(r["bank"])] + [
            "—" if c is None or c["count"] < MIN_BANK_TRANSFERS
            else stacked(pct(c["failure_rate"]), f"{c['count']:,} sent" if len(slots) > 3
                         else f"{c['count']:,} sent · {compact('money', c['value'])}")
            for c in r["cells"]]
        for r in report["banks"]], first=0.28)]
    rows = [[escape(s.name()), escape(b["bank"]), f"{b['count']:,}", pct(b["failure_rate"]),
             f"{b['above'] * 100:.1f} pts"]
            for s, found in zip(slots, report["watch"]) for b in found]
    heading = p("Banks needing attention", "h2")
    if rows:
        out.append(KeepTogether([heading, table(
            ["Period", "Receiving bank", "Transfers", "Failure rate", "Above average by"], rows,
            [WIDTH * w for w in (0.18, 0.34, 0.16, 0.16, 0.16)], numeric=(2, 3, 4))]))
    else:
        out.append(KeepTogether([heading, p("No bank stood out in any period.")]))
    return out


def onboarding_part(report, n):
    slots, cols = report["slots"], report["columns"]
    t = [c["totals"] for c in cols]
    word = UNITS[report["unit"]][0]
    out = section(f"{n}. Customers and onboarding")
    text = versus(report, "signups", "People started", lambda v: f"{count(v)} sign-ups")
    text += " " + versus(report, "accounts", "Customers opened", lambda v: f"{count(v)} accounts")
    text += " " + versus(report, "finish_rate", "The share of sign-ups that finished was", pct)
    if all(x["active_users"] is not None for x in t):
        text += " " + versus(report, "active_users", "Account holders who signed in numbered", count)
    out.append(p(escape(text)))
    stuck = [s for s in report["stuck"] if s["cells"][-1]]
    if stuck:
        top = max(stuck, key=lambda s: s["cells"][-1]["count"])
        out += [Spacer(1, 2 * mm), callout(
            f"<b>Key point:</b> the biggest drop-off in {escape(slots[-1].name())} was "
            f"\"{escape(top['step'])}\": {top['cells'][-1]['count']:,} people "
            f"({pct(top['cells'][-1]['share'], 0)} of sign-ups) stopped there.")]
    out.append(chart_block(bar_chart(
        f"Sign-ups and accounts opened per {word}", slots,
        [("Sign-ups started", [x["signups"] for x in t], BLUE), ("Accounts opened", [x["accounts"] for x in t], AQUA)],
        labels=short_names(slots), value_labels=counts_label)))
    weeks = report["weeks"]
    if len(weeks) >= 3:
        out.append(chart_block(bar_chart(
            "Sign-ups and accounts opened, week by week (dated by week start)", weeks,
            [("Sign-ups started", [w["signups"] for w in weeks], BLUE),
             ("Accounts opened", [w["accounts"] for w in weeks], AQUA)])))
    out += [Spacer(1, 2 * mm), p("Onboarding funnel", "h2"),
            p("People who started signing up in each period, and how many reached each step.")]
    out.append(Spacer(1, 2 * mm))
    out.append(per_period_table(slots, "Step", [
        [escape(r["stage"])] + ["—" if c is None else stacked(f"{c['count']:,}", pct(c["share"])) for c in r["cells"]]
        for r in report["stages"]]))
    if report["stuck"]:
        out += [p("Where people stopped", "h2"), Spacer(1, 1 * mm), per_period_table(slots, "Last step reached", [
            [escape(r["step"])] + ["—" if c is None else stacked(f"{c['count']:,}", pct(c["share"]))
                                   for c in r["cells"]]
            for r in report["stuck"]])]
    return out


def rewards_part(report, n):
    slots, cols = report["slots"], report["columns"]
    t = [c["totals"] for c in cols]
    out = section(f"{n}. Rewards")
    text = versus(report, "rewards_value", "Rewards paid to customers came to", words_money)
    per_account = [ratio(x["rewards_value"], x["accounts"]) for x in t]
    if per_account[-1] is not None:
        text += (f" That is about {words_money(per_account[-1])} for every account opened in "
                 f"{slots[-1].name()}.")
    out.append(p(escape(text)))
    if report["rewards"]:
        many = len(slots) > 3
        rows = [[escape(r["type"])] + ["—" if c is None else stacked(cash(c["value"], many), f"{c['count']:,} payouts")
                                       for c in r["cells"]] for r in report["rewards"]]
        rows.append(["<b>Total</b>"] + [stacked(f"<b>{cash(x['rewards_value'], many)}</b>",
                                                f"{x['rewards_count']:,} payouts") for x in t])
        out += [Spacer(1, 3 * mm), per_period_table(slots, "Reward", rows)]
    return out


def events_part(report, n):
    slots = report["slots"]
    out = section(f"{n}. Notable events")
    out.append(p("The days that stood out in each period: the busiest and quietest, days with many failures, "
                 "and sudden spikes in sign-ups."))
    rows = [[escape(s.name(False)), f"{d:%a %d %b}", escape(kind), escape(detail)]
            for s, events in zip(slots, report["events"]) for kind, d, detail in events]
    out.append(Spacer(1, 2 * mm))
    if rows:
        out.append(table(["Period", "Date", "Event", "Detail"], rows,
                         [WIDTH * w for w in (0.13, 0.13, 0.20, 0.54)]))
    else:
        out.append(p("Nothing unusual was detected."))
    return out


def appendix(report):
    out = []
    if report["months"]:
        out += [PageBreak(), p("Appendix A. Month by month", "h1"),
                p("The months inside the quarters compared, so the trend within each quarter is visible.")]
        rows = [[f"{m['date']:%b %Y}", count(m["transactions"]), pct(m["success_rate"]), count(m["failed"]),
                 compact("money", m["value"]), compact("money", m["money_in"]), count(m["signups"]),
                 count(m["accounts"])] for m in report["months"]]
        out += [Spacer(1, 2 * mm), table(
            ["Month", "Transactions", "Success rate", "Failed", "Money sent", "Money in", "Sign-ups", "Accounts"],
            rows, [WIDTH * w for w in (0.12, 0.13, 0.12, 0.10, 0.15, 0.15, 0.11, 0.12)], numeric=numeric(7))]
    letter = "B" if report["months"] else "A"
    out += [PageBreak() if not report["months"] else Spacer(1, 6 * mm),
            p(f"Appendix {letter}. Week by week", "h1"),
            p("Weeks run Monday to Sunday and are dated by their first day; the first and last weeks may be "
              "partial.")]
    rows = [[f"{w['date']:%d %b %Y}", count(w["transactions"]), pct(w["success_rate"]), count(w["failed"]),
             compact("money", w["value"]), compact("money", w["money_in"]), count(w["signups"]), count(w["accounts"])]
            for w in report["weeks"]]
    out += [Spacer(1, 2 * mm), table(
        ["Week of", "Transactions", "Success rate", "Failed", "Money sent", "Money in", "Sign-ups", "Accounts"],
        rows, [WIDTH * w for w in (0.14, 0.13, 0.12, 0.09, 0.15, 0.15, 0.10, 0.12)], numeric=numeric(7))]
    return out


def build_pdf(report):
    slots = report["slots"]
    names = [s.name() for s in slots]
    word = UNITS[report["unit"]]
    story = [
        Spacer(1, 4 * mm),
        p(f"{word[0].title()} by {word[0]} comparison", "title"),
        p(f"{escape(names[0])} to {escape(names[-1])} · {len(slots)} {word[1]}", "subtitle"),
        Spacer(1, 1.5 * mm),
        p(f"Prepared from the Dash Pulse dashboard"
          f"{' by ' + escape(report['generated_by']) if report['generated_by'] else ''}. "
          f"All times are Lagos time (WAT); amounts are in Nigerian naira (NGN). "
          f"The cards below compare {escape(names[-1])} with {escape(names[-2])}.", "meta"),
        Spacer(1, 6 * mm),
        kpi_cards(report),
        Spacer(1, 6 * mm),
        p("1. Headlines", "h1"),
    ]
    story += [Paragraph(escape(f), S["bullet"], bulletText="•") for f in report["findings"]]
    if report["notes"]:
        story += [Spacer(1, 2 * mm), p("Read with care", "h2")]
        story += [Paragraph(escape(n), S["bullet"], bulletText="!") for n in report["notes"]]

    story += section("2. Scorecard")
    story.append(p(f"Every headline figure for each {word[0]}"
                   + (", with the change between them." if len(slots) == 2
                      else f", with the change from the {word[0]} before it underneath.")
                   + " Green is good news and red is bad news; grey changes are neutral or too small to matter."))
    story += [Spacer(1, 2 * mm), grid(slots, report["rows"])]
    story += [p("Daily averages", "h2"),
              p(f"Totals divided by the number of days in each {word[0]}. This is the fairest like-for-like view "
                f"when periods have different lengths or one is still running."),
              Spacer(1, 2 * mm), grid(slots, report["daily"])]

    parts = [transactions_part, money_part, failures_part, banks_part, onboarding_part, rewards_part, events_part]
    for i, part in enumerate(parts, start=3):
        story += part(report, i)

    story += appendix(report)
    story += [Spacer(1, 6 * mm), p("Notes and definitions", "h1")]
    for n in report["notes"]:
        story.append(Paragraph(escape(n), S["bullet"], bulletText="•"))
    for term, meaning in DEFINITIONS + EXTRA_DEFINITIONS:
        if term in ("Previous period", "Not comparable"):
            continue
        story.append(Paragraph(f"<b>{escape(term)}:</b> {escape(meaning)}", S["bullet"], bulletText="•"))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=21 * mm,
                            bottomMargin=19 * mm, title=f"Dash MFB {word[0]} comparison, {names[0]} to {names[-1]}",
                            author="Dash Pulse", subject="Period comparison")
    doc.build(story, canvasmaker=lambda *a, **k: NumberedCanvas(*a, report=report, **k))
    return buf.getvalue()


def email_html(report):
    slots = report["slots"]
    keys = ["transactions", "success_rate", "value", "money_in", "accounts", "failed"]
    rows = report["by_key"]
    head = "".join(f'<th align="right" style="padding:6px 8px;background:#4a1a6b;color:#fff">{escape(s.name())}</th>'
                   for s in slots)
    body = ""
    for key in keys:
        r = rows.get(key)
        if not r:
            continue
        cells = "".join(f'<td style="padding:6px 8px;border-bottom:1px solid #eee;text-align:right">'
                        f'{escape(compact(r["kind"], c["value"]))}{"*" if c["incomplete"] else ""}</td>'
                        for c in r["cells"])
        body += f'<tr><td style="padding:6px 8px;border-bottom:1px solid #eee">{escape(r["metric"])}</td>{cells}</tr>'
    findings = "".join(f'<li style="margin-bottom:6px">{escape(f)}</li>' for f in report["findings"])
    word = UNITS[report["unit"]]
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;color:#1e1b2e;max-width:760px">
<div style="font-size:20px;font-weight:600;color:#4a1a6b">Dash MFB · {word[0].title()} by {word[0]} comparison</div>
<p style="font-size:14px;margin:8px 0 16px">{escape(slots[0].name())} to {escape(slots[-1].name())}
({len(slots)} {word[1]}).</p>
<div style="font-size:15px;font-weight:600;color:#4a1a6b;margin-bottom:6px">Headlines</div>
<ul style="font-size:14px;line-height:1.5;padding-left:20px;margin:0 0 18px">{findings}</ul>
<table cellspacing="0" style="border-collapse:collapse;font-size:13px;width:100%">
<tr><th align="left" style="padding:6px 8px;background:#4a1a6b;color:#fff">Measure</th>{head}</tr>{body}</table>
<p style="font-size:13px;color:#6b6880;margin-top:18px">The full comparison, with charts and detail on every area,
is attached as a PDF. Figures marked * were only partly recorded in that period. Confidential, for internal use within
Dash MFB only.</p>
</div>"""


def filename(report):
    return f"Dash-Comparison_{report['unit']}s_{report['slots'][0].key}_to_{report['slots'][-1].key}.pdf"
