"""
Role-based access control helpers.

Authorization is the real security boundary of an ERP: a manager must never
reach another branch, a parent never another family's child, a coach never a
batch that isn't theirs. These gate *entry* by role; per-object scoping lives
in apps.academy.scoping and is applied inside every queryset.
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import Role


def _has_role(user, roles):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.role in roles


def role_required(*roles):
    """Decorator for function views. Anonymous -> login; wrong role -> 403."""

    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not _has_role(request.user, roles):
                raise PermissionDenied("You don't have access to this area.")
            return view(request, *args, **kwargs)

        return _wrapped

    return decorator


# Convenience decorators
def admin_required(view):
    return role_required(Role.ADMIN)(view)


def manager_required(view):
    return role_required(Role.ADMIN, Role.MANAGER)(view)


def coach_required(view):
    return role_required(Role.ADMIN, Role.COACH)(view)


def parent_required(view):
    return role_required(Role.PARENT)(view)


def staff_scope(view):
    """Admin or Manager — the back-office operators."""
    return role_required(Role.ADMIN, Role.MANAGER)(view)


class RoleRequiredMixin:
    """Class-based-view counterpart of role_required."""

    allowed_roles: tuple = ()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not _has_role(request.user, self.allowed_roles):
            raise PermissionDenied("You don't have access to this area.")
        return super().dispatch(request, *args, **kwargs)
