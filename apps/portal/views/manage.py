"""
In-portal org setup (Admin only): branches, sports, batches, managers,
coaches — create + assign, all in the white portal UI so the Django /admin/
is never required for day-to-day management.
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.academy.models import (
    Batch,
    Branch,
    CoachAssignment,
    ManagerAssignment,
    Sport,
)
from apps.academy.scoping import accessible_batches, accessible_branches
from apps.accounts.models import Role, User
from apps.accounts.permissions import admin_required
from apps.audit.services import record
from apps.notifications.engine import notify_roster_change
from apps.portal.forms import (
    AssignBatchesForm,
    AssignBranchesForm,
    BatchForm,
    BranchForm,
    SportForm,
    StaffForm,
)


# ----------------------------------------------------------------- branches
@admin_required
def branch_create(request):
    form = BranchForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        branch = form.save(commit=False)
        branch.academy_id = request.user.academy_id
        branch.save()
        form.save_m2m()
        record(actor=request.user, action="branch.add", obj=branch, summary=branch.name)
        messages.success(request, f"Branch “{branch.name}” created.")
        return redirect("portal:branch_detail", pk=branch.pk)
    return render(request, "portal/manage/branch_form.html", {"form": form, "mode": "new"})


@admin_required
def branch_edit(request, pk):
    branch = get_object_or_404(accessible_branches(request.user), pk=pk)
    old_photo = branch.photo.name if branch.photo else ""
    form = BranchForm(request.POST or None, request.FILES or None, instance=branch, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        if old_photo and old_photo != (branch.photo.name if branch.photo else ""):
            branch.photo.storage.delete(old_photo)  # replaced or removed: drop the old file
        record(actor=request.user, action="branch.edit", obj=branch, summary=branch.name)
        messages.success(request, f"Branch “{branch.name}” updated.")
        return redirect("portal:branch_detail", pk=branch.pk)
    return render(
        request, "portal/manage/branch_form.html", {"form": form, "mode": "edit", "branch": branch}
    )


# ----------------------------------------------------------------- sports
@admin_required
def sport_create(request):
    form = SportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        sport = form.save(commit=False)
        sport.academy_id = request.user.academy_id
        sport.save()
        record(actor=request.user, action="sport.add", obj=sport, summary=sport.name)
        messages.success(request, f"Sport “{sport.name}” added.")
        return redirect("portal:branches")
    return render(request, "portal/manage/sport_form.html", {"form": form})


# ----------------------------------------------------------------- batches
@admin_required
def batch_list(request):
    batches = accessible_batches(request.user).select_related("branch", "sport").prefetch_related("coaches")
    return render(request, "portal/manage/batches.html", {"batches": batches})


def _branch_batches_url(branch_id):
    """Batches have no sidebar entry of their own: they live on the branch page's Batches tab."""
    if branch_id:
        return reverse("portal:branch_detail", args=[branch_id]) + "?tab=batches"
    return reverse("portal:branches")


def _back(branch):
    """(url, label) for the form's "← Back" / Cancel: that branch's Batches tab, else the grid."""
    if branch is None:
        return reverse("portal:branches"), "branches"
    return _branch_batches_url(branch.pk), branch.name


@admin_required
def batch_create(request):
    initial = {}
    pre = request.GET.get("branch", "")
    branch = accessible_branches(request.user).filter(pk=pre).first() if pre.isdigit() else None
    if branch is not None:
        initial["branch"] = branch.pk  # "+ New batch" from a branch's Batches tab
    form = BatchForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        batch = form.save()
        record(actor=request.user, action="batch.add", obj=batch, summary=str(batch))
        messages.success(request, f"Batch “{batch}” created.")
        return redirect(_branch_batches_url(batch.branch_id))
    back_url, back_label = _back(branch)
    return render(request, "portal/manage/batch_form.html", {
        "form": form, "mode": "new", "back_url": back_url, "back_label": back_label,
    })


