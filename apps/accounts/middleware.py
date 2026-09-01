"""Idle-timeout middleware: sign users out after a period of inactivity."""
from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone

LAST_SEEN_KEY = "_last_seen_ts"


class SessionIdleTimeoutMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 1800)

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = int(timezone.now().timestamp())
            last = request.session.get(LAST_SEEN_KEY)
            if last is not None and (now - last) > self.timeout:
                logout(request)
                request.session.flush()
            else:
                request.session[LAST_SEEN_KEY] = now
        return self.get_response(request)
