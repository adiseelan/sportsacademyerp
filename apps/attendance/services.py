"""Session lifecycle: check-in (geo-fenced), attendance, close-out."""
from django.db import transaction
from django.utils import timezone

from apps.academy.geo import haversine_m

from .models import Attendance, CheckInMethod, Session, SessionStatus


class CheckInError(Exception):
    """Raised when a coach cannot start a session (with a user-safe message)."""


def get_or_create_session(batch, on_date):
    session, _ = Session.objects.get_or_create(batch=batch, date=on_date)
    return session


def roster_students(session):
    """Active students enrolled in this batch."""
    from apps.students.models import EnrollmentStatus, Student

    return (
        Student.objects.filter(
            enrollments__batch=session.batch,
            enrollments__status=EnrollmentStatus.ACTIVE,
        )
        .distinct()
        .order_by("full_name")
    )


@transaction.atomic
def perform_check_in(session, coach, lat=None, lng=None, manual_reason=""):
    if session.status in (SessionStatus.LIVE, SessionStatus.COMPLETED):
        raise CheckInError("This session has already been started.")

    branch = session.batch.branch
    distance = None
    if branch.has_geo and lat is not None and lng is not None:
        distance = haversine_m(branch.latitude, branch.longitude, lat, lng)

    within = distance is not None and distance <= branch.geofence_radius_m

    if within:
        session.check_in_method = CheckInMethod.GEO
        session.manual_flagged = False
        session.manual_reason = ""
    else:
        # Fall back to a flagged manual check-in — but only with a reason.
        if not manual_reason:
            if distance is not None:
                raise CheckInError(
                    f"You appear to be ~{int(distance)} m from the venue "
                    f"(allowed {branch.geofence_radius_m} m). Use manual check-in "
                    "with a reason if this is wrong."
                )
            raise CheckInError(
                "Location unavailable. Use manual check-in and provide a reason."
            )
        session.check_in_method = CheckInMethod.MANUAL
        session.manual_flagged = True
        session.manual_reason = manual_reason[:200]

    now = timezone.now()
    session.coach = coach
    session.status = SessionStatus.LIVE
    session.check_in_at = now
    session.start_at = now
    session.check_in_lat = lat
    session.check_in_lng = lng
    session.check_in_distance_m = distance
    session.save()

    _audit(coach, "session.start", session,
           f"{session.batch} ({session.check_in_method})")
    _notify_live(session)
    return session


@transaction.atomic
def submit_attendance(session, marks, user):
    """marks: {student_id: status}. Closes the session."""
    if session.status != SessionStatus.LIVE:
        raise CheckInError("Attendance can only be submitted for a live session.")

    valid_ids = set(roster_students(session).values_list("id", flat=True))
    now = timezone.now()
    for student_id, status in marks.items():
        if int(student_id) not in valid_ids:
            continue
        Attendance.objects.update_or_create(
            session=session,
            student_id=student_id,
            defaults={"status": status, "marked_at": now, "marked_by": user},
        )

    session.status = SessionStatus.COMPLETED
    session.end_at = now
    session.save(update_fields=["status", "end_at"])
    _audit(user, "attendance.submit", session,
           f"{len(marks)} students · {session.batch}")
    return session


# ---- integrations (kept lazy to avoid import cycles) -----------------
def _audit(actor, action, obj, summary):
    try:
        from apps.audit.services import record

        record(actor=actor, action=action, obj=obj, summary=summary)
    except Exception:
        pass


def _notify_live(session):
    try:
        from apps.notifications.engine import notify_session_started

        notify_session_started(session)
    except Exception:
        pass
