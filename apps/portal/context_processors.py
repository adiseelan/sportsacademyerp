def portal_context(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return {}
    from apps.notifications.models import Notification

    unread = Notification.objects.filter(recipient=user, is_read=False).count()
    role_labels = {
        "ADMIN": "Admin",
        "MANAGER": "Manager",
        "COACH": "Coach",
        "PARENT": "Parent",
    }
    return {
        "unread_notifications": unread,
        "current_role_label": "Admin" if user.is_superuser else role_labels.get(user.role, ""),
    }
