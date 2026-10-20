import logging
import threading
from html import escape

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db import close_old_connections
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse

from . import mailer, report_compare, report_data
from .models import ReportLog
from .report_pdf import build_pdf, fmt
from .report_xlsx import build_xlsx

logger = logging.getLogger("pulse.reports")

PERIODS = [("7", "Last 7 days"), ("30", "Last 30 days"), ("90", "Last 3 months"), ("custom", "Choose dates")]
PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def check_email(form, data):
    email = (data.get("email") or "").strip().lower()
    if not email:
        form.add_error("email", "Enter the email address to send the report to.")
    elif email.rsplit("@", 1)[-1] not in settings.PULSE_REPORT_EMAIL_DOMAINS:
        allowed = ", ".join(f"@{d}" for d in settings.PULSE_REPORT_EMAIL_DOMAINS)
        form.add_error("email", f"Reports can only be sent to {allowed} addresses.")


class ReportForm(forms.Form):
    period = forms.ChoiceField(choices=PERIODS, initial="30", widget=forms.RadioSelect)
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    email = forms.EmailField(required=False, label="Send to")

    def clean(self):
        data = super().clean()
        if data.get("period") == "custom" and not (data.get("start") and data.get("end")):
            raise forms.ValidationError("Choose a start and end date.")
        try:
            data["window"] = report_data.resolve(data.get("period"), data.get("start"), data.get("end"))
        except (TypeError, ValueError) as e:
            raise forms.ValidationError(str(e) if isinstance(e, ValueError) and "days" in str(e)
                                        else "Choose a valid date range.")
        if self.data.get("action") == "email":
            check_email(self, data)
        return data


class CompareForm(forms.Form):
    unit = forms.ChoiceField(choices=[("month", "Months"), ("quarter", "Quarters")], initial="month",
                             widget=forms.RadioSelect)
    span = forms.ChoiceField(choices=[("3", "Last 3"), ("6", "Last 6"), ("pick", "Choose which")], initial="3",
                             widget=forms.RadioSelect)
    current = forms.BooleanField(required=False, label="Include the current one so far")
    months = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)
    quarters = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)
    email = forms.EmailField(required=False, label="Send to")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        first = report_compare.first_day()
        for field, unit in (("months", "month"), ("quarters", "quarter")):
            self.fields[field].choices = [(s.key, s.name()) for s in report_compare.available(unit, first=first)]
        self.first = first

    def clean(self):
        data = super().clean()
        unit = data.get("unit") or "month"
        keys = data.get("months" if unit == "month" else "quarters") or []
        try:
            data["slots"] = report_compare.choose(unit, data.get("span") or "3", keys, data.get("current"),
                                                  first=self.first)
        except ValueError as e:
            raise forms.ValidationError(str(e))
        if self.data.get("action") == "compare_email":
            check_email(self, data)
        return data


def filename(window, ext):
    return f"Dash-Operations-Report_{window.start:%Y-%m-%d}_to_{window.end:%Y-%m-%d}.{ext}"


def email_html(report):
    rows = "".join(
        f'<tr><td style="padding:6px 10px;border-bottom:1px solid #eee">{escape(r["metric"])}</td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right"><b>'
        f'{escape(fmt(r["kind"], r["now"]))}</b></td>'
        f'<td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;color:#6b6880">'
        f'{escape(fmt(r["kind"], r["before"]))}</td></tr>'
        for r in report["comparison"]
    )
    findings = "".join(f'<li style="margin-bottom:6px">{escape(f)}</li>' for f in report["findings"])
    period, previous = report["period"], report["previous"]
    return f"""<div style="font-family:Segoe UI,Arial,sans-serif;color:#1e1b2e;max-width:680px">
<div style="font-size:20px;font-weight:600;color:#4a1a6b">Dash MFB · Operations Report</div>
<p style="font-size:14px;margin:8px 0 16px">{escape(period.label())} ({period.days} days), compared with
{escape(previous.label())}.</p>
<div style="font-size:15px;font-weight:600;color:#4a1a6b;margin-bottom:6px">Key findings</div>
<ul style="font-size:14px;line-height:1.5;padding-left:20px;margin:0 0 18px">{findings}</ul>
<table cellspacing="0" style="border-collapse:collapse;font-size:13px;width:100%">
<tr><th align="left" style="padding:6px 10px;background:#4a1a6b;color:#fff">Measure</th>
<th align="right" style="padding:6px 10px;background:#4a1a6b;color:#fff">This period</th>
<th align="right" style="padding:6px 10px;background:#4a1a6b;color:#fff">Previous period</th></tr>{rows}</table>
<p style="font-size:13px;color:#6b6880;margin-top:18px">The full report is attached as a PDF for reading and
presenting, and as an Excel workbook with the daily figures. Confidential, for internal use within Dash MFB only.</p>
</div>"""


