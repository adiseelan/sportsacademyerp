"""Admin & Manager dashboards (revenue, live status, KPIs)."""
from datetime import date, datetime

from urllib.parse import urlencode

from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.academy.models import Batch, Branch, Sport
from apps.academy.scoping import accessible_batches, accessible_branches, accessible_students
from apps.accounts.models import Role, User
from apps.accounts.permissions import admin_required, manager_required
from apps.audit.models import AuditLog
from apps.portal import analytics, charts, periods
from apps.students.models import Enrollment, EnrollmentStatus


def _parse_date(val):
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _filters(request):
    branch = None
    sport = None
    bid = request.GET.get("branch")
    sid = request.GET.get("sport")
    if bid:
        branch = accessible_branches(request.user).filter(pk=bid).first()
    if sid:
        sport = Sport.objects.filter(pk=sid, academy_id=request.user.academy_id).first()
    return {
        "date_from": _parse_date(request.GET.get("from")),
        "date_to": _parse_date(request.GET.get("to")),
        "branch": branch,
        "sport": sport,
    }


@admin_required
def admin_dashboard(request):
    """Academy-wide view for one reporting period (month or year) picked in the
    header (?period=2026-10 | ?period=2026; default: the current month)."""
    user = request.user
    today = timezone.localdate()
    period = periods.parse_period(request.GET.get("period"), today)
    start, end = period.start, period.end

    summary = analytics.period_summary(user, start, end)
    by_branch = analytics.revenue_by(user, "branch", start, end)
    by_sport = analytics.revenue_by(user, "sport", start, end)
    if period.is_year:
        trend = analytics.revenue_trend(user, months=12, end=date(start.year, 12, 1))
        trend_label = f"Jan – Dec {start.year}"
    else:
        trend = analytics.revenue_trend(user, months=6, end=start)
        trend_label = f"6 months to {period.label}"
    earliest = analytics.first_payment_date(user)
    students = accessible_students(user)

    ctx = {
        "period": period,
        "month_options": periods.month_options(today, earliest),
        "year_options": periods.year_options(today, earliest),
        "summary": summary,
        "trend_chart": charts.line_chart(trend),
        "trend_label": trend_label,
        "branch_chart": charts.bar_chart(by_branch[:8]),
        "sport_chart": charts.bar_chart(by_sport[:8]),
        "donut": charts.donut(float(summary["collected"]), float(summary["outstanding"])),
        "counts": {
            "students": students.count(),
            "new_students": students.filter(
                created_at__date__gte=start, created_at__date__lte=end
            ).count(),
            "batches": accessible_batches(user).filter(is_active=True).count(),
        },
        "live": analytics.live_sessions(user),
        "recent_payments": analytics.scoped_payments(user).filter(
            recorded_at__date__gte=start, recorded_at__date__lte=end
        )[:8],
    }
    return render(request, "portal/admin/dashboard.html", ctx)


@manager_required
def manager_dashboard(request):
    f = _filters(request)
    summary = analytics.revenue_summary(request.user, **f)
    by_sport = analytics.revenue_by(request.user, "sport", f["date_from"], f["date_to"])
    trend = analytics.revenue_trend(request.user, months=6)

    ctx = {
        "summary": summary,
        "trend_chart": charts.line_chart(trend),
        "sport_chart": charts.bar_chart(by_sport[:8]),
        "donut": charts.donut(float(summary["collected"]), float(summary["outstanding"])),
        "branches": accessible_branches(request.user),
        "counts": {
            "branches": accessible_branches(request.user).count(),
            "students": accessible_students(request.user).count(),
            "batches": accessible_batches(request.user).filter(is_active=True).count(),
        },
        "coach_status": analytics.coach_roster_status(request.user),
        "live": analytics.live_sessions(request.user),
        "sports": Sport.objects.filter(academy_id=request.user.academy_id),
        "filters": f,
    }
    return render(request, "portal/manager/dashboard.html", ctx)


# Cover art for branches without a photo: one of six court colours + the sports' icons.
_SPORT_EMOJI = [
    ("cricket", "🏏"), ("football", "⚽"), ("soccer", "⚽"), ("tennis", "🎾"), ("badminton", "🏸"),
    ("swim", "🏊"), ("basket", "🏀"), ("volley", "🏐"), ("hockey", "🏑"), ("athlet", "🏃"),
    ("skat", "⛸️"), ("chess", "♟️"), ("kabaddi", "🤼"), ("yoga", "🧘"), ("box", "🥊"),
]


def _sport_emoji(name):
    low = name.lower()
    return next((emoji for key, emoji in _SPORT_EMOJI if key in low), "🏅")


def _decorate_cover(branch):
    branch.cover_emojis = [_sport_emoji(s.name) for s in branch.sports.all()][:3] or ["🏟️"]
    branch.cover_variant = branch.pk % 6  # stable colour per branch
    return branch


def _filtered_branches(request):
    """Apply ?q= and ?status= to the user's branches; returns (qs, q, status)."""
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    branches = accessible_branches(request.user).prefetch_related("sports", "managers")
    if q:
        branches = branches.filter(Q(name__icontains=q) | Q(address__icontains=q) | Q(code__icontains=q))
    if status == "active":
        branches = branches.filter(is_active=True)
    elif status == "inactive":
        branches = branches.filter(is_active=False)
    else:
        status = ""
    return branches, q, status