@admin_required
def batch_edit(request, pk):
    batch = get_object_or_404(accessible_batches(request.user).select_related("branch"), pk=pk)
    back_url, back_label = _back(batch.branch)
    form = BatchForm(request.POST or None, instance=batch, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        record(actor=request.user, action="batch.edit", obj=batch, summary=str(batch))
        messages.success(request, f"Batch “{batch}” updated.")
        return redirect(_branch_batches_url(batch.branch_id))
    return render(request, "portal/manage/batch_form.html", {
        "form": form, "mode": "edit", "batch": batch, "back_url": back_url, "back_label": back_label,
    })


# ----------------------------------------------------------------- managers
def _sync_manager_branches(manager, branches, actor):
    ids = {b.id for b in branches}
    for bid in ids:
        ManagerAssignment.objects.update_or_create(
            manager=manager, branch_id=bid, defaults={"is_active": True, "assigned_by": actor}
        )
    ManagerAssignment.objects.filter(manager=manager).exclude(branch_id__in=ids).delete()


@admin_required
def manager_create(request):
    sform = StaffForm(request.POST or None)
    aform = AssignBranchesForm(request.POST or None, user=request.user)
    if request.method == "POST" and sform.is_valid() and aform.is_valid():
        manager = User.objects.create_user(
            email=sform.cleaned_data["email"],
            full_name=sform.cleaned_data["full_name"],
            phone=sform.cleaned_data["phone"],
            role=Role.MANAGER,
            academy_id=request.user.academy_id,
        )
        _sync_manager_branches(manager, aform.cleaned_data["branches"], request.user)
        record(actor=request.user, action="manager.add", obj=manager,
               summary=f"{manager.full_name} ({len(aform.cleaned_data['branches'])} branch)")
        messages.success(request, f"Manager “{manager.full_name}” added.")
        return redirect("portal:managers")
    return render(
        request, "portal/manage/staff_form.html",
        {"sform": sform, "aform": aform, "role": "Manager", "assign_label": "Assign branches"},
    )


@admin_required
def manager_assign(request, pk):
    manager = get_object_or_404(
        User, pk=pk, role=Role.MANAGER, academy_id=request.user.academy_id
    )
    initial = {"branches": list(
        accessible_branches(request.user)
        .filter(manager_assignments__manager=manager, manager_assignments__is_active=True)
        .values_list("id", flat=True)
    )}
    aform = AssignBranchesForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and aform.is_valid():
        _sync_manager_branches(manager, aform.cleaned_data["branches"], request.user)
        record(actor=request.user, action="manager.assign", obj=manager,
               summary=f"{manager.full_name}: {len(aform.cleaned_data['branches'])} branch")
        messages.success(request, f"Updated branches for {manager.full_name}.")
        return redirect("portal:managers")
    return render(
        request, "portal/manage/assign_form.html",
        {"aform": aform, "person": manager, "field": "branches", "assign_label": "Assign branches"},
    )


# ----------------------------------------------------------------- coaches
def _sync_coach_batches(coach, batches, actor):
    ids = {b.id for b in batches}
    for bid in ids:
        CoachAssignment.objects.update_or_create(
            coach=coach, batch_id=bid, defaults={"is_active": True, "assigned_by": actor}
        )
    CoachAssignment.objects.filter(coach=coach).exclude(batch_id__in=ids).delete()
    for b in batches:
        notify_roster_change(b, f"{coach.get_short_name()} is now coaching {b}.")


@admin_required
def coach_create(request):
    sform = StaffForm(request.POST or None)
    aform = AssignBatchesForm(request.POST or None, user=request.user)
    if request.method == "POST" and sform.is_valid() and aform.is_valid():
        coach = User.objects.create_user(
            email=sform.cleaned_data["email"],
            full_name=sform.cleaned_data["full_name"],
            phone=sform.cleaned_data["phone"],
            role=Role.COACH,
            academy_id=request.user.academy_id,
        )
        _sync_coach_batches(coach, aform.cleaned_data["batches"], request.user)
        record(actor=request.user, action="coach.add", obj=coach,
               summary=f"{coach.full_name} ({len(aform.cleaned_data['batches'])} batch)")
        messages.success(request, f"Coach “{coach.full_name}” added.")
        return redirect("portal:coaches")
    return render(
        request, "portal/manage/staff_form.html",
        {"sform": sform, "aform": aform, "role": "Coach", "assign_label": "Assign batches"},
    )


@admin_required
def coach_assign(request, pk):
    coach = get_object_or_404(
        User, pk=pk, role=Role.COACH, academy_id=request.user.academy_id
    )
    initial = {"batches": list(
        accessible_batches(request.user)
        .filter(coach_assignments__coach=coach, coach_assignments__is_active=True)
        .values_list("id", flat=True)
    )}
    aform = AssignBatchesForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and aform.is_valid():
        _sync_coach_batches(coach, aform.cleaned_data["batches"], request.user)
        record(actor=request.user, action="coach.assign", obj=coach,
               summary=f"{coach.full_name}: {len(aform.cleaned_data['batches'])} batch")
        messages.success(request, f"Updated batches for {coach.full_name}.")
        return redirect("portal:coaches")
    return render(
        request, "portal/manage/assign_form.html",
        {"aform": aform, "person": coach, "field": "batches", "assign_label": "Assign batches"},
    )
