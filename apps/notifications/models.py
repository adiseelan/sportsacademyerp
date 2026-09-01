from django.conf import settings
from django.db import models
from django.utils import timezone


class Event(models.TextChoices):
    FEE_DUE = "fee_due", "Fee due soon"
    FEE_OVERDUE = "fee_overdue", "Fee overdue"
    PAYMENT_RECEIVED = "payment_received", "Payment received"
    SESSION_STARTED = "session_started", "Session started"
    ROSTER_CHANGE = "roster_change", "Roster/schedule change"
    COACH_NO_SHOW = "coach_no_show", "Coach no-show"
    GENERAL = "general", "General"


class Notification(models.Model):
    """In-app notification (one row per recipient)."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    event = models.CharField(max_length=20, choices=Event.choices, default=Event.GENERAL)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=400, blank=True)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read"])]

    def __str__(self):
        return f"{self.recipient.get_short_name()} · {self.title}"


class DeliveryLog(models.Model):
    """Audit of out-of-app channel dispatches (email/SMS/WhatsApp/push)."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delivery_logs"
    )
    channel = models.CharField(max_length=20)
    target = models.CharField(max_length=160, blank=True)
    event = models.CharField(max_length=20, blank=True)
    ok = models.BooleanField(default=True)
    provider_ref = models.CharField(max_length=160, blank=True)
    detail = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.channel} → {self.recipient.get_short_name()} ({'ok' if self.ok else 'fail'})"
