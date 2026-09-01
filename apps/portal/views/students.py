"""Student roster: list / detail / create / enroll / assign fee."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.academy.scoping import accessible_students, can_manage_students
from apps.accounts.models import Role, User
from apps.accounts.permissions import staff_scope
from apps.audit.services import record
from apps.fees import services as fee_services
from apps.notifications.engine import notify_roster_change
from apps.portal.forms import AssignFeeForm, EnrollmentForm, StudentCreateForm
from apps.students.models import Enrollment, Guardian, Student


@staff_scope
def student_list(request):
    q = request.GET.get("q", "").strip()
    students = accessible_students(request.user).order_by("full_name")
    if q:
        students = students.filter(full_name__icontains=q)
    students = students.prefetch_related("enrollments__sport", "enrollments__branch")
    return render(request, "portal/students/list.html", {"students": students[:200], "q": q})


def _get_student_in_scope(request, pk):
    student = get_object_or_404(accessible_students(request.user), pk=pk)
    return student


@staff_scope
def student_detail(request, pk):
    student = _get_student_in_scope(request, pk)
    ctx = {
        "student": student,
        "enrollments": student.enrollments.select_related("sport", "batch", "branch"),
        "fees": student.fees.select_related("plan", "sport"),
        "invoices": student.invoices.select_related("sport").order_by("-issued_date")[:20],
        "attendance": student.attendance.select_related("session", "session__batch")[:20],
        "guardians": student.guardian_links.select_related("parent"),
        "enroll_form": EnrollmentForm(user=request.user),
        "fee_form": AssignFeeForm(user=request.user),
        "can_manage": can_manage_students(request.user),
    }
    return render(request, "portal/students/detail.html", ctx)


@staff_scope
def student_create(request):
    form = StudentCreateForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        with transaction.atomic():
            student = Student.objects.create(
                academy_id=request.user.academy_id,
                full_name=cd["full_name"],
                date_of_birth=cd["date_of_birth"],
                gender=cd["gender"] or "",
                contact_phone=cd["contact_phone"],
                address=cd["address"],
                created_by=request.user,
            )
            parent, created = User.objects.get_or_create(
                email=cd["parent_email"],
                defaults={
                    "full_name": cd["parent_full_name"],
                    "phone": cd["parent_phone"],
                    "role": Role.PARENT,
                    "academy_id": request.user.academy_id,
                },
            )
            if created:
                parent.set_unusable_password()
                parent.save()
            Guardian.objects.get_or_create(
                parent=parent,
                student=student,
                defaults={"relationship": cd["relationship"], "is_primary": True},
            )
            record(actor=request.user, action="student.add", obj=student,
                   summary=f"{student.full_name} (guardian {parent.email})")

            batch = cd.get("batch")
            if batch:
                Enrollment.objects.create(
                    student=student, batch=batch, sport=batch.sport,
                    branch=batch.branch, created_by=request.user,
                )
                if cd.get("fee_plan"):
                    fee_services.assign_fee(
                        student, batch.sport, cd["fee_plan"], actor=request.user
                    )
        messages.success(request, f"{student.full_name} added.")
        return redirect("portal:student_detail", pk=student.pk)
    return render(request, "portal/students/create.html", {"form": form})


@staff_scope
def student_enroll(request, pk):
    student = _get_student_in_scope(request, pk)
    if request.method != "POST":
        return redirect("portal:student_detail", pk=pk)
    form = EnrollmentForm(request.POST, user=request.user)
    if form.is_valid():
        batch = form.cleaned_data["batch"]
        _, created = Enrollment.objects.get_or_create(
            student=student, batch=batch,
            defaults={"sport": batch.sport, "branch": batch.branch, "created_by": request.user},
        )
        if created:
            record(actor=request.user, action="enrollment.add", obj=student,
                   summary=f"{student.full_name} → {batch}")
            notify_roster_change(batch, f"{student.full_name} added to {batch}.")
            messages.success(request, f"Enrolled in {batch}.")
        else:
            messages.info(request, "Already enrolled in that batch.")
    else:
        messages.error(request, "Could not enroll — check the batch selection.")
    return redirect("portal:student_detail", pk=pk)


@staff_scope
def student_assign_fee(request, pk):
    student = _get_student_in_scope(request, pk)
    if request.method != "POST":
        return redirect("portal:student_detail", pk=pk)
    form = AssignFeeForm(request.POST, user=request.user)
    if form.is_valid():
        cd = form.cleaned_data
        fee_services.assign_fee(
            student, cd["sport"], cd["plan"], start_date=cd["start_date"], actor=request.user
        )
        messages.success(request, f"Fee plan '{cd['plan'].name}' assigned for {cd['sport'].name}.")
    else:
        messages.error(request, "Could not assign fee — check the form.")
    return redirect("portal:student_detail", pk=pk)
