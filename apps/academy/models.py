"""
Organizational core: Academy (tenant) -> Branch -> Sport/Batch, plus the
Manager<->Branch and Coach<->Batch assignment tables that drive scoping.
"""
import os
from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


class Academy(models.Model):
    """Top-level tenant. Single academy today; schema ready for many."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=160, unique=True, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    currency = models.CharField(max_length=3, default="INR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Academies"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:160]
        super().save(*args, **kwargs)


class Sport(models.Model):
    academy = models.ForeignKey(Academy, on_delete=models.CASCADE, related_name="sports")
    name = models.CharField(max_length=80)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("academy", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


def branch_photo_upload(instance, filename):
    """Random file name so uploads never collide or leak the original name."""
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    return f"branches/{uuid4().hex}{ext}"


class Branch(models.Model):
    academy = models.ForeignKey(Academy, on_delete=models.CASCADE, related_name="branches")
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(
        default=200, help_text="Coach must be within this radius (metres) to check in."
    )
    phone = models.CharField(max_length=20, blank=True)
    photo = models.ImageField(
        upload_to=branch_photo_upload, blank=True,
        help_text="Cover photo shown on the Branches page (JPG / PNG / WebP, up to 5 MB).",
    )
    sports = models.ManyToManyField(Sport, related_name="branches", blank=True)
    managers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="ManagerAssignment",
        through_fields=("branch", "manager"),
        related_name="managed_branches",
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Branches"
        unique_together = ("academy", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def has_geo(self):
        return self.latitude is not None and self.longitude is not None


WEEKDAYS = [
    ("Mon", "Monday"),
    ("Tue", "Tuesday"),
    ("Wed", "Wednesday"),
    ("Thu", "Thursday"),
    ("Fri", "Friday"),
    ("Sat", "Saturday"),
    ("Sun", "Sunday"),
]
WEEKDAY_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


class Batch(models.Model):
    """A scheduled group under one sport at one branch."""

    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="batches")
    sport = models.ForeignKey(Sport, on_delete=models.PROTECT, related_name="batches")
    name = models.CharField(max_length=120, help_text='e.g. "U-14 Evening"')
    days_of_week = models.CharField(
        max_length=40, blank=True, help_text='Comma list, e.g. "Mon,Wed,Fri"'
    )
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    capacity = models.PositiveSmallIntegerField(default=30)
    coaches = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through="CoachAssignment",
        through_fields=("batch", "coach"),
        related_name="coached_batches",
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name_plural = "Batches"
        ordering = ["branch", "sport", "name"]

    def __str__(self):
        return f"{self.sport.name} {self.name} · {self.branch.name}"

    @property
    def academy_id(self):
        return self.branch.academy_id

    def day_list(self):
        return [d.strip() for d in self.days_of_week.split(",") if d.strip()]

    def runs_on(self, date):
        idx = date.weekday()
        return any(WEEKDAY_INDEX.get(d) == idx for d in self.day_list())

    def schedule_label(self):
        days = " ".join(self.day_list()) or "—"
        if self.start_time and self.end_time:
            return f"{days} · {self.start_time:%H:%M}–{self.end_time:%H:%M}"
        return days


class ManagerAssignment(models.Model):
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="manager_assignments"
    )
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="manager_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("manager", "branch")

    def __str__(self):
        return f"{self.manager.get_short_name()} → {self.branch.name}"


class CoachAssignment(models.Model):
    coach = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="coach_assignments"
    )
    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="coach_assignments")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    assigned_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("coach", "batch")

    def __str__(self):
        return f"{self.coach.get_short_name()} → {self.batch}"
