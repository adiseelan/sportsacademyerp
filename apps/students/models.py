"""
Students, their guardians (siblings supported), and per-batch enrollments.
A student may enrol in many sports/batches across branches simultaneously.
"""
from datetime import date

from django.conf import settings
from django.db import models
from django.utils import timezone


class StudentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class Student(models.Model):
    academy = models.ForeignKey(
        "academy.Academy", on_delete=models.CASCADE, related_name="students"
    )
    full_name = models.CharField(max_length=150)
    date_of_birth = models.DateField(null=True, blank=True)
    GENDER = [("M", "Male"), ("F", "Female"), ("O", "Other")]
    gender = models.CharField(max_length=1, choices=GENDER, blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)

    guardians = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="Guardian",
        related_name="wards",
        blank=True,
    )
    status = models.CharField(
        max_length=10, choices=StudentStatus.choices, default=StudentStatus.ACTIVE
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        today = date.today()
        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )

    @property
    def is_active(self):
        return self.status == StudentStatus.ACTIVE

    def primary_guardian(self):
        link = self.guardian_links.filter(is_primary=True).select_related("parent").first()
        return link.parent if link else None

    def active_enrollments(self):
        return self.enrollments.filter(status=EnrollmentStatus.ACTIVE).select_related(
            "sport", "batch", "branch"
        )


class Guardian(models.Model):
    RELATIONSHIP = [
        ("father", "Father"),
        ("mother", "Mother"),
        ("guardian", "Guardian"),
        ("other", "Other"),
    ]
    parent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="guardian_links"
    )
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="guardian_links"
    )
    relationship = models.CharField(max_length=10, choices=RELATIONSHIP, default="guardian")
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ("parent", "student")

    def __str__(self):
        return f"{self.parent.get_short_name()} ({self.relationship}) of {self.student.full_name}"


class EnrollmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    PAUSED = "PAUSED", "Paused"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"


class Enrollment(models.Model):
    """A student in one batch (which fixes the sport + branch)."""

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    batch = models.ForeignKey("academy.Batch", on_delete=models.PROTECT, related_name="enrollments")
    # Denormalised for fast, safe scoping/reporting (kept in sync with batch).
    sport = models.ForeignKey("academy.Sport", on_delete=models.PROTECT, related_name="enrollments")
    branch = models.ForeignKey("academy.Branch", on_delete=models.PROTECT, related_name="enrollments")

    start_date = models.DateField(default=date.today)
    status = models.CharField(
        max_length=10, choices=EnrollmentStatus.choices, default=EnrollmentStatus.ACTIVE
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("student", "batch")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student.full_name} → {self.batch}"

    def save(self, *args, **kwargs):
        # Keep denormalised sport/branch consistent with the chosen batch.
        if self.batch_id:
            self.sport_id = self.batch.sport_id
            self.branch_id = self.batch.branch_id
        super().save(*args, **kwargs)
