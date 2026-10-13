"""Exportable CSV reports (revenue, outstanding, attendance, coach activity)."""
import csv

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.academy.scoping import batch_ids_for
from apps.accounts.permissions import staff_scope
from apps.attendance.models import Attendance, Session
from apps.fees.models import InvoiceStatus
from apps.portal import analytics, periods


def _csv_response(name, header, rows):
    resp = HttpResponse(content_type="text/csv")
    stamp = timezone.localdate().isoformat()
    resp["Content-Disposition"] = f'attachment; filename="{name}_{stamp}.csv"'
    writer = csv.writer(resp)
    writer.writerow(header)
    writer.writerows(rows)
    return resp


@staff_scope
def reports_index(request):
    return render(request, "portal/reports.html", {})


@staff_scope
def export_revenue(request):
    payments = analytics.scoped_payments(request.user).select_related(
        "student", "invoice", "invoice__sport", "invoice__branch"
    )
    name = "revenue"
    if request.GET.get("period"):  # ?period=2026-10 | 2026 (from the dashboard menu)
        period = periods.parse_period(request.GET["period"], timezone.localdate())
        payments = payments.filter(
            recorded_at__date__gte=period.start, recorded_at__date__lte=period.end
        )
        name = f"revenue_{period.value}"
    rows = [
        [
            timezone.localtime(p.recorded_at).strftime("%Y-%m-%d %H:%M"),
            p.receipt_number or "",
            p.student.full_name,
            p.invoice.sport.name if p.invoice else "",
            p.invoice.branch.name if p.invoice and p.invoice.branch else "",
            p.get_method_display(),
            p.get_kind_display(),
            f"{p.amount}",
        ]
        for p in payments
    ]
    return _csv_response(
        name,
        ["Date", "Receipt", "Student", "Sport", "Branch", "Method", "Kind", "Amount"],
        rows,
    )


@staff_scope
def export_outstanding(request):
    invoices = analytics.scoped_invoices(request.user).filter(
        status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE]
    ).select_related("student", "sport", "branch")
    rows = [
        [
            i.number,
            i.student.full_name,
            i.sport.name,
            i.branch.name if i.branch else "",
            i.period_label,
            i.due_date.isoformat(),
            f"{i.net_payable}",
            f"{i.amount_paid}",
            f"{i.balance}",
            i.get_status_display(),
        ]
        for i in invoices.order_by("due_date")
    ]
    return _csv_response(
        "outstanding_fees",
        ["Invoice", "Student", "Sport", "Branch", "Period", "Due", "Payable", "Paid", "Balance", "Status"],
        rows,
    )


@staff_scope
def export_attendance(request):
    batch_ids = batch_ids_for(request.user)
    records = (
        Attendance.objects.filter(session__batch_id__in=batch_ids)
        .select_related("student", "session", "session__batch", "session__batch__branch", "session__batch__sport")
        .order_by("-session__date")[:5000]
    )
    rows = [
        [
            a.session.date.isoformat(),
            a.session.batch.sport.name,
            str(a.session.batch),
            a.session.batch.branch.name,
            a.student.full_name,
            a.get_status_display(),
        ]
        for a in records
    ]
    return _csv_response(
        "attendance",
        ["Date", "Sport", "Batch", "Branch", "Student", "Status"],
        rows,
    )


@staff_scope
def export_coach_activity(request):
    batch_ids = batch_ids_for(request.user)
    sessions = (
        Session.objects.filter(batch_id__in=batch_ids)
        .exclude(coach__isnull=True)
        .select_related("coach", "batch", "batch__branch", "batch__sport")
        .prefetch_related("records")
        .order_by("-date")[:5000]
    )
    rows = []
    for s in sessions:
        present = sum(1 for r in s.records.all() if r.status in ("PRESENT", "LATE"))
        rows.append(
            [
                s.date.isoformat(),
                s.coach.full_name,
                str(s.batch),
                s.batch.branch.name,
                s.get_status_display(),
                s.get_check_in_method_display() if s.check_in_method else "",
                "yes" if s.manual_flagged else "no",
                s.duration_minutes or "",
                present,
            ]
        )
    return _csv_response(
        "coach_activity",
        ["Date", "Coach", "Batch", "Branch", "Status", "CheckIn", "Manual", "Minutes", "Present"],
        rows,
    )
