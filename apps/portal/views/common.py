"""Home dispatcher, notifications, live view, profile, error handlers."""
import re

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.accounts.permissions import role_required
from apps.accounts.models import Role
from apps.notifications.models import Notification
from apps.portal import analytics


@login_required
def home(request):
    """Route each role to its own dashboard."""
    u = request.user
    if u.is_admin:
        return redirect("portal:admin_dashboard")
    if u.is_manager:
        return redirect("portal:manager_dashboard")
    if u.is_coach:
        return redirect("portal:coach_today")
    if u.is_parent:
        return redirect("portal:parent_home")
    return redirect("accounts:logout")


@login_required
def notifications_list(request):
    notes = Notification.objects.filter(recipient=request.user)[:100]
    return render(request, "portal/notifications.html", {"notes": notes})


@login_required
@require_POST
def notification_read(request, pk):
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    note.is_read = True
    note.save(update_fields=["is_read"])
    return redirect(note.url or "portal:notifications")


@login_required
@require_POST
def notification_dismiss(request, pk):
    """Remove one notification from the recipient's list (the grey ✕ button)."""
    note = get_object_or_404(Notification, pk=pk, recipient=request.user)
    note.delete()
    if request.headers.get("X-Requested-With") == "fetch":
        unread = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return JsonResponse({"ok": True, "unread": unread})
    return redirect("portal:notifications")


@login_required
@require_POST
def notifications_read_all(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect("portal:notifications")


@login_required
def profile(request):
    return render(request, "portal/profile.html", {})


@role_required(Role.ADMIN)
def audit_log(request):
    from apps.audit.models import AuditLog

    action = request.GET.get("action", "").strip()
    events = AuditLog.objects.select_related("actor")
    if action:
        events = events.filter(action=action)
    actions = (
        AuditLog.objects.values_list("action", flat=True).distinct().order_by("action")
    )
    return render(
        request,
        "portal/admin/audit.html",
        {"events": events[:300], "actions": actions, "action": action},
    )


# ---------------------------------------------------------------- live view
@role_required(Role.ADMIN, Role.MANAGER)
def live_page(request):
    return render(request, "portal/live.html", {})


def _live_actions(user, session):
    """Items for the ⋮ (more_vert) menu on one live-session row, by role."""
    actions = []
    if user.is_admin:  # these pages are admin/coach-only
        actions.append({"icon": "📋", "label": "View attendance", "sub": "Mark or review this session",
                        "url": reverse("portal:coach_attendance", args=[session.pk])})
        actions.append({"icon": "✏️", "label": "Edit batch", "sub": session.batch.name,
                        "url": reverse("portal:batch_edit", args=[session.batch_id])})
    coach = session.coach
    if coach and coach.phone:
        dial = re.sub(r"[^+\d]", "", coach.phone)
        if dial:
            actions.append({"icon": "📞", "label": "Call coach", "sub": coach.phone, "url": f"tel:{dial}"})
    if coach and coach.email:
        actions.append({"icon": "✉️", "label": "Email coach", "sub": coach.email, "url": f"mailto:{coach.email}"})
    return actions


@role_required(Role.ADMIN, Role.MANAGER)
def live_json(request):
    """Polled by the live page every few seconds (near real-time)."""
    rows = []
    for s in analytics.live_sessions(request.user):
        rows.append(
            {
                "id": s.pk,
                "coach": s.coach.get_short_name() if s.coach else "—",
                "batch": str(s.batch),
                "venue": s.batch.branch.name,
                "sport": s.batch.sport.name,
                "since": timezone.localtime(s.start_at).strftime("%H:%M") if s.start_at else "",
                "manual": s.manual_flagged,
                "actions": _live_actions(request.user, s),
            }
        )
    return JsonResponse(
        {"count": len(rows), "sessions": rows, "as_of": timezone.localtime().strftime("%H:%M:%S")}
    )


# ---------------------------------------------------------------- errors
def error_403(request, exception=None):
    return render(request, "portal/errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "portal/errors/404.html", status=404)


def error_500(request):
    return render(request, "portal/errors/500.html", status=500)
