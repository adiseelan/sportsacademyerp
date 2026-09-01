"""
Project-level security middleware.

Adds a Content-Security-Policy and a set of hardening response headers that
Django's SecurityMiddleware does not cover. The app ships entirely
self-contained static assets (no CDNs, no inline scripts), so the policy can
stay strict: script-src 'self'. The Django admin needs 'unsafe-inline' for
its bundled widgets, so a slightly relaxed policy is applied only there.
"""
from django.conf import settings


def _policy(directives):
    parts = []
    for key, values in directives:
        if values:
            parts.append(f"{key} {' '.join(values)}")
    return "; ".join(parts)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.app_csp = _policy(
            [
                ("default-src", settings.CSP_DEFAULT_SRC),
                ("script-src", settings.CSP_SCRIPT_SRC),
                ("style-src", settings.CSP_STYLE_SRC),
                ("img-src", settings.CSP_IMG_SRC),
                ("connect-src", settings.CSP_CONNECT_SRC),
                ("font-src", settings.CSP_FONT_SRC),
                ("frame-ancestors", settings.CSP_FRAME_ANCESTORS),
                ("base-uri", settings.CSP_BASE_URI),
                ("form-action", settings.CSP_FORM_ACTION),
                ("object-src", ("'none'",)),
            ]
        )
        # Admin bundles inline JS/CSS; relax only for /admin/.
        self.admin_csp = _policy(
            [
                ("default-src", ("'self'",)),
                ("script-src", ("'self'", "'unsafe-inline'")),
                ("style-src", ("'self'", "'unsafe-inline'")),
                ("img-src", ("'self'", "data:")),
                ("frame-ancestors", ("'none'",)),
                ("base-uri", ("'self'",)),
                ("object-src", ("'none'",)),
            ]
        )

    def __call__(self, request):
        response = self.get_response(request)

        if request.path.startswith("/admin/"):
            response.setdefault("Content-Security-Policy", self.admin_csp)
        else:
            response.setdefault("Content-Security-Policy", self.app_csp)

        # Extra hardening headers.
        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("Referrer-Policy", settings.SECURE_REFERRER_POLICY)
        response.setdefault(
            "Permissions-Policy",
            "geolocation=(self), microphone=(), camera=(), payment=(self)",
        )
        response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.setdefault("X-Frame-Options", "DENY")
        return response
