"""
Custom user model + email-OTP auth primitives.

Design goals:
  * Email is the identity. No usernames.
  * Role is a first-class field (Admin / Manager / Coach / Parent).
  * Multi-tenant ready: every user belongs to an Academy (nullable only for
    the platform superuser).
  * OTP codes are NEVER stored in plaintext — only an HMAC-SHA256 digest.
"""
from __future__ import annotations

import hmac
import hashlib

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    MANAGER = "MANAGER", "Manager"
    COACH = "COACH", "Coach"
    PARENT = "PARENT", "Parent"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=Role.ADMIN, is_active=True)
        return self._create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.PARENT)

    # Tenant. Nullable so the platform superuser can exist above any academy.
    academy = models.ForeignKey(
        "academy.Academy",
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access
    date_joined = models.DateTimeField(default=timezone.now)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.lower().strip()
        super().save(*args, **kwargs)

    # ---- role helpers -------------------------------------------------
    @property
    def is_admin(self):
        return self.role == Role.ADMIN or self.is_superuser

    @property
    def is_manager(self):
        return self.role == Role.MANAGER

    @property
    def is_coach(self):
        return self.role == Role.COACH

    @property
    def is_parent(self):
        return self.role == Role.PARENT

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email


# ---------------------------------------------------------------- OTP core
def hash_code(email: str, code: str) -> str:
    """Deterministic keyed digest — no reversible plaintext ever stored."""
    msg = f"{email.lower()}:{code}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


class EmailOTP(models.Model):
    """A single one-time code issued to an email for login."""

    PURPOSE_LOGIN = "login"

    email = models.EmailField(db_index=True)
    code_hash = models.CharField(max_length=64)
    purpose = models.CharField(max_length=20, default=PURPOSE_LOGIN)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        indexes = [models.Index(fields=["email", "consumed_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"OTP({self.email}, {'used' if self.consumed_at else 'active'})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_consumed(self):
        return self.consumed_at is not None

    def verify(self, code: str) -> bool:
        return hmac.compare_digest(self.code_hash, hash_code(self.email, code))


class OtpRateState(models.Model):
    """
    Per-email throttle state that enforces:
      * at most OTP_MAX_SENDS codes inside a rolling OTP_SEND_WINDOW_SECONDS,
      * then a hard OTP_COOLDOWN_SECONDS wait ("5 times, then wait").
    """

    email = models.EmailField(unique=True, db_index=True)
    window_start = models.DateTimeField(null=True, blank=True)
    sends_in_window = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    total_sends = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"RateState({self.email}, sends={self.sends_in_window})"


class LoginEvent(models.Model):
    """Lightweight security log of authentication outcomes."""

    OUTCOME = [
        ("otp_sent", "OTP sent"),
        ("otp_cooldown", "OTP blocked (cooldown)"),
        ("success", "Login success"),
        ("bad_code", "Wrong code"),
        ("expired", "Code expired/absent"),
        ("locked_code", "Code burned (too many tries)"),
        ("unknown_email", "Unknown email"),
    ]

    email = models.EmailField(db_index=True)
    outcome = models.CharField(max_length=20, choices=OUTCOME)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.email} · {self.outcome} · {self.created_at:%Y-%m-%d %H:%M}"
