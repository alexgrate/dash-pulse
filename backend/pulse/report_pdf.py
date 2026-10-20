from io import BytesIO
from xml.sax.saxutils import escape

from django.conf import settings
from reportlab.graphics.charts.barcharts import HorizontalBarChart, VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    CondPageBreak,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .report_data import DAILY_CHART_MAX_DAYS, money, pct

BRAND = colors.HexColor("#4a1a6b")
BRAND_SOFT = colors.HexColor("#f4f0f8")
INK = colors.HexColor("#1e1b2e")
MUTED = colors.HexColor("#6b6880")
RULE = colors.HexColor("#e2dde9")
GOOD = colors.HexColor("#157a3c")
BAD = colors.HexColor("#b42318")
BLUE = colors.HexColor("#2a78d6")
ORANGE = colors.HexColor("#eb6834")
AQUA = colors.HexColor("#1baf7a")
YELLOW = colors.HexColor("#eda100")
MAGENTA = colors.HexColor("#e87ba4")
DEEP_GREEN = colors.HexColor("#008300")
GREY = colors.HexColor("#b9b4c4")
SERIES = [BLUE, ORANGE, AQUA, YELLOW, MAGENTA, DEEP_GREEN]

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
WIDTH = PAGE_W - 2 * MARGIN

S = {
    "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=BRAND),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=11, leading=15, textColor=INK),
    "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=8.5, leading=12, textColor=MUTED),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=14, leading=18, textColor=BRAND,
                         spaceBefore=4, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=INK,
                         spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK,
                             leftIndent=10, bulletIndent=0, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8, leading=10, textColor=INK, alignment=TA_LEFT),
    "cell_r": ParagraphStyle("cell_r", fontName="Helvetica", fontSize=8, leading=10, textColor=INK,
                             alignment=TA_RIGHT),
    "cell_muted": ParagraphStyle("cell_muted", fontName="Helvetica", fontSize=7.5, leading=9.5, textColor=MUTED),
    "head": ParagraphStyle("head", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5, textColor=colors.white),
    "head_r": ParagraphStyle("head_r", fontName="Helvetica-Bold", fontSize=7.5, leading=9.5,
                             textColor=colors.white, alignment=TA_RIGHT),
    "kpi": ParagraphStyle("kpi", fontName="Helvetica-Bold", fontSize=14, leading=17, textColor=INK),
    "kpi_label": ParagraphStyle("kpi_label", fontName="Helvetica", fontSize=7, leading=9, textColor=MUTED),
    "note": ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=8, leading=11, textColor=MUTED),
}


def p(text, style="body"):
    return Paragraph(text, S[style])


def num(v):
    return f"{v:,.0f}" if v is not None else "n/a"


def short_money(v):
    if v is None:
        return "n/a"
    for size, suffix in ((1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if abs(v) >= size:
            return f"NGN {v / size:,.1f}{suffix}"
    return f"NGN {v:,.0f}"


def fmt(kind, v):
    if v is None:
        return "n/a"
    return {"count": num, "money": money, "pct": pct}[kind](v)


def change_text(row):
    if not row.get("comparable", True):
        return "not comparable", MUTED
    c = row["change"]
    if c is None:
        return "n/a", MUTED
    if row["points"]:
        text = f"{'+' if c >= 0 else '−'}{abs(c) * 100:.1f} pts"
        flat = abs(c) < 0.005
    else:
        text = f"{'+' if c >= 0 else '−'}{abs(c) * 100:.1f}%"
        flat = abs(c) < 0.01
    if flat or row["up_is_good"] is None:
        return text, MUTED
    good = (c > 0) == row["up_is_good"]
    return text, GOOD if good else BAD


def table(header, rows, widths, numeric=(), zebra=True):
    data = [[p(escape(h), "head_r" if i in numeric else "head") for i, h in enumerate(header)]]
    for r in rows:
        data.append([c if not isinstance(c, str) else p(c, "cell_r" if i in numeric else "cell")
                     for i, c in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, RULE),
    ]
    if zebra:
        for i in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), BRAND_SOFT))
    t.setStyle(TableStyle(style))
    return t


