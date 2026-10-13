"""Scoped analytics for dashboards & reports. Everything respects role scope."""
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.academy.scoping import accessible_branches, accessible_students, branch_ids_for
from apps.attendance.models import Session, SessionStatus
from apps.fees.models import Invoice, InvoiceStatus, Payment, PaymentStatus
from apps.fees.periods import period_label

ZERO = Decimal("0.00")
UNSETTLED = [InvoiceStatus.DUE, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE]


# ---------------------------------------------------------------- scoping
def scoped_invoices(user):
    qs = Invoice.objects.select_related("student", "sport", "branch")
    if user.is_superuser and user.academy_id is None:
        pass
    else:
        qs = qs.filter(academy_id=user.academy_id)
    if user.is_admin:
        return qs
    if user.is_manager:
        return qs.filter(branch_id__in=branch_ids_for(user))
    if user.is_parent:
        return qs.filter(student__in=accessible_students(user))
    if user.is_coach:
        return qs.filter(student__in=accessible_students(user))
    return qs.none()


def scoped_payments(user):
    qs = Payment.objects.filter(status=PaymentStatus.SUCCESS).select_related(
        "student", "invoice", "invoice__branch", "invoice__sport"
    )
    if not (user.is_superuser and user.academy_id is None):
        qs = qs.filter(academy_id=user.academy_id)
    if user.is_admin:
        return qs
    if user.is_manager:
        return qs.filter(invoice__branch_id__in=branch_ids_for(user))
    if user.is_parent or user.is_coach:
        return qs.filter(student__in=accessible_students(user))
    return qs.none()


# ---------------------------------------------------------------- headline
def revenue_summary(user, date_from=None, date_to=None, branch=None, sport=None):
    payments = scoped_payments(user)
    invoices = scoped_invoices(user)

    if date_from:
        payments = payments.filter(recorded_at__date__gte=date_from)
    if date_to:
        payments = payments.filter(recorded_at__date__lte=date_to)
    if branch:
        payments = payments.filter(invoice__branch=branch)
        invoices = invoices.filter(branch=branch)
    if sport:
        payments = payments.filter(invoice__sport=sport)
        invoices = invoices.filter(sport=sport)

    collected = payments.aggregate(s=Sum("amount"))["s"] or ZERO

    unsettled = invoices.filter(status__in=UNSETTLED)
    outstanding = ZERO
    overdue = ZERO
    for inv in unsettled:
        outstanding += inv.balance
        if inv.status == InvoiceStatus.OVERDUE:
            overdue += inv.balance

    return {
        "collected": collected,
        "outstanding": outstanding,
        "overdue": overdue,
        "invoice_count": invoices.count(),
        "unpaid_count": unsettled.count(),
    }


def period_payments(user, start, end, branch=None):
    """Successful payments recorded between start and end (the "Collected" rows)."""
    payments = scoped_payments(user).filter(recorded_at__date__gte=start, recorded_at__date__lte=end)
    if branch is not None:
        payments = payments.filter(invoice__branch=branch)
    return payments


def period_unsettled(user, end, branch=None):
    """Invoices due on or before `end` that still have a balance (the "Outstanding" rows,
    arrears from earlier periods included)."""
    invoices = scoped_invoices(user).filter(status__in=UNSETTLED, due_date__lte=end)
    if branch is not None:
        invoices = invoices.filter(branch=branch)
    return invoices


def period_summary(user, start, end, branch=None):
    """Headline numbers for one reporting period (admin dashboard; a branch's Fees tab
    when `branch` is given). Built from period_payments / period_unsettled, so the
    totals always match the lists shown under them."""
    collected = period_payments(user, start, end, branch).aggregate(s=Sum("amount"))["s"] or ZERO
    unsettled = period_unsettled(user, end, branch)
    outstanding = sum((inv.balance for inv in unsettled), ZERO)
    return {
        "collected": collected,
        "outstanding": outstanding,
        "unpaid_count": unsettled.count(),
    }


def first_payment_date(user, branch=None):
    """Date of the first successful payment in scope (where the period picker starts)."""
    payments = scoped_payments(user)
    if branch is not None:
        payments = payments.filter(invoice__branch=branch)
    first = payments.order_by("recorded_at").values_list("recorded_at", flat=True).first()
    return timezone.localtime(first).date() if first else None


def revenue_by(user, dimension, date_from=None, date_to=None):
    """dimension: 'branch' or 'sport'. Returns list of (name, total)."""
    payments = scoped_payments(user)
    if date_from:
        payments = payments.filter(recorded_at__date__gte=date_from)
    if date_to:
        payments = payments.filter(recorded_at__date__lte=date_to)
    field = "invoice__branch__name" if dimension == "branch" else "invoice__sport__name"
    rows = (
        payments.values(field)
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    return [(r[field] or "—", r["total"] or ZERO) for r in rows]


def revenue_trend(user, months=6, end=None):
    """N calendar months of collected revenue, ending with the month of `end`
    (default: the current month)."""
    payments = scoped_payments(user)
    end = end or timezone.localdate()
    out = []
    year, month = end.year, end.month
    buckets = []
    for _ in range(months):
        buckets.append((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    buckets.reverse()
    for y, m in buckets:
        total = payments.filter(
            recorded_at__year=y, recorded_at__month=m
        ).aggregate(s=Sum("amount"))["s"] or ZERO
        from datetime import date

        out.append((period_label(date(y, m, 1), "MONTHLY").split(" ")[0], total))
    return out


# ---------------------------------------------------------------- live view
def live_sessions(user):
    qs = Session.objects.filter(status=SessionStatus.LIVE).select_related(
        "batch", "batch__branch", "batch__sport", "coach"
    )
    if not (user.is_superuser and user.academy_id is None):
        qs = qs.filter(batch__branch__academy_id=user.academy_id)
    if user.is_manager:
        qs = qs.filter(batch__branch_id__in=branch_ids_for(user))
    elif user.is_coach:
        qs = qs.filter(coach=user)
    return qs.order_by("batch__branch__name")


def coach_roster_status(user):
    """All coaches in scope + whether they're currently running a session."""
    from apps.accounts.models import Role, User

    coaches = User.objects.filter(role=Role.COACH, is_active=True)
    if not (user.is_superuser and user.academy_id is None):
        coaches = coaches.filter(academy_id=user.academy_id)
    if user.is_manager:
        branch_ids = branch_ids_for(user)
        coaches = coaches.filter(
            coach_assignments__batch__branch_id__in=branch_ids
        ).distinct()

    live = {
        s.coach_id: s
        for s in live_sessions(user).all()
        if s.coach_id
    }
    rows = []
    for coach in coaches:
        session = live.get(coach.id)
        rows.append(
            {
                "coach": coach,
                "live": session is not None,
                "session": session,
                "venue": session.batch.branch.name if session else None,
            }
        )
    return rows
