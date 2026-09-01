"""
Central query-scoping. EVERY user-facing queryset must pass through here so a
user can only ever see rows their role + assignments permit. This is the core
defence against IDOR / horizontal privilege escalation.

Rules:
  Admin    -> everything inside their academy
  Manager  -> only their assigned branch(es) and everything under them
  Coach    -> only their assigned batch(es) and the students/sessions in them
  Parent   -> only their own linked student(s)
  Platform superuser with no academy -> everything (operator god-mode)
"""
from .models import Batch, Branch


def _is_platform_root(user):
    return user.is_superuser and getattr(user, "academy_id", None) is None


def accessible_branches(user):
    if not user.is_authenticated:
        return Branch.objects.none()
    qs = Branch.objects.select_related("academy")
    if _is_platform_root(user):
        return qs
    qs = qs.filter(academy_id=user.academy_id)
    if user.is_admin:
        return qs
    if user.is_manager:
        return qs.filter(
            manager_assignments__manager=user, manager_assignments__is_active=True
        ).distinct()
    if user.is_coach:
        return qs.filter(
            batches__coach_assignments__coach=user,
            batches__coach_assignments__is_active=True,
        ).distinct()
    if user.is_parent:
        return qs.filter(batches__enrollments__student__guardians=user).distinct()
    return qs.none()


def accessible_batches(user):
    if not user.is_authenticated:
        return Batch.objects.none()
    qs = Batch.objects.select_related("branch", "sport", "branch__academy")
    if _is_platform_root(user):
        return qs
    qs = qs.filter(branch__academy_id=user.academy_id)
    if user.is_admin:
        return qs
    if user.is_manager:
        return qs.filter(
            branch__manager_assignments__manager=user,
            branch__manager_assignments__is_active=True,
        ).distinct()
    if user.is_coach:
        return qs.filter(
            coach_assignments__coach=user, coach_assignments__is_active=True
        ).distinct()
    if user.is_parent:
        return qs.filter(enrollments__student__guardians=user).distinct()
    return qs.none()


def accessible_students(user):
    from apps.students.models import Student

    if not user.is_authenticated:
        return Student.objects.none()
    qs = Student.objects.select_related("academy")
    if _is_platform_root(user):
        return qs
    qs = qs.filter(academy_id=user.academy_id)
    if user.is_admin:
        return qs
    if user.is_parent:
        return qs.filter(guardians=user).distinct()
    if user.is_manager:
        branch_ids = list(accessible_branches(user).values_list("id", flat=True))
        return qs.filter(enrollments__branch_id__in=branch_ids).distinct()
    if user.is_coach:
        batch_ids = list(accessible_batches(user).values_list("id", flat=True))
        return qs.filter(enrollments__batch_id__in=batch_ids).distinct()
    return qs.none()


def can_manage_students(user):
    return user.is_admin or user.is_manager


def branch_ids_for(user):
    return list(accessible_branches(user).values_list("id", flat=True))


def batch_ids_for(user):
    return list(accessible_batches(user).values_list("id", flat=True))