def send_report(log_id, window, username, email):
    log = ReportLog.objects.get(pk=log_id)
    try:
        report = report_data.build(window, username)
        mailer.send(
            [email],
            f"Dash MFB Operations Report · {window.label()}",
            email_html(report),
            [(filename(window, "pdf"), PDF, build_pdf(report)), (filename(window, "xlsx"), XLSX, build_xlsx(report))],
        )
        log.status = "sent"
    except Exception as e:
        logger.exception("Report email failed")
        log.status, log.error = "failed", str(e)[:500]
    finally:
        log.save()
        close_old_connections()


def send_comparison(log_id, unit, slots, username, email):
    log = ReportLog.objects.get(pk=log_id)
    try:
        report = report_compare.build(unit, slots, username)
        word = report_compare.UNITS[unit][0]
        mailer.send(
            [email],
            f"Dash MFB {word.title()} Comparison · {slots[0].name()} to {slots[-1].name()}",
            report_compare.email_html(report),
            [(report_compare.filename(report), PDF, report_compare.build_pdf(report))],
        )
        log.status = "sent"
    except Exception as e:
        logger.exception("Comparison email failed")
        log.status, log.error = "failed", str(e)[:500]
    finally:
        log.save()
        close_old_connections()


def compare(request):
    form = CompareForm(request.POST, prefix="cmp")
    if not form.is_valid():
        return form
    action = request.POST.get("action")
    unit, slots = form.cleaned_data["unit"], form.cleaned_data["slots"]
    user = request.user
    span = {"start": slots[0].start, "end": slots[-1].end}
    if action == "compare_pdf":
        report = report_compare.build(unit, slots, user.get_username())
        content = report_compare.build_pdf(report)
        ReportLog.objects.create(user=user, action="compare_pdf", **span)
        response = HttpResponse(content, content_type=PDF)
        response["Content-Disposition"] = f'attachment; filename="{report_compare.filename(report)}"'
        return response
    email = form.cleaned_data["email"].strip().lower()
    log = ReportLog.objects.create(user=user, action="compare_email", sent_to=email, status="sending", **span)
    start(send_comparison, log.pk, unit, slots, user.get_username(), email)
    messages.success(request, f"The comparison from {slots[0].name()} to {slots[-1].name()} is being prepared "
                              f"and will arrive at {email} in a minute or two, with the PDF attached.")
    return redirect(request.path)


def start(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def reports(request):
    action = request.POST.get("action", "")
    comparing = request.method == "POST" and action.startswith("compare_")
    form = ReportForm(None if comparing else (request.POST or None), initial={"email": request.user.email})
    compare_form = CompareForm(prefix="cmp", initial={"email": request.user.email})
    if comparing:
        result = compare(request)
        if isinstance(result, HttpResponse):
            return result
        compare_form = result
    elif request.method == "POST" and form.is_valid():
        action = request.POST.get("action")
        window = form.cleaned_data["window"]
        user = request.user
        if action in ("pdf", "xlsx"):
            report = report_data.build(window, user.get_username())
            content = build_pdf(report) if action == "pdf" else build_xlsx(report)
            ReportLog.objects.create(user=user, start=window.start, end=window.end, action=action)
            response = HttpResponse(content, content_type=PDF if action == "pdf" else XLSX)
            response["Content-Disposition"] = f'attachment; filename="{filename(window, action)}"'
            return response
        if action == "email":
            email = form.cleaned_data["email"].strip().lower()
            log = ReportLog.objects.create(user=user, start=window.start, end=window.end, action="email",
                                           sent_to=email, status="sending")
            start(send_report, log.pk, window, user.get_username(), email)
            messages.success(request, f"The report for {window.label()} is being prepared and will arrive at "
                                      f"{email} in a minute or two, with the PDF and Excel file attached.")
            return redirect(request.path)
    context = {
        **admin.site.each_context(request),
        "title": "Reports",
        "form": form,
        "compare_form": compare_form,
        "recent": ReportLog.objects.select_related("user")[:15],
        "domains": ", ".join(f"@{d}" for d in settings.PULSE_REPORT_EMAIL_DOMAINS),
    }
    return TemplateResponse(request, "pulse/reports.html", context)
