"""Email-OTP authentication views (passwordless, rate-limited)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from . import otp as otp_service
from .forms import EmailLoginForm, OtpForm
from .utils import get_client_ip, get_user_agent

PENDING_EMAIL_KEY = "otp_pending_email"
NEXT_URL_KEY = "otp_next_url"


def _safe_next(request):
    nxt = request.GET.get("next") or request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return None


@never_cache
@require_http_methods(["GET", "POST"])
def login_request(request):
    """Step 1 — collect the email and issue an OTP."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    form = EmailLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        ip, ua = get_client_ip(request), get_user_agent(request)
        try:
            result = otp_service.request_login_otp(email, ip=ip, user_agent=ua)
        except otp_service.CooldownActive as exc:
            messages.error(request, str(exc))
            return render(request, "accounts/login.html", {"form": form})

        request.session[PENDING_EMAIL_KEY] = email
        nxt = _safe_next(request)
        if nxt:
            request.session[NEXT_URL_KEY] = nxt

        # Generic message — never confirms whether the email is registered.
        messages.info(
            request,
            "If that email is registered, a verification code is on its way. "
            f"It expires in {max(1, settings.OTP_TTL_SECONDS // 60)} minute(s).",
        )
        if result.dev_code:
            messages.warning(
                request, f"Your code is {result.dev_code} (shown on screen for testing)."
            )
        return redirect("accounts:verify")

    return render(request, "accounts/login.html", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
def login_verify(request):
    """Step 2 — verify the OTP and start the session."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    email = request.session.get(PENDING_EMAIL_KEY)
    if not email:
        messages.error(request, "Start by entering your email.")
        return redirect("accounts:login")

    form = OtpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        ip, ua = get_client_ip(request), get_user_agent(request)
        try:
            user = otp_service.verify_login_otp(
                email, form.cleaned_data["code"], ip=ip, user_agent=ua
            )
        except otp_service.OtpError as exc:
            messages.error(request, str(exc))
            return render(request, "accounts/verify.html", {"form": form, "email": email})

        # Success — rotate session, clean up, route by role.
        login(request, user)  # cycles the session key (fixation-safe)
        request.session.pop(PENDING_EMAIL_KEY, None)
        nxt = request.session.pop(NEXT_URL_KEY, None)
        messages.success(request, f"Welcome back, {user.get_short_name()}.")
        return redirect(nxt or settings.LOGIN_REDIRECT_URL)

    return render(request, "accounts/verify.html", {"form": form, "email": email})


@never_cache
@require_http_methods(["POST"])
def login_resend(request):
    """Re-issue an OTP for the pending email (same rate limits apply)."""
    email = request.session.get(PENDING_EMAIL_KEY)
    if not email:
        return redirect("accounts:login")
    ip, ua = get_client_ip(request), get_user_agent(request)
    try:
        result = otp_service.request_login_otp(email, ip=ip, user_agent=ua)
    except otp_service.CooldownActive as exc:
        messages.error(request, str(exc))
        return redirect("accounts:verify")

    if result.sends_remaining == 0:
        messages.warning(
            request,
            "That was your last available code for now. If it doesn't arrive, "
            "you'll need to wait before requesting more.",
        )
    else:
        messages.info(
            request,
            f"A new code was sent. {result.sends_remaining} request(s) left "
            "before a cooldown.",
        )
    if result.dev_code:
        messages.warning(request, f"Your code is {result.dev_code} (shown on screen for testing).")
    return redirect("accounts:verify")


@require_http_methods(["POST", "GET"])
def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("accounts:login")