def labels_for(dates):
    every = max(1, -(-len(dates) // 10))
    last = len(dates) - 1
    return [f"{d:%d %b}" if (last - i) % every == 0 else "" for i, d in enumerate(dates)]


def headroom(series, stacked):
    values = [v or 0 for _, vals, _ in series for v in vals]
    if stacked:
        values = [sum(v or 0 for v in col) for col in zip(*[vals for _, vals, _ in series])]
    return max(values or [0]) * 1.18 or 1


def legend_room(title, series):
    if len(series) < 2:
        return 0
    title_w = len(title) * 5
    legend_w = sum(len(name) * 4 + 24 for name, _, _ in series)
    return 14 if title_w + legend_w + 24 > WIDTH else 0


def legend_for(d, series, height):
    legend = Legend()
    legend.x, legend.y = WIDTH, height - 1
    legend.boxAnchor = "ne"
    legend.alignment = "right"
    legend.columnMaximum = 1
    legend.deltax = 0
    legend.dx = 7
    legend.dy = 7
    legend.fontName = "Helvetica"
    legend.fontSize = 7.5
    legend.dxTextSpace = 4
    legend.colorNamePairs = [(color, name) for name, _, color in series]
    d.add(legend)


def bar_chart(title, buckets, series, unit="", stacked=False, height=62 * mm, labels=None, value_labels=None):
    d = Drawing(WIDTH, height)
    d.add(String(0, height - 10, title, fontName="Helvetica-Bold", fontSize=9, fillColor=INK))
    room = legend_room(title, series)
    chart = VerticalBarChart()
    chart.x, chart.y = 38, 16
    chart.width, chart.height = WIDTH - 44, height - 36 - room
    chart.data = [values for _, values, _ in series]
    for i, (_, _, color) in enumerate(series):
        chart.bars[i].fillColor = color
        chart.bars[i].strokeColor = None
    chart.categoryAxis.categoryNames = labels if labels is not None else labels_for([b["date"] for b in buckets])
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.angle = 0
    chart.categoryAxis.labels.dy = -3
    chart.categoryAxis.strokeColor = RULE
    chart.categoryAxis.tickDown = 0
    if stacked:
        chart.categoryAxis.style = "stacked"
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 6.5
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = RULE
    chart.valueAxis.gridStrokeColor = RULE
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.labelTextFormat = lambda v: f"{v:,.0f}{unit}"
    chart.barSpacing = 1 if len(buckets) > 8 else 3
    chart.groupSpacing = 3 if len(buckets) > 20 else (6 if len(buckets) > 8 else 14)
    if value_labels:
        chart.valueAxis.valueMax = headroom(series, stacked)
        chart.barLabelFormat = value_labels
        chart.barLabels.fontName = "Helvetica"
        chart.barLabels.fontSize = 6.5
        chart.barLabels.fillColor = INK
        chart.barLabels.boxAnchor = "s"
        chart.barLabels.nudge = 6
        if stacked:
            chart.barLabels.boxAnchor = "c"
            chart.barLabels.nudge = 0
            chart.barLabels.fillColor = colors.white
    d.add(chart)
    if len(series) > 1:
        legend_for(d, series, height - room)
    return d


def line_chart(title, labels, series, value_format, height=55 * mm, value_min=None, value_max=None):
    d = Drawing(WIDTH, height)
    d.add(String(0, height - 10, title, fontName="Helvetica-Bold", fontSize=9, fillColor=INK))
    room = legend_room(title, series)
    chart = HorizontalLineChart()
    chart.x, chart.y = 38, 16
    chart.width, chart.height = WIDTH - 44, height - 36 - room
    chart.data = [values for _, values, _ in series]
    for i, (_, _, color) in enumerate(series):
        chart.lines[i].strokeColor = color
        chart.lines[i].strokeWidth = 2
        chart.lines[i].symbol = makeMarker("Circle", size=3.5, fillColor=color, strokeColor=colors.white)
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 6.5
    chart.categoryAxis.labels.dy = -3
    chart.categoryAxis.strokeColor = RULE
    chart.categoryAxis.tickDown = 0
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 6.5
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = RULE
    chart.valueAxis.gridStrokeColor = RULE
    chart.valueAxis.visibleGrid = True
    chart.valueAxis.labelTextFormat = value_format
    if value_min is not None:
        chart.valueAxis.valueMin = value_min
    if value_max is not None:
        chart.valueAxis.valueMax = value_max
    chart.joinedLines = 1
    d.add(chart)
    if len(series) > 1:
        legend_for(d, series, height - room)
    return d


def hbar_chart(title, labels, series, value_labels, row=None, label_width=150):
    row = row or (7 + 5 * len(series))
    room = legend_room(title, series)
    height = 34 + room + row * len(labels)
    d = Drawing(WIDTH, height)
    d.add(String(0, height - 10, title, fontName="Helvetica-Bold", fontSize=9, fillColor=INK))
    chart = HorizontalBarChart()
    chart.x, chart.y = label_width, 6
    chart.width, chart.height = WIDTH - label_width - 34, height - 30 - room
    chart.data = [list(reversed(values)) for _, values, _ in reversed(series)]
    for i, (_, _, color) in enumerate(reversed(series)):
        chart.bars[i].fillColor = color
        chart.bars[i].strokeColor = None
    chart.categoryAxis.categoryNames = list(reversed(labels))
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.boxAnchor = "e"
    chart.categoryAxis.labels.dx = -4
    chart.categoryAxis.strokeColor = RULE
    chart.categoryAxis.tickLeft = 0
    chart.valueAxis.visible = False
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = headroom(series, False)
    chart.barSpacing = 1
    chart.groupSpacing = 6
    chart.barLabelFormat = value_labels
    chart.barLabels.fontName = "Helvetica"
    chart.barLabels.fontSize = 6.5
    chart.barLabels.fillColor = INK
    chart.barLabels.boxAnchor = "w"
    chart.barLabels.nudge = 6
    d.add(chart)
    if len(series) > 1:
        legend_for(d, series, height - room)
    return d


def callout(text):
    t = Table([[Paragraph(text, S["body"])]], colWidths=[WIDTH])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BRAND_SOFT),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, BRAND),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, report=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = []
        self.report = report

    def showPage(self):
        self.pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self.pages)
        for state in self.pages:
            self.__dict__.update(state)
            self.decorate(total)
            super().showPage()
        super().save()

    def decorate(self, total):
        r = self.report
        self.saveState()
        logo = settings.BASE_DIR.parent / "frontend" / "public" / "favicon.png"
        x = MARGIN
        if logo.exists():
            self.drawImage(str(logo), x, PAGE_H - 13 * mm, 7 * mm, 7 * mm, mask="auto")
            x += 9 * mm
        self.setFont("Helvetica-Bold", 8.5)
        self.setFillColor(BRAND)
        self.drawString(x, PAGE_H - 10.4 * mm, r.get("header", "Dash MFB · Operations Report"))
        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawRightString(PAGE_W - MARGIN, PAGE_H - 10.4 * mm, r["period"].label())
        self.setStrokeColor(RULE)
        self.setLineWidth(0.6)
        self.line(MARGIN, PAGE_H - 15 * mm, PAGE_W - MARGIN, PAGE_H - 15 * mm)
        self.line(MARGIN, 13 * mm, PAGE_W - MARGIN, 13 * mm)
        self.setFont("Helvetica", 7.5)
        self.drawString(MARGIN, 8.5 * mm, "Confidential · for internal use within Dash MFB only")
        self.drawCentredString(PAGE_W / 2, 8.5 * mm, f"Generated {r['generated_at']:%d %b %Y, %H:%M} WAT")
        self.drawRightString(PAGE_W - MARGIN, 8.5 * mm, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def kpi_cards(report):
    keys = ["transactions", "success_rate", "value", "money_in", "accounts", "signups", "failed", "active_users"]
    rows = {r["key"]: r for r in report["comparison"]}
    cells = []
    for key in keys:
        r = rows[key]
        text, color = change_text(r)
        value = short_money(r["now"]) if r["kind"] == "money" else fmt(r["kind"], r["now"])
        cells.append([
            p(escape(r["metric"].upper()), "kpi_label"),
            p(escape(value), "kpi"),
            p(f'<font color="{hexcolor(color)}">{text}</font>'
              f'{r.get("suffix", " vs previous") if r.get("comparable", True) else ""}', "cell_muted"),
        ])
    grid = []
    for i in range(0, len(cells), 4):
        grid.append([Table([[c[0]], [c[1]], [c[2]]], colWidths=WIDTH / 4 - 4,
                           style=TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 7),
                                             ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                                             ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
                     for c in cells[i:i + 4]])
    t = Table(grid, colWidths=[WIDTH / 4] * 4, rowHeights=21 * mm)
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, RULE),
        ("INNERGRID", (0, 0), (-1, -1), 0.6, RULE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def hexcolor(color):
    return color.hexval().replace("0x", "#")


def comparison_table(report):
    rows = []
    for r in report["comparison"]:
        text, color = change_text(r)
        rows.append([escape(r["metric"]), fmt(r["kind"], r["now"]), fmt(r["kind"], r["before"]),
                     Paragraph(f'<font color="{hexcolor(color)}">{text}</font>', S["cell_r"])])
    return table(["Measure", "This period", "Previous period", "Change"], rows,
                 [WIDTH * 0.40, WIDTH * 0.22, WIDTH * 0.22, WIDTH * 0.16], numeric=(1, 2, 3))


def buckets_for(report):
    series = report["current"]["series"]
    return (series, False) if len(series) <= DAILY_CHART_MAX_DAYS else (report["weekly"], True)


def section(title):
    return [CondPageBreak(60 * mm), p(escape(title), "h1")]


def build_pdf(report):
    cur, prev = report["current"], report["prior"]
    t = cur["totals"]
    buckets, weekly = buckets_for(report)
    period, previous = report["period"], report["previous"]
    story = []

    story += [
        Spacer(1, 4 * mm),
        p("Operations Report", "title"),
        p(f"{escape(period.label())} · {period.days} days", "subtitle"),
        Spacer(1, 1.5 * mm),
        p(f"Compared with the previous {period.days} days ({escape(previous.label())}). "
          f"Prepared from the Dash Pulse dashboard"
          f"{' by ' + escape(report['generated_by']) if report['generated_by'] else ''}. "
          f"All times are Lagos time (WAT); amounts are in Nigerian naira (NGN).", "meta"),
        Spacer(1, 6 * mm),
        kpi_cards(report),
        Spacer(1, 6 * mm),
        p("1. Executive summary", "h1"),
    ]
    story += [Paragraph(escape(f), S["bullet"], bulletText="•") for f in report["findings"]]
    if report["notes"]:
        story += [Spacer(1, 2 * mm), p("Read with care", "h2")]
        story += [Paragraph(escape(n), S["bullet"], bulletText="!") for n in report["notes"]]
    story += [Spacer(1, 4 * mm), p("Period at a glance", "h2"), comparison_table(report)]

    story += section("2. Transactions")
    story.append(p(
        f"Customers attempted <b>{num(t['transactions'])}</b> transactions. <b>{num(t['success'])}</b> succeeded, "
        f"<b>{num(t['failed'])}</b> failed, <b>{num(t['reversed'])}</b> were reversed and "
        f"<b>{num(t['pending'])}</b> were still pending when this report was produced. "
        f"Success rate is measured on transactions with a final outcome."))
    story.append(Spacer(1, 3 * mm))
    story.append(bar_chart(
        f"Transactions per {'week (dated by week start)' if weekly else 'day'}",
        buckets,
        [("Successful", [b["success"] for b in buckets], BLUE),
         ("Failed", [b["failed"] for b in buckets], ORANGE),
         ("Reversed or pending", [b["transactions"] - b["success"] - b["failed"] for b in buckets], GREY)],
        stacked=True,
    ))
    story.append(p("By product", "h2"))
    prev_products = {r["product"]: r for r in prev["products"]}
    rows = []
    for r in cur["products"]:
        before = prev_products.get(r["product"], {}).get("count")
        c = (r["count"] / before - 1) if before else None
        rows.append([escape(r["product"]), num(r["count"]), pct(r["share"], 0), num(r["success"]),
                     num(r["failed"]), pct(r["failure_rate"]), money(r["value"]),
                     "n/a" if c is None else f"{'+' if c >= 0 else '−'}{abs(c) * 100:.0f}%"])
    story.append(table(["Product", "Count", "Share", "Successful", "Failed", "Failure rate", "Value sent",
                        "Count vs prev."], rows,
                       [WIDTH * w for w in (0.22, 0.10, 0.08, 0.11, 0.09, 0.11, 0.17, 0.12)],
                       numeric=(1, 2, 3, 4, 5, 6, 7)))

    story += section("3. Money movement")
    lines = [f"Customers successfully sent <b>{money(t['value'])}</b> out of their accounts "
             f"(average <b>{money(t['average_value'])}</b> per successful transaction)."]
    if t["money_in"] is not None:
        lines.append(f"<b>{money(t['money_in'])}</b> arrived from other banks into customers' accounts in "
                     f"<b>{num(t['money_in_count'])}</b> transfers.")
        if t["money_in_other"]:
            lines.append(f"A further <b>{money(t['money_in_other'])}</b> arrived in "
                         f"<b>{num(t['money_in_other_count'])}</b> transfers into Dash accounts that are not app "
                         f"customers, such as treasury or fixed-deposit accounts; it is left out of money in.")
        lines.append("Money sent covers only what customers send through the app, while some customers also "
                     "move money out through internet banking or the branch, so the two figures should not be "
                     "netted against each other.")
    story.append(p(" ".join(lines)))
    story.append(Spacer(1, 3 * mm))
    money_series = [("Money sent (NGN m)", [b["value"] / 1e6 for b in buckets], BLUE)]
    if t["money_in"] is not None:
        money_series.append(("Money in (NGN m)", [(b["money_in"] or 0) / 1e6 for b in buckets], AQUA))
    story.append(bar_chart(f"Money per {'week (dated by week start)' if weekly else 'day'} (NGN millions)", buckets, money_series,
                           unit="m"))

    story += section("4. Failed transactions")
    story.append(p(
        f"<b>{num(t['failed'])}</b> transactions failed ({pct(t['failure_rate'])} of those with a final outcome), "
        f"against <b>{num(prev['totals']['failed'])}</b> in the previous period. Reasons are grouped from the "
        f"messages returned by the payment partner and core banking."))
    sides = {}
    for r in cur["reasons"]:
        sides[r["side"]] = sides.get(r["side"], 0) + r["count"]
    story.append(p("Who caused the failures", "h2"))
    story.append(table(["Side", "Failures", "Share"],
                       [[escape(k), num(v), pct(v / t["failed"] if t["failed"] else None)]
                        for k, v in sorted(sides.items(), key=lambda kv: -kv[1])],
                       [WIDTH * 0.5, WIDTH * 0.25, WIDTH * 0.25], numeric=(1, 2)))
    story.append(p("Failure reasons", "h2"))
    prev_reasons = {r["reason"]: r["count"] for r in prev["reasons"]}
    rows = []
    for r in cur["reasons"][:15]:
        before = prev_reasons.get(r["reason"])
        c = (r["count"] / before - 1) if before else None
        rows.append([
            Paragraph(f"<b>{escape(r['reason'])}</b><br/><font color='#6b6880'>{escape(r['hint'])}</font>",
                      S["cell"]),
            escape(r["side"]), num(r["count"]), pct(r["share"]), money(r["value"]),
            "new" if c is None else f"{'+' if c >= 0 else '−'}{abs(c) * 100:.0f}%",
            f"{r['worst_day']:%d %b}" if r["worst_day"] else "",
        ])
    story.append(table(["Reason", "Side", "Count", "Share", "Value", "vs prev.", "Worst day"], rows,
                       [WIDTH * w for w in (0.36, 0.14, 0.09, 0.08, 0.15, 0.09, 0.09)],
                       numeric=(2, 3, 4, 5, 6)))
    if len(cur["reasons"]) > 15:
        story.append(p(f"{len(cur['reasons']) - 15} smaller reasons are listed in the Excel file.", "note"))

    story += section("5. Transfers to other banks")
    story.append(p("Outgoing transfers by receiving bank, busiest first. A high failure rate at one bank usually "
                   "points to that bank or the NIP network rather than to Dash."))
    rows = [[escape(b["bank"]), num(b["count"]), num(b["success"]), num(b["failed"]), pct(b["failure_rate"]),
             money(b["value"])] for b in cur["banks"][:15]]
    story.append(table(["Receiving bank", "Transfers", "Successful", "Failed", "Failure rate", "Value sent"],
                       rows, [WIDTH * w for w in (0.30, 0.13, 0.14, 0.11, 0.13, 0.19)], numeric=(1, 2, 3, 4, 5)))
    settled_inter = sum(b["success"] + b["failed"] for b in cur["banks"])
    normal = (sum(b["failed"] for b in cur["banks"]) / settled_inter) if settled_inter else None
    watch = [b for b in cur["banks"] if normal is not None and b["count"] >= 30 and b["failure_rate"] is not None
             and b["failure_rate"] >= max(normal * 1.25, normal + 0.03)]
    story.append(p("Banks needing attention", "h2"))
    if watch:
        story.append(p(f"Banks whose failure rate was well above the {pct(normal)} average for all transfers "
                       f"to other banks (at least 30 transfers)."))
        story.append(Spacer(1, 2 * mm))
        story.append(table(["Receiving bank", "Transfers", "Failed", "Failure rate", "Above average by"],
                           [[escape(b["bank"]), num(b["count"]), num(b["failed"]), pct(b["failure_rate"]),
                             f"{(b['failure_rate'] - normal) * 100:.1f} pts"]
                            for b in sorted(watch, key=lambda b: -(b["failure_rate"] or 0))[:10]],
                           [WIDTH * 0.36, WIDTH * 0.16, WIDTH * 0.16, WIDTH * 0.16, WIDTH * 0.16],
                           numeric=(1, 2, 3, 4)))
    else:
        story.append(p(f"No bank stood out: every bank with at least 30 transfers stayed close to the "
                       f"{pct(normal)} average failure rate for transfers to other banks."))

    story += section("6. Customers and onboarding")
    story.append(KeepTogether([
        p(f"<b>{num(t['signups'])}</b> people started signing up and <b>{num(t['accounts'])}</b> accounts were "
          f"opened. Of the people who started in this period, <b>{pct(t['finish_rate'])}</b> now have an account."
          + (f" <b>{num(t['active_users'])}</b> different account holders signed in to the app."
             if t["active_users"] is not None
             else "")),
        Spacer(1, 3 * mm),
        bar_chart(f"Sign-ups and accounts opened per {'week (dated by week start)' if weekly else 'day'}", buckets,
                  [("Sign-ups started", [b["signups"] for b in buckets], BLUE),
                   ("Accounts opened", [b["accounts"] for b in buckets], AQUA)]),
    ]))
    funnel_note = []
    if cur["funnel"] and cur["funnel"][-1]["count"] != t["accounts"]:
        funnel_note = [p(f"The funnel follows only the people who started in this period, so its last step "
                         f"({num(cur['funnel'][-1]['count'])}) differs slightly from accounts opened "
                         f"({num(t['accounts'])}), which also counts people who started earlier.", "note"),
                       Spacer(1, 2 * mm)]
    funnel = KeepTogether([
        p("Onboarding funnel (people who started in this period)", "h2"),
        *funnel_note,
        table(["Stage", "People", "% of sign-ups", "Dropped at this step"],
              [[escape(s["stage"]), num(s["count"]), pct(s["share"]), num(s["lost"])] for s in cur["funnel"]],
              [WIDTH * 0.40, WIDTH * 0.20, WIDTH * 0.20, WIDTH * 0.20], numeric=(1, 2, 3)),
    ])
    story.append(funnel)
    if cur["stuck"]:
        story.append(KeepTogether([
            p("Where people stopped", "h2"),
            table(["Last step reached", "People", "Share of sign-ups"],
                  [[escape(s["step"]), num(s["count"]), pct(s["share"])] for s in cur["stuck"]],
                  [WIDTH * 0.56, WIDTH * 0.22, WIDTH * 0.22], numeric=(1, 2)),
        ]))

    story += section("7. Rewards")
    if cur["rewards"]:
        story.append(table(["Reward", "Payouts", "Total paid"],
                           [[escape(r["type"]), num(r["count"]), money(r["value"])] for r in cur["rewards"]]
                           + [["<b>Total</b>", f"<b>{num(t['rewards_count'])}</b>",
                               f"<b>{money(t['rewards_value'])}</b>"]],
                           [WIDTH * 0.5, WIDTH * 0.2, WIDTH * 0.3], numeric=(1, 2)))
    else:
        story.append(p("No rewards were paid in this period."))

    story += section("8. Notable events")
    if report["events"]:
        story.append(table(["Date", "Event", "Detail"],
                           [[f"{d:%a %d %b}", escape(kind), escape(detail)] for kind, d, detail in report["events"]],
                           [WIDTH * 0.16, WIDTH * 0.22, WIDTH * 0.62]))
    else:
        story.append(p("Nothing unusual was detected in this period."))

    story += [PageBreak(), p("Appendix A. Daily figures", "h1")]
    rows = []
    for s in cur["series"]:
        rows.append([f"{s['date']:%a %d %b}", num(s["transactions"]), pct(s["success_rate"]), num(s["failed"]),
                     money(s["value"]), money(s["money_in"]) if s["money_in"] is not None else "n/a",
                     num(s["signups"]), num(s["accounts"])])
    rows.append(["<b>Total</b>", f"<b>{num(t['transactions'])}</b>", f"<b>{pct(t['success_rate'])}</b>",
                 f"<b>{num(t['failed'])}</b>", f"<b>{money(t['value'])}</b>",
                 f"<b>{money(t['money_in']) if t['money_in'] is not None else 'n/a'}</b>",
                 f"<b>{num(t['signups'])}</b>", f"<b>{num(t['accounts'])}</b>"])
    story.append(table(["Date", "Transactions", "Success rate", "Failed", "Money sent", "Money in", "Sign-ups",
                        "Accounts"], rows,
                       [WIDTH * w for w in (0.13, 0.12, 0.11, 0.09, 0.18, 0.17, 0.10, 0.10)],
                       numeric=(1, 2, 3, 4, 5, 6, 7)))

    story += [Spacer(1, 6 * mm), p("Appendix B. Notes and definitions", "h1")]
    for n in report["notes"]:
        story.append(Paragraph(escape(n), S["bullet"], bulletText="•"))
    for term, meaning in DEFINITIONS:
        story.append(Paragraph(f"<b>{escape(term)}:</b> {escape(meaning)}", S["bullet"], bulletText="•"))

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=21 * mm,
                            bottomMargin=19 * mm, title=f"Dash MFB Operations Report, {period.label()}",
                            author="Dash Pulse", subject="Operations report")
    doc.build(story, canvasmaker=lambda *a, **k: NumberedCanvas(*a, report=report, **k))
    return buf.getvalue()


