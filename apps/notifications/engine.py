"""
Central notification service. Domain code calls the high-level helpers
(notify_fee_event, notify_session_started, ...) and the engine works out
*who* should hear about it and over *which* channels.
"""
import logging

from .backends import get_backend
from .models import Event

log = logging.getLogger("erp.security")

# Default channel routing per event. Parents get multi-channel; staff in-app.
EVENT_CHANNELS = {
    Event.FEE_DUE: ("inapp", "email", "sms", "whatsapp", "push"),
    Event.FEE_OVERDUE: ("inapp", "email", "sms", "whatsapp", "push"),
    Event.PAYMENT_RECEIVED: ("inapp", "email"),
    Event.SESSION_STARTED: ("inapp",),
    Event.ROSTER_CHANGE: ("inapp", "push"),
    Event.COACH_NO_SHOW: ("inapp", "push"),
    Event.GENERAL: ("inapp",),
}


def dispatch(recipient, event, title, body, url="", channels=None):
    """Send one notification to one recipient across the given channels."""
    if recipient is None:
        return
    channels = channels or EVENT_CHANNELS.get(event, ("inapp",))
    for channel in channels:
        backend = get_backend(channel)
        if not backend:
            continue
        try:
            backend.send(recipient, title, body, event=event, url=url)
        except Exception as exc:  # isolation: one channel failing != request failing
            log.warning("Channel %s failed: %s", channel, exc)


def dispatch_many(recipients, event, title, body, url="", channels=None):
    seen = set()
    for r in recipients:
        if r and r.pk not in seen:
            seen.add(r.pk)
            dispatch(r, event, title, body, url=url, channels=channels)


# ---------------------------------------------------------------- audiences
def parents_of(student):
    return list(student.guardians.filter(is_active=True))


def managers_of(branch):
    from apps.academy.models import ManagerAssignment

    return [
        a.manager
        for a in ManagerAssignment.objects.select_related("manager").filter(
            branch=branch, is_active=True, manager__is_active=True
        )
    ]


def admins_of(academy):
    from apps.accounts.models import Role, User

    return list(User.objects.filter(academy=academy, role=Role.ADMIN, is_active=True))


# ---------------------------------------------------------------- fee events
def notify_fee_event(invoice, event, payment=None):
    student = invoice.student
    money = f"₹{invoice.balance}"
    if event == "payment_received" and payment is not None:
        title = f"Payment received · {invoice.sport.name}"
        body = (
            f"₹{payment.amount} received for {student.full_name} "
            f"({invoice.period_label}). Receipt {payment.receipt_number or '—'}."
        )
        ev = Event.PAYMENT_RECEIVED
    elif event == "fee_overdue":
        title = f"Fee overdue · {invoice.sport.name}"
        body = (
            f"{money} is overdue for {student.full_name} "
            f"({invoice.period_label}, due {invoice.due_date:%d %b})."
        )
        ev = Event.FEE_OVERDUE
    else:  # fee_due
        title = f"Fee due · {invoice.sport.name}"
        body = (
            f"{money} due for {student.full_name} "
            f"({invoice.period_label}) by {invoice.due_date:%d %b}."
        )
        ev = Event.FEE_DUE

    url = f"/app/fees/invoice/{invoice.pk}/"
    # Parents hear about it directly; managers + admins get an in-app copy.
    dispatch_many(parents_of(student), ev, title, body, url=url)

    branch_ids = list(
        student.enrollments.values_list("branch", flat=True).distinct()
    )
    from apps.academy.models import Branch

    staff = []
    for branch in Branch.objects.filter(id__in=branch_ids):
        staff += managers_of(branch)
    staff += admins_of(invoice.academy)
    dispatch_many(staff, ev, title, body, url=url, channels=("inapp",))


# ---------------------------------------------------------------- session events
def notify_session_started(session):
    branch = session.batch.branch
    coach_name = session.coach.get_short_name() if session.coach else "A coach"
    title = "Session started"
    flag = " (manual check-in)" if session.manual_flagged else ""
    body = f"{coach_name} started {session.batch} at {branch.name}{flag}."
    url = "/app/live/"
    audience = managers_of(branch) + admins_of(branch.academy)
    dispatch_many(audience, Event.SESSION_STARTED, title, body, url=url, channels=("inapp",))


def notify_roster_change(batch, message):
    from apps.academy.models import CoachAssignment

    coaches = [a.coach for a in CoachAssignment.objects.filter(batch=batch, is_active=True)]
    dispatch_many(
        coaches, Event.ROSTER_CHANGE, "Roster/schedule change", message, url="/app/"
    )


def notify_manual_reminder(invoice, actor=None):
    """Manager/Admin manually nudging a parent about a due fee."""
    notify_fee_event(invoice, "fee_overdue" if invoice.status == "OVERDUE" else "fee_due")
