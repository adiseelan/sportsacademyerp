"""
Fee engine + unified payment ledger.

FeePlan (template) -> StudentFee (assignment per student+sport) -> Invoice
(a bill for one period) -> Payment (ledger entries: online or manual, plus
refunds/adjustments/waivers). Online and offline money land in the SAME ledger
and are reflected identically to Admin, Manager and Parent.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

TWO_DP = Decimal("0.01")
ZERO = Decimal("0.00")


class PlanType(models.TextChoices):
    FIXED_MONTHLY = "FIXED_MONTHLY", "Fixed monthly (recurring)"
    PACKAGE = "PACKAGE", "Package (validity period)"


class Period(models.TextChoices):
    MONTHLY = "MONTHLY", "Monthly"
    QUARTERLY = "QUARTERLY", "Quarterly"
    YEARLY = "YEARLY", "Yearly"


class FeePlan(models.Model):
    academy = models.ForeignKey("academy.Academy", on_delete=models.CASCADE, related_name="fee_plans")
    name = models.CharField(max_length=120)
    sport = models.ForeignKey(
        "academy.Sport", on_delete=models.SET_NULL, null=True, blank=True, related_name="fee_plans"
    )
    plan_type = models.CharField(max_length=15, choices=PlanType.choices, default=PlanType.FIXED_MONTHLY)
    period = models.CharField(max_length=10, choices=Period.choices, default=Period.MONTHLY)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (₹{self.amount}/{self.get_period_display().lower()})"


class StudentFeeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    EXPIRED = "EXPIRED", "Expired"
    CANCELLED = "CANCELLED", "Cancelled"


class StudentFee(models.Model):
    """A fee plan assigned to a student for a specific sport."""

    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="fees")
    sport = models.ForeignKey("academy.Sport", on_delete=models.PROTECT, related_name="student_fees")
    plan = models.ForeignKey(FeePlan, on_delete=models.PROTECT, related_name="assignments")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True, help_text="Package validity end.")
    next_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=10, choices=StudentFeeStatus.choices, default=StudentFeeStatus.ACTIVE
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "next_due_date"])]

    def __str__(self):
        return f"{self.student.full_name} · {self.sport.name} · {self.plan.name}"

    @property
    def academy_id(self):
        return self.student.academy_id

    @property
    def is_package(self):
        return self.plan.plan_type == PlanType.PACKAGE


class InvoiceStatus(models.TextChoices):
    DUE = "DUE", "Due"
    PARTIAL = "PARTIAL", "Partially paid"
    PAID = "PAID", "Paid"
    OVERDUE = "OVERDUE", "Overdue"
    WAIVED = "WAIVED", "Waived"
    CANCELLED = "CANCELLED", "Cancelled"


class Invoice(models.Model):
    academy = models.ForeignKey("academy.Academy", on_delete=models.CASCADE, related_name="invoices")
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="invoices")
    student_fee = models.ForeignKey(
        StudentFee, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    sport = models.ForeignKey("academy.Sport", on_delete=models.PROTECT, related_name="invoices")
    branch = models.ForeignKey(
        "academy.Branch", on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices"
    )
    number = models.CharField(max_length=30, unique=True, blank=True)
    period_label = models.CharField(max_length=30, blank=True)

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=ZERO)

    issued_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=InvoiceStatus.choices, default=InvoiceStatus.DUE)
    notes = models.CharField(max_length=300, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-issued_date", "-id"]
        indexes = [models.Index(fields=["status", "due_date"])]

    def __str__(self):
        return self.number or f"Invoice #{self.pk}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.number:
            self.number = f"INV-{self.issued_date:%Y}-{self.pk:06d}"
            super().save(update_fields=["number"])

    # ---- money math ---------------------------------------------------
    @property
    def net_payable(self):
        return (self.amount - self.discount).quantize(TWO_DP)

    @property
    def balance(self):
        return (self.net_payable - self.amount_paid).quantize(TWO_DP)

    @property
    def is_settled(self):
        return self.status in (InvoiceStatus.PAID, InvoiceStatus.WAIVED, InvoiceStatus.CANCELLED)

    def recompute(self, save=True):
        """Recalculate amount_paid from the ledger and refresh status."""
        agg = self.payments.filter(status=PaymentStatus.SUCCESS).aggregate(
            paid=models.Sum("amount")
        )
        self.amount_paid = (agg["paid"] or ZERO).quantize(TWO_DP)

        if self.status in (InvoiceStatus.WAIVED, InvoiceStatus.CANCELLED):
            pass
        elif self.balance <= ZERO and self.net_payable > ZERO:
            self.status = InvoiceStatus.PAID
        elif self.amount_paid > ZERO:
            self.status = (
                InvoiceStatus.OVERDUE
                if self._is_past_due()
                else InvoiceStatus.PARTIAL
            )
        else:
            self.status = InvoiceStatus.OVERDUE if self._is_past_due() else InvoiceStatus.DUE

        if save:
            self.save(update_fields=["amount_paid", "status"])
        return self

    def _is_past_due(self):
        return self.due_date < timezone.localdate()


class PaymentKind(models.TextChoices):
    PAYMENT = "PAYMENT", "Payment"
    REFUND = "REFUND", "Refund"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class PaymentMethod(models.TextChoices):
    ONLINE = "ONLINE", "Online (gateway)"
    CASH = "CASH", "Cash"
    UPI = "UPI", "UPI (offline)"
    BANK = "BANK", "Bank transfer"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class PaymentStatus(models.TextChoices):
    SUCCESS = "SUCCESS", "Success"
    PENDING = "PENDING", "Pending"
    FAILED = "FAILED", "Failed"


class Payment(models.Model):
    """One ledger entry. Positive = money in; refunds stored as negatives."""

    academy = models.ForeignKey("academy.Academy", on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, null=True, blank=True, related_name="payments"
    )
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="payments")

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    kind = models.CharField(max_length=12, choices=PaymentKind.choices, default=PaymentKind.PAYMENT)
    method = models.CharField(max_length=12, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.SUCCESS)

    gateway = models.CharField(max_length=30, blank=True)
    gateway_ref = models.CharField(max_length=120, blank=True)
    receipt_number = models.CharField(max_length=30, blank=True, unique=True, null=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    recorded_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["status", "recorded_at"])]

    def __str__(self):
        return f"{self.receipt_number or 'PMT'} · ₹{self.amount} · {self.get_method_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.receipt_number and self.status == PaymentStatus.SUCCESS:
            self.receipt_number = f"RCP-{self.recorded_at:%Y}-{self.pk:06d}"
            super().save(update_fields=["receipt_number"])