@admin_required
def branches_list(request):
    """Branches overview: photo cards with search + status filter (?q=, ?status=)."""
    bid = request.GET.get("branch", "")
    if bid.isdigit():  # old links (?branch=<id>) → the branch page
        return redirect("portal:branch_detail", pk=int(bid))
    branches, q, status = _filtered_branches(request)
    return render(request, "portal/admin/branches.html", {
        "branches": [_decorate_cover(b) for b in branches],
        "total": accessible_branches(request.user).count(),
        "q": q,
        "status": status,
        "keep_q": urlencode({"q": q}) + "&" if q else "",
    })


FEE_FILTERS = (("all", "All"), ("paid", "Paid"), ("unpaid", "Unpaid"))
_OLD_FEE_VIEWS = {"collected": "paid", "outstanding": "unpaid"}  # links from before the single table


def _branch_fees(request, branch):
    """Fees tab: Collected / Outstanding tiles + one table of who paid and who hasn't.

    Paid rows are the period's payments (they add up to Collected); unpaid rows are the
    invoices still open on the period's last day, arrears included (they add up to
    Outstanding). ?show=all|paid|unpaid filters the table; the tiles never change.
    """
    user = request.user
    today = timezone.localdate()
    period = periods.parse_period(request.GET.get("period"), today)
    show = request.GET.get("show") or _OLD_FEE_VIEWS.get(request.GET.get("view"), "all")
    if show not in dict(FEE_FILTERS):
        show = "all"

    paid = [
        {
            "paid": True,
            "obj": p,
            "student": p.student,
            "date": timezone.localtime(p.recorded_at).date(),
            "amount": p.amount,
        }
        for p in analytics.period_payments(user, period.start, period.end, branch=branch)
        .select_related("student", "invoice", "invoice__sport")
    ]
    unpaid = [
        {"paid": False, "obj": i, "student": i.student, "date": i.due_date, "amount": i.balance}
        for i in analytics.period_unsettled(user, period.end, branch=branch).select_related("student", "sport")
    ]
    rows = {"all": paid + unpaid, "paid": paid, "unpaid": unpaid}[show]
    # A–Z by student so one student's payment and remaining balance sit together.
    rows.sort(key=lambda r: (r["student"].full_name.lower(), not r["paid"], r["date"]))

    keep = "tab=fees&" if show == "all" else f"tab=fees&show={show}&"
    counts = {"all": len(paid) + len(unpaid), "paid": len(paid), "unpaid": len(unpaid)}
    earliest = analytics.first_payment_date(user, branch=branch)
    return {
        "period": period,
        "period_prefix": keep,
        "month_options": periods.month_options(today, earliest),
        "year_options": periods.year_options(today, earliest),
        "summary": analytics.period_summary(user, period.start, period.end, branch=branch),
        "show": show,
        "fee_filters": [
            {
                "value": value,
                "label": label,
                "count": counts[value],
                "query": f"tab=fees&period={period.value}" + ("" if value == "all" else f"&show={value}"),
            }
            for value, label in FEE_FILTERS
        ],
        "fee_rows": rows,
    }


@admin_required
def branch_detail(request, pk):
    """One branch, full page (tabs: overview | batches | students | fees).
    "← All branches" goes back to the grid."""
    selected = get_object_or_404(accessible_branches(request.user), pk=pk)
    tab = request.GET.get("tab")
    if tab not in ("batches", "students", "fees"):
        tab = "overview"
    # Students currently at this branch (any enrollment here that isn't withdrawn).
    enrollments = (
        Enrollment.objects.filter(branch=selected)
        .exclude(status=EnrollmentStatus.WITHDRAWN)
        .select_related("batch", "sport")
        .order_by("sport__name", "batch__name")
    )
    students = (
        accessible_students(request.user)
        .filter(pk__in=enrollments.values("student_id"))
        .prefetch_related(Prefetch("enrollments", queryset=enrollments, to_attr="branch_enrollments"))
        .order_by("full_name")
    )
    last = (
        AuditLog.objects.filter(
            content_type=ContentType.objects.get_for_model(Branch), object_id=str(selected.pk)
        )
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    fees = _branch_fees(request, selected) if tab == "fees" else {}
    return render(request, "portal/admin/branch_detail.html", {
        **fees,
        "selected": selected,
        "tab": tab,
        "batches": selected.batches.select_related("sport").prefetch_related("coaches").order_by("sport__name", "name"),
        "branch_managers": selected.managers.order_by("full_name"),
        "students": students,
        "last_updated": last or selected.created_at,
    })


@admin_required
def coaches_list(request):
    rows = analytics.coach_roster_status(request.user)
    return render(request, "portal/admin/coaches.html", {"rows": rows})


@admin_required
def managers_list(request):
    managers = (
        User.objects.filter(academy_id=request.user.academy_id, role=Role.MANAGER)
        .prefetch_related("managed_branches")
        .order_by("full_name")
    )
    return render(request, "portal/admin/managers.html", {"managers": managers})
