from calendar import monthrange
from datetime import date, timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer

from .queries import LEGACY, fetch, lagos_now
from .report_data import COMPARE, PARTIAL_KEYS, Period, change, collect, money, pct, ratio, recorded_from, safe
from .report_pdf import (
    BLUE,
    BRAND,
    DEFINITIONS,
    GOOD,
    BAD,
    GREEN,
    GREY,
    MARGIN,
    MUTED,
    RED,
    S,
    WIDTH,
    NumberedCanvas,
    bar_chart,
    hexcolor,
    kpi_cards,
    num,
    p,
    section,
    table,
)

UNITS = {"month": ("month", "months"), "quarter": ("quarter", "quarters")}
MAX_PERIODS = 6
MAX_OPTIONS = 24
RATE_KEYS = {"success_rate", "finish_rate", "average_value"}
MIN_BANK_TRANSFERS = 30

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
    totals, sides, counts = {}, {}, []
    for c in cols:
        here = {}
        for r in c["reasons"]:
            here[r["reason"]] = r["count"]
            totals[r["reason"]] = totals.get(r["reason"], 0) + r["count"]
            sides[r["reason"]] = r["side"]
        counts.append(here)
    top = sorted(totals, key=lambda k: -totals[k])[:limit]
    return [{"reason": k, "side": sides[k], "counts": [c.get(k, 0) for c in counts]} for k in top]


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


