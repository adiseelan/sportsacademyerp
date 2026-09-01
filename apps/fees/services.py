"""
Fee/payment service layer. All money mutations go through here so the ledger,
invoice status, audit log and notifications stay consistent.
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .gateways import get_gateway
from .models import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    Period,
    StudentFee,
    StudentFeeStatus,
)
from .periods import PERIOD_MONTHS, add_months, period_label

ZERO = Decimal("0.00")
TWO_DP = Decimal("0.01")
DEFAULT_GRACE_DAYS = 7


# ---------------------------------------------------------------- assignment
@transaction.atomic
def assign_fee(student, sport, plan, start_date=None, actor=None, create_first_invoice=True):
    start_date = start_date or timezone.localdate()
    end_date = None
    if plan.plan_type == "PACKAGE":
        end_date = add_months(start_date, PERIOD_MONTHS.get(plan.period, 1))

    # Retire any existing active assignment for this student+sport.
    StudentFee.objects.filter(
        student=student, sport=sport, status=StudentFeeStatus.ACTIVE
    ).update(status=StudentFeeStatus.CANCELLED)

    fee = StudentFee.objects.create(
        student=student,
        sport=sport,
        plan=plan,
        start_date=start_date,
        end_date=end_date,
        next_due_date=start_date,
        created_by=actor,
    )
    _audit(actor, "fee.assign", fee, f"{student.full_name} · {sport.name} · {plan.name}")

    invoice = None
    if create_first_invoice:
        invoice = generate_invoice(fee, period_start=start_date, actor=actor)
    return fee, invoice


@transaction.atomic
def generate_invoice(student_fee, period_start=None, actor=None):
    period_start = period_start or student_fee.next_due_date or timezone.localdate()
    plan = student_fee.plan
    label = period_label(period_start, plan.period)

    # Attribute the invoice to the branch where this sport is enrolled.
    from apps.students.models import EnrollmentStatus

    enrollment = (
        student_fee.student.enrollments.filter(
            sport=student_fee.sport, status=EnrollmentStatus.ACTIVE
        )
        .select_related("branch")
        .first()
    )

    invoice = Invoice.objects.create(
        academy_id=student_fee.student.academy_id,
        student=student_fee.student,
        student_fee=student_fee,
        sport=student_fee.sport,
        branch=enrollment.branch if enrollment else None,
        amount=plan.amount,
        period_label=label,
        issued_date=period_start,
        due_date=period_start + timedelta(days=DEFAULT_GRACE_DAYS),
        created_by=actor,
    )
    invoice.recompute()

    # Advance the schedule for the next cycle.
    months = PERIOD_MONTHS.get(plan.period, 1)
    student_fee.next_due_date = add_months(period_start, months)
    student_fee.save(update_fields=["next_due_date"])

    _notify(invoice, "fee_due")
    return invoice


# ---------------------------------------------------------------- payments
@transaction.atomic
def record_payment(
    invoice,
    amount,
    method=PaymentMethod.CASH,
    actor=None,
    kind=PaymentKind.PAYMENT,
    gateway="manual",
    gateway_ref="",
    note="",
    status=PaymentStatus.SUCCESS,
):
    amount = Decimal(amount)
    payment = Payment.objects.create(
        academy_id=invoice.academy_id,
        invoice=invoice,
        student=invoice.student,
        amount=amount,
        kind=kind,
        method=method,
        status=status,
        gateway=gateway,
        gateway_ref=gateway_ref,
        recorded_by=actor,
        note=note,
    )
    invoice.recompute()
    verb = "payment.refund" if kind == PaymentKind.REFUND else "payment.record"
    _audit(actor, verb, payment, f"₹{amount} · {invoice.number} · {method}")
    if status == PaymentStatus.SUCCESS and kind == PaymentKind.PAYMENT:
        _notify(invoice, "payment_received", payment=payment)
    return payment


def record_manual_payment(invoice, amount, method, actor, note=""):
    return record_payment(
        invoice, amount, method=method, actor=actor, gateway="manual", note=note
    )


# ---------------------------------------------------------------- online flow
def create_online_order(invoice):
    gateway = get_gateway()
    return gateway, gateway.create_order(invoice, invoice.balance)


@transaction.atomic
def confirm_online_payment(invoice, payload, actor=None):
    gateway = get_gateway()
    if not gateway.verify(payload):
        raise ValueError("Payment could not be verified. No money was recorded.")
    return record_payment(
        invoice,
        invoice.balance,
        method=PaymentMethod.ONLINE,
        actor=actor,
        gateway=gateway.name,
        gateway_ref=gateway.reference(payload),
        note="Online payment",
    )


# ---------------------------------------------------------------- adjustments
@transaction.atomic
def apply_discount(invoice, amount, actor=None, note=""):
    invoice.discount = (invoice.discount + Decimal(amount)).quantize(TWO_DP)
    invoice.save(update_fields=["discount"])
    invoice.recompute()
    _audit(actor, "fee.discount", invoice, f"₹{amount} off {invoice.number}")
    return invoice


@transaction.atomic
def waive_invoice(invoice, actor=None, reason=""):
    invoice.status = InvoiceStatus.WAIVED
    invoice.notes = (invoice.notes + f" | Waived: {reason}").strip(" |")[:300]
    invoice.save(update_fields=["status", "notes"])
    _audit(actor, "fee.waive", invoice, f"{invoice.number} waived: {reason}")
    return invoice


@transaction.atomic
def refund_payment(invoice, amount, actor=None, note=""):
    return record_payment(
        invoice,
        Decimal(amount).copy_abs() * Decimal("-1"),
        method=PaymentMethod.ADJUSTMENT,
        actor=actor,
        kind=PaymentKind.REFUND,
        gateway="manual",
        note=note or "Refund",
    )


# ---------------------------------------------------------------- overdue job
@transaction.atomic
def flag_overdue(academy=None):
    """Mark unpaid past-due invoices overdue and fire reminders. Idempotent."""
    today = timezone.localdate()
    qs = Invoice.objects.filter(
        due_date__lt=today,
        status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
    )
    if academy is not None:
        qs = qs.filter(academy=academy)

    flagged = 0
    for inv in qs.select_related("student", "sport", "academy"):
        inv.status = InvoiceStatus.OVERDUE
        inv.save(update_fields=["status"])
        _notify(inv, "fee_overdue")
        flagged += 1
    return flagged


# ---------------------------------------------------------------- integrations
def _audit(actor, action, obj, summary):
    try:
        from apps.audit.services import record

        record(actor=actor, action=action, obj=obj, summary=summary)
    except Exception:
        pass


def _notify(invoice, event, payment=None):
    try:
        from apps.notifications.engine import notify_fee_event

        notify_fee_event(invoice, event, payment=payment)
    except Exception:
        pass