DEFINITIONS = [
    ("Transactions", "every transfer, airtime, data, bills and betting payment customers attempted in the app."),
    ("Successful", "confirmed as completed by the payment record."),
    ("Failed", "rejected by core banking or the payment partner; the customer's money was not sent."),
    ("Reversed", "sent, then returned to the customer."),
    ("Success rate", "successful divided by transactions with a final outcome (pending ones are left out)."),
    ("Money sent by customers", "the value of successful transactions, both to other banks and within Dash."),
    ("Money in", "transfers received from other banks into app customers' accounts, as notified by the payment "
                 "partner. Internal settlement movements are excluded."),
    ("Received into other Dash accounts", "transfers from other banks into Dash accounts that are not app "
                                          "customers, such as treasury or fixed-deposit accounts. Shown "
                                          "separately and not counted as money in."),
    ("Sign-ups started", "people who began creating an account in the app, counted on the day they started."),
    ("Accounts opened", "accounts actually created, counted on the day of opening."),
    ("Finished", "of the people who started in the period, the share who have an account now."),
    ("Customers who signed in", "different people with an account who signed in to the app during the period. "
                                "People who created a login but never finished opening an account are left out."),
    ("Previous period", "the same number of days immediately before the reporting period."),
    ("Not comparable", "shown instead of a change when a figure was not yet being recorded for the whole "
                       "previous period."),
]
