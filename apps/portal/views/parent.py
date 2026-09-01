"""Parent app: children overview, fees, attendance, live visibility."""
from django.shortcuts import get_object_or_404, render

from apps.academy.scoping import accessible_students
from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.attendance.models import Session, SessionStatus
from apps.fees.models import InvoiceStatus
from apps.portal import analytics


@role_required(Role.PARENT)
def parent_home(request):
    students = accessible_students(request.user).prefetch_related(
        "enrollments__sport", "enrollments__batch__branch", "enrollments__batch__coaches"
    )
    invoices = analytics.scoped_invoices(request.user)
    cards = []
    for s in students:
        outstanding = sum(
            (i.balance for i in invoices.filter(
                student=s, status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE]
            )),
            start=__import__("decimal").Decimal("0.00"),
        )
        live = Session.objects.filter(
            batch__enrollments__student=s, status=SessionStatus.LIVE
        ).select_related("batch", "coach").distinct()
        cards.append({"student": s, "outstanding": outstanding, "live": live})
    return render(request, "portal/parent/home.html", {"cards": cards})


@role_required(Role.PARENT)
def parent_fees(request):
    invoices = (
        analytics.scoped_invoices(request.user)
        .select_related("student", "sport")
        .order_by("status", "due_date")
    )
    return render(request, "portal/parent/fees.html", {"invoices": invoices})


@role_required(Role.PARENT)
def parent_attendance(request, student_id):
    student = get_object_or_404(accessible_students(request.user), pk=student_id)
    records = (
        student.attendance.select_related("session", "session__batch", "session__batch__sport")
        .order_by("-session__date")[:100]
    )
    return render(
        request,
        "portal/parent/attendance.html",
        {"student": student, "records": records},
    )
