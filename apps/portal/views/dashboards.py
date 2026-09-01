"""Admin & Manager dashboards (revenue, live status, KPIs)."""
from datetime import datetime

from django.shortcuts import render

from apps.academy.models import Batch, Branch, Sport
from apps.academy.scoping import accessible_batches, accessible_branches, accessible_students
from apps.accounts.models import Role, User
from apps.accounts.permissions import admin_required, manager_required
from apps.portal import analytics, charts


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
    f = _filters(request)
    summary = analytics.revenue_summary(request.user, **f)
    by_branch = analytics.revenue_by(request.user, "branch", f["date_from"], f["date_to"])
    by_sport = analytics.revenue_by(request.user, "sport", f["date_from"], f["date_to"])
    trend = analytics.revenue_trend(request.user, months=6)

    ctx = {
        "summary": summary,
        "trend_chart": charts.line_chart(trend),
        "branch_chart": charts.bar_chart(by_branch[:8]),
        "sport_chart": charts.bar_chart(by_sport[:8]),
        "donut": charts.donut(float(summary["collected"]), float(summary["outstanding"])),
        "counts": {
            "branches": accessible_branches(request.user).count(),
            "students": accessible_students(request.user).count(),
            "coaches": User.objects.filter(
                academy_id=request.user.academy_id, role=Role.COACH, is_active=True
            ).count(),
            "managers": User.objects.filter(
                academy_id=request.user.academy_id, role=Role.MANAGER, is_active=True
            ).count(),
            "batches": accessible_batches(request.user).filter(is_active=True).count(),
        },
        "live": analytics.live_sessions(request.user),
        "recent_payments": analytics.scoped_payments(request.user)[:8],
        "branches": accessible_branches(request.user),
        "sports": Sport.objects.filter(academy_id=request.user.academy_id),
        "filters": f,
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


@admin_required
def branches_list(request):
    branches = accessible_branches(request.user).prefetch_related("sports", "managers")
    return render(request, "portal/admin/branches.html", {"branches": branches})


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
