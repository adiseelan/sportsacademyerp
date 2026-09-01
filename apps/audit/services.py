"""record() — the single entry point for writing audit events."""
from django.contrib.contenttypes.models import ContentType

from .middleware import get_current_request
from .models import AuditLog


def _client_ip(request):
    if not request:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def record(actor=None, action="", obj=None, summary="", ip=None):
    """
    Write one audit row. `actor` and `ip` fall back to the current request
    when omitted, so callers usually just pass action/obj/summary.
    """
    request = get_current_request()
    if actor is None and request is not None:
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            actor = user
    if ip is None:
        ip = _client_ip(request)

    ct = oid = None
    if obj is not None and getattr(obj, "pk", None) is not None:
        ct = ContentType.objects.get_for_model(obj.__class__)
        oid = str(obj.pk)

    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_label=str(actor) if actor else "system",
        action=action,
        summary=summary[:300],
        content_type=ct,
        object_id=oid or "",
        ip_address=ip,
    )
