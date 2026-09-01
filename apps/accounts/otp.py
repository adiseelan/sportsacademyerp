"""
OTP service layer — rate-limited issue + constant-time verify.

Public API:
    request_login_otp(email, ip, user_agent) -> OtpIssueResult
    verify_login_otp(email, code, ip, user_agent) -> User

Both raise typed exceptions the views translate into user-facing messages.
"""
from __future__ import annotations

import logging
import math
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailOTP, LoginEvent, OtpRateState, User, hash_code

log = logging.getLogger("erp.security")


# ----------------------------------------------------------------- errors
class OtpError(Exception):
    """Base class for all OTP failures (message is user-safe)."""


class CooldownActive(OtpError):
    def __init__(self, seconds_left: int):
        self.seconds_left = max(1, int(seconds_left))
        mins = math.ceil(self.seconds_left / 60)
        super().__init__(
            f"You've reached the limit of {settings.OTP_MAX_SENDS} code requests. "
            f"Please wait about {mins} minute(s) before trying again."
        )


class InvalidCode(OtpError):
    def __init__(self, attempts_left: int):
        self.attempts_left = attempts_left
        if attempts_left > 0:
            super().__init__(
                f"That code is incorrect. {attempts_left} attempt(s) left."
            )
        else:
            super().__init__(
                "That code is incorrect and has now been blocked. "
                "Request a fresh code."
            )


class CodeExpired(OtpError):
    def __init__(self):
        super().__init__("Your code has expired or was already used. Request a new one.")


@dataclass
class OtpIssueResult:
    email: str
    sends_used: int
    sends_remaining: int
    ttl_seconds: int
    dev_code: str | None = None  # populated only when DEBUG, for convenience


# ----------------------------------------------------------------- helpers
def _generate_code() -> str:
    n = settings.OTP_LENGTH
    return "".join(secrets.choice("0123456789") for _ in range(n))


def _resolve_active_user(email: str):
    return User.objects.filter(email__iexact=email, is_active=True).first()


def _log(email, outcome, ip, ua):
    LoginEvent.objects.create(
        email=email, outcome=outcome, ip_address=ip, user_agent=(ua or "")[:300]
    )


# ----------------------------------------------------------------- issue
def request_login_otp(email: str, ip=None, user_agent="") -> OtpIssueResult:
    """
    State mutations happen inside a short atomic block that ALWAYS commits;
    the CooldownActive exception is raised only *after* the block so the
    throttle counters are never rolled back by the raise.
    """
    email = email.strip().lower()
    now = timezone.now()
    user = _resolve_active_user(email)
    code = _generate_code()

    cooldown_remaining = None
    sends_used = 0

    with transaction.atomic():
        state, _ = OtpRateState.objects.select_for_update().get_or_create(email=email)

        if state.locked_until and now < state.locked_until:
            cooldown_remaining = (state.locked_until - now).total_seconds()
        else:
            # Roll the window if it has elapsed (or first ever send).
            window = timedelta(seconds=settings.OTP_SEND_WINDOW_SECONDS)
            if not state.window_start or (now - state.window_start) > window:
                state.window_start = now
                state.sends_in_window = 0
                state.locked_until = None

            if state.sends_in_window >= settings.OTP_MAX_SENDS:
                # Already at the cap -> arm cooldown and reject.
                state.locked_until = now + timedelta(seconds=settings.OTP_COOLDOWN_SECONDS)
                state.save()
                cooldown_remaining = settings.OTP_COOLDOWN_SECONDS
            else:
                # Record a valid send. Real code only for a real account, but
                # the counter advances regardless so we don't leak which
                # emails exist via differing limits/timing.
                if user:
                    EmailOTP.objects.create(
                        email=email,
                        code_hash=hash_code(email, code),
                        expires_at=now + timedelta(seconds=settings.OTP_TTL_SECONDS),
                        ip_address=ip,
                        user_agent=(user_agent or "")[:300],
                    )
                state.sends_in_window += 1
                state.total_sends += 1
                state.last_sent_at = now
                if state.sends_in_window >= settings.OTP_MAX_SENDS:
                    state.locked_until = now + timedelta(seconds=settings.OTP_COOLDOWN_SECONDS)
                state.save()
                sends_used = state.sends_in_window

    if cooldown_remaining is not None:
        _log(email, "otp_cooldown", ip, user_agent)
        raise CooldownActive(cooldown_remaining)

    if user:
        _dispatch_code(user, code)
    _log(email, "otp_sent" if user else "unknown_email", ip, user_agent)

    remaining = max(0, settings.OTP_MAX_SENDS - sends_used)
    return OtpIssueResult(
        email=email,
        sends_used=sends_used,
        sends_remaining=remaining,
        ttl_seconds=settings.OTP_TTL_SECONDS,
        dev_code=code if ((settings.DEBUG or settings.OTP_SHOW_ON_SCREEN) and user) else None,
    )


def _dispatch_code(user: User, code: str):
    ctx = {
        "user": user,
        "code": code,
        "ttl_minutes": max(1, settings.OTP_TTL_SECONDS // 60),
    }
    subject = f"Your SportsAcademy ERP login code: {code}"
    text_body = render_to_string("accounts/email/otp_code.txt", ctx)
    try:
        send_mail(
            subject=subject,
            message=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:  # pragma: no cover - never leak SMTP errors to the client
        log.exception("Failed to send OTP email to %s", user.email)


# ----------------------------------------------------------------- verify
def verify_login_otp(email: str, code: str, ip=None, user_agent="") -> User:
    """
    Failed-attempt bookkeeping uses committed queryset .update() writes (not a
    transaction that a raised exception would roll back), so the attempt
    counter and the single-use burn always stick. This is what stops an
    attacker brute-forcing a code with unlimited guesses.
    """
    email = email.strip().lower()
    code = (code or "").strip()
    now = timezone.now()

    otp = (
        EmailOTP.objects.filter(email=email, consumed_at__isnull=True, expires_at__gt=now)
        .order_by("-created_at")
        .first()
    )
    if not otp:
        _log(email, "expired", ip, user_agent)
        raise CodeExpired()

    if otp.attempts >= settings.OTP_MAX_VERIFY_ATTEMPTS:
        EmailOTP.objects.filter(pk=otp.pk).update(consumed_at=now)
        _log(email, "locked_code", ip, user_agent)
        raise InvalidCode(0)

    if not otp.verify(code):
        new_attempts = otp.attempts + 1
        attempts_left = settings.OTP_MAX_VERIFY_ATTEMPTS - new_attempts
        EmailOTP.objects.filter(pk=otp.pk).update(
            attempts=new_attempts,
            consumed_at=now if attempts_left <= 0 else None,
        )
        _log(email, "bad_code", ip, user_agent)
        raise InvalidCode(max(0, attempts_left))

    user = _resolve_active_user(email)
    if not user:
        EmailOTP.objects.filter(pk=otp.pk).update(consumed_at=now)
        _log(email, "unknown_email", ip, user_agent)
        raise CodeExpired()

    # Success: burn the code, clear throttle so the user isn't stuck.
    EmailOTP.objects.filter(pk=otp.pk).update(consumed_at=now)
    OtpRateState.objects.filter(email=email).update(
        sends_in_window=0, locked_until=None, window_start=None
    )
    if ip:
        User.objects.filter(pk=user.pk).update(last_login_ip=ip)
    _log(email, "success", ip, user_agent)
    return user