def findings(slots, cols, rows, daily):
    out = []
    names = [s.name() for s in slots]
    by_key = {r["key"]: r for r in rows}
    per_day = {r["key"]: r for r in daily}
    word = UNITS[slots[0].unit]
    out.append(f"This report compares {len(slots)} {word[1]}, from {names[0]} to {names[-1]}.")
    last, prev = slots[-1], slots[-2]

    def moved(label, key, fmt):
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

    moved("Transactions", "transactions", lambda v: f"{v:,.0f}")
    moved("Money sent by customers", "value", money)
    moved("Accounts opened", "accounts", lambda v: f"{v:,.0f}")
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
        out.append(f"The busiest {word[0]} was {names[i]} with {by_key['transactions']['cells'][i]['value']:,} "
                   f"transactions.")
        i = best("value", skip_gaps=True)
        out.append(f"Customers sent the most money in {names[i]}: {money(by_key['value']['cells'][i]['value'])}.")
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
    for s in slots:
        if s.partial:
            out.append(f"{s.name(False)} is not finished; its figures run to {s.end:%d %B %Y}. Its totals are not "
                       f"compared with finished {UNITS[s.unit][1]}; use the daily averages table instead.")
    lengths = {s.days for s in slots if not s.partial}
    if len(lengths) > 1:
        out.append(f"The {UNITS[slots[0].unit][1]} compared have different numbers of days "
                   f"({min(lengths)} to {max(lengths)}), so the daily averages table gives the fairest comparison.")
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
    return {
        "unit": unit,
        "slots": slots,
        "columns": cols,
        "period": Period(slots[0].start, slots[-1].end),
        "header": "Dash MFB · Period Comparison",
        "rows": rows,
        "daily": daily,
        "comparison": comparison,
        "reasons": reason_rows(cols),
        "sides": side_rows(cols),
        "products": product_rows(cols),
        "banks": bank_rows(cols),
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


def grid(slots, rows, first=0.28):
    width = (1 - first) / len(slots)
    data = []
    for r in rows:
        line = [escape(r["metric"])]
        for cell in r["cells"]:
            value = compact(r["kind"], cell["value"]) + ("*" if cell["incomplete"] else "")
            extra = change_html(r, cell)
            line.append(Paragraph(f"{value}<br/><font size='6.5'>{extra}</font>" if extra else value, S["cell_r"]))
        data.append(line)
    return table(["Measure"] + [s.name() for s in slots], data, [WIDTH * first] + [WIDTH * width] * len(slots),
                 numeric=tuple(range(1, len(slots) + 1)))


def counts_table(slots, label, rows, first=0.34):
    width = (1 - first) / len(slots)
    return table([label] + [s.name() for s in slots], rows, [WIDTH * first] + [WIDTH * width] * len(slots),
                 numeric=tuple(range(1, len(slots) + 1)))


def build_pdf(report):
    slots, cols = report["slots"], report["columns"]
    names = [s.name() for s in slots]
    short = [s.name(False) for s in slots]
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
        p("1. Summary", "h1"),
    ]
    story += [Paragraph(escape(f), S["bullet"], bulletText="•") for f in report["findings"]]
    if report["notes"]:
        story += [Spacer(1, 2 * mm), p("Read with care", "h2")]
        story += [Paragraph(escape(n), S["bullet"], bulletText="!") for n in report["notes"]]

    story += section(f"2. {word[1].title()} side by side")
    story.append(p(f"Each figure shows the change from the {word[0]} before it. Totals of a {word[0]} that is "
                   f"still running are not compared; see the daily averages."))
    story.append(Spacer(1, 2 * mm))
    story.append(grid(slots, report["rows"]))

    story += section("3. Daily averages")
    story.append(p(f"Totals divided by the number of days in each {word[0]}, the fairest like-for-like view."))
    story.append(Spacer(1, 2 * mm))
    story.append(grid(slots, report["daily"]))

    story += section("4. Trends")
    t = [c["totals"] for c in cols]
    story.append(bar_chart(f"Transactions per {word[0]}", slots,
                           [("Successful", [x["success"] for x in t], GREEN),
                            ("Failed", [x["failed"] for x in t], RED),
                            ("Reversed or pending", [x["transactions"] - x["success"] - x["failed"] for x in t], GREY)],
                           stacked=True, labels=short))
    story.append(Spacer(1, 3 * mm))
    money_series = [("Money sent (NGN m)", [x["value"] / 1e6 for x in t], BRAND)]
    if all(x["money_in"] is not None for x in t):
        money_series.append(("Money in (NGN m)", [x["money_in"] / 1e6 for x in t], BLUE))
    story.append(bar_chart(f"Money per {word[0]} (NGN millions)", slots, money_series, unit="m", labels=short))
    story.append(Spacer(1, 3 * mm))
    story.append(bar_chart(f"Sign-ups and accounts opened per {word[0]}", slots,
                           [("Sign-ups started", [x["signups"] for x in t], BLUE),
                            ("Accounts opened", [x["accounts"] for x in t], GREEN)], labels=short))

    story += section("5. Failed transactions")
    story.append(p("Who caused the failures in each period, then the main reasons. A reason that keeps growing is "
                   "the one to raise."))
    story.append(Spacer(1, 2 * mm))
    story.append(counts_table(slots, "Side", [
        [escape(side)] + [f"{v:,}<br/><font size='6.5' color='{hexcolor(MUTED)}'>"
                          f"{pct(ratio(v, t[i]['failed']), 0)}</font>" for i, v in enumerate(values)]
        for side, values in report["sides"]]))
    story.append(p("Main failure reasons", "h2"))
    story.append(counts_table(slots, "Reason", [
        [Paragraph(f"<b>{escape(r['reason'])}</b><br/><font color='{hexcolor(MUTED)}'>{escape(r['side'])}</font>",
                   S["cell"])] + [f"{v:,}" for v in r["counts"]]
        for r in report["reasons"]]))

    story += section("6. Products")
    story.append(p("Transactions per product, with the failure rate underneath."))
    story.append(Spacer(1, 2 * mm))
    story.append(counts_table(slots, "Product", [
        [escape(r["product"])] + [
            "—" if c is None else f"{c['count']:,}<br/><font size='6.5' color='{hexcolor(MUTED)}'>"
                                  f"{pct(c['failure_rate'])} failed</font>" for c in r["cells"]]
        for r in report["products"]]))

    story += section("7. Transfers to other banks")
    story.append(p(f"The busiest receiving banks, with each period's failure rate and number of transfers. Rates "
                   f"for fewer than {MIN_BANK_TRANSFERS} transfers are not shown."))
    story.append(Spacer(1, 2 * mm))
    story.append(counts_table(slots, "Receiving bank", [
        [escape(r["bank"])] + [
            "—" if c is None or c["count"] < MIN_BANK_TRANSFERS
            else f"{pct(c['failure_rate'])}<br/><font size='6.5' color='{hexcolor(MUTED)}'>{c['count']:,} sent</font>"
            for c in r["cells"]]
        for r in report["banks"]]))

    story += section("Notes and definitions")
    for term, meaning in DEFINITIONS + EXTRA_DEFINITIONS:
        if term == "Previous period":
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
    rows = {r["key"]: r for r in report["rows"]}
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
<div style="font-size:15px;font-weight:600;color:#4a1a6b;margin-bottom:6px">Key findings</div>
<ul style="font-size:14px;line-height:1.5;padding-left:20px;margin:0 0 18px">{findings}</ul>
<table cellspacing="0" style="border-collapse:collapse;font-size:13px;width:100%">
<tr><th align="left" style="padding:6px 8px;background:#4a1a6b;color:#fff">Measure</th>{head}</tr>{body}</table>
<p style="font-size:13px;color:#6b6880;margin-top:18px">The full comparison is attached as a PDF. Figures marked * were
only partly recorded in that period. Confidential, for internal use within Dash MFB only.</p>
</div>"""


def filename(report):
    return f"Dash-Comparison_{report['unit']}s_{report['slots'][0].key}_to_{report['slots'][-1].key}.pdf"
