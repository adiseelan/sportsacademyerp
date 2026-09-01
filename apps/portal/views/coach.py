"""Coach app: today's sessions, geo check-in, attendance, history."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.academy.scoping import accessible_batches
from apps.accounts.models import Role
from apps.accounts.permissions import role_required
from apps.attendance import services as att_services
from apps.attendance.models import Session, SessionStatus
from apps.portal.forms import ManualCheckinForm


@role_required(Role.COACH, Role.ADMIN)
def coach_today(request):
    today = timezone.localdate()
    batches = accessible_batches(request.user).filter(is_active=True).select_related(
        "branch", "sport"
    )
    rows = []
    for batch in batches:
        if not batch.runs_on(today) and not batch.sessions.filter(date=today).exists():
            continue
        session = att_services.get_or_create_session(batch, today)
        rows.append({"batch": batch, "session": session})
    live = Session.objects.filter(
        coach=request.user, status=SessionStatus.LIVE
    ).select_related("batch")
    return render(
        request,
        "portal/coach/today.html",
        {"rows": rows, "today": today, "live": live},
    )


@role_required(Role.COACH, Role.ADMIN)
def coach_checkin(request, batch_id):
    batch = get_object_or_404(accessible_batches(request.user), pk=batch_id)
    today = timezone.localdate()
    session = att_services.get_or_create_session(batch, today)

    if session.status == SessionStatus.LIVE:
        return redirect("portal:coach_attendance", session_id=session.pk)
    if session.status == SessionStatus.COMPLETED:
        messages.info(request, "Today's session is already completed.")
        return redirect("portal:coach_today")

    if request.method == "POST":
        lat = request.POST.get("lat")
        lng = request.POST.get("lng")
        manual_reason = request.POST.get("manual_reason", "").strip()
        try:
            lat = float(lat) if lat else None
            lng = float(lng) if lng else None
        except ValueError:
            lat = lng = None
        try:
            att_services.perform_check_in(
                session, request.user, lat=lat, lng=lng, manual_reason=manual_reason
            )
        except att_services.CheckInError as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "portal/coach/checkin.html",
                {"batch": batch, "session": session, "manual_form": ManualCheckinForm()},
            )
        messages.success(request, "Checked in. Session started.")
        return redirect("portal:coach_attendance", session_id=session.pk)

    return render(
        request,
        "portal/coach/checkin.html",
        {"batch": batch, "session": session, "manual_form": ManualCheckinForm()},
    )


@role_required(Role.COACH, Role.ADMIN)
def coach_attendance(request, session_id):
    session = get_object_or_404(
        Session.objects.select_related("batch", "batch__branch", "batch__sport"),
        pk=session_id,
    )
    # Only the running coach (or an admin) may mark this session.
    if not request.user.is_admin and session.coach_id != request.user.id:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied

    roster = att_services.roster_students(session)
    existing = {a.student_id: a.status for a in session.records.all()}

    if request.method == "POST" and session.status == SessionStatus.LIVE:
        marks = {}
        for student in roster:
            val = request.POST.get(f"status_{student.id}")
            if val in ("PRESENT", "ABSENT", "LATE"):
                marks[student.id] = val
        att_services.submit_attendance(session, marks, request.user)
        messages.success(request, f"Attendance submitted for {len(marks)} students.")
        return redirect("portal:coach_history")

    roster_rows = [{"student": s, "status": existing.get(s.id)} for s in roster]
    return render(
        request,
        "portal/coach/attendance.html",
        {"session": session, "roster_rows": roster_rows, "roster_count": len(roster_rows)},
    )


@role_required(Role.COACH, Role.ADMIN)
def coach_history(request):
    sessions = (
        Session.objects.filter(coach=request.user)
        .exclude(status=SessionStatus.SCHEDULED)
        .select_related("batch", "batch__branch", "batch__sport")
        .prefetch_related("records")
        .order_by("-date", "-start_at")[:60]
    )
    return render(request, "portal/coach/history.html", {"sessions": sessions})
