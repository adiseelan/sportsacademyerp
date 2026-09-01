"""
Sessions (one occurrence of a batch) + per-student attendance.
Coach check-in is geo-fenced against the branch location, with a flagged
manual fallback for when GPS is unavailable.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class SessionStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    LIVE = "LIVE", "Live"
    COMPLETED = "COMPLETED", "Completed"
    CANCELLED = "CANCELLED", "Cancelled"


class CheckInMethod(models.TextChoices):
    GEO = "GEO", "Geo-verified"
    MANUAL = "MANUAL", "Manual (flagged)"


class Session(models.Model):
    batch = models.ForeignKey("academy.Batch", on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField()
    status = models.CharField(
        max_length=10, choices=SessionStatus.choices, default=SessionStatus.SCHEDULED
    )
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="ran_sessions"
    )

    check_in_at = models.DateTimeField(null=True, blank=True)
    check_in_lat = models.FloatField(null=True, blank=True)
    check_in_lng = models.FloatField(null=True, blank=True)
    check_in_distance_m = models.FloatField(null=True, blank=True)
    check_in_method = models.CharField(max_length=10, choices=CheckInMethod.choices, blank=True)
    manual_reason = models.CharField(max_length=200, blank=True)
    manual_flagged = models.BooleanField(default=False)

    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("batch", "date")
        ordering = ["-date", "-start_at"]
        indexes = [models.Index(fields=["status", "date"])]

    def __str__(self):
        return f"{self.batch} · {self.date}"

    @property
    def academy_id(self):
        return self.batch.branch.academy_id

    @property
    def is_live(self):
        return self.status == SessionStatus.LIVE

    @property
    def duration_minutes(self):
        if self.start_at and self.end_at:
            return round((self.end_at - self.start_at).total_seconds() / 60)
        return None


class AttendanceStatus(models.TextChoices):
    PRESENT = "PRESENT", "Present"
    ABSENT = "ABSENT", "Absent"
    LATE = "LATE", "Late"


class Attendance(models.Model):
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="records")
    student = models.ForeignKey("students.Student", on_delete=models.CASCADE, related_name="attendance")
    status = models.CharField(max_length=10, choices=AttendanceStatus.choices)
    marked_at = models.DateTimeField(default=timezone.now)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        unique_together = ("session", "student")
        ordering = ["student__full_name"]

    def __str__(self):
        return f"{self.student.full_name} · {self.status} · {self.session.date}"
