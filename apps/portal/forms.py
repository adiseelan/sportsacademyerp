import os

from django import forms
from django.utils import timezone

from apps.academy.models import WEEKDAYS, Batch, Branch, Sport
from apps.academy.scoping import accessible_batches, accessible_branches
from apps.accounts.models import Role, User
from apps.fees.models import FeePlan, PaymentMethod
from apps.students.models import Enrollment, Student


class StudentCreateForm(forms.Form):
    # Student
    full_name = forms.CharField(max_length=150)
    date_of_birth = forms.DateField(
        required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    gender = forms.ChoiceField(required=False, choices=[("", "—")] + list(Student.GENDER))
    contact_phone = forms.CharField(max_length=20, required=False)
    address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    # Guardian (a parent account is created/linked by email)
    parent_full_name = forms.CharField(max_length=150, label="Parent/guardian name")
    parent_email = forms.EmailField(label="Parent email (used for their login)")
    parent_phone = forms.CharField(max_length=20, required=False, label="Parent phone")
    relationship = forms.ChoiceField(
        choices=[("father", "Father"), ("mother", "Mother"), ("guardian", "Guardian")],
        initial="guardian",
    )

    # First enrolment (optional but recommended)
    batch = forms.ModelChoiceField(queryset=Enrollment.objects.none(), required=False)
    fee_plan = forms.ModelChoiceField(queryset=FeePlan.objects.none(), required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None:
            self.fields["batch"].queryset = accessible_batches(user).filter(is_active=True)
            self.fields["fee_plan"].queryset = FeePlan.objects.filter(
                academy_id=user.academy_id, is_active=True
            )

    def clean_parent_email(self):
        return self.cleaned_data["parent_email"].strip().lower()


class EnrollmentForm(forms.Form):
    batch = forms.ModelChoiceField(queryset=Enrollment.objects.none())

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["batch"].queryset = accessible_batches(user).filter(is_active=True)


class AssignFeeForm(forms.Form):
    sport = forms.ModelChoiceField(queryset=Sport.objects.none())
    plan = forms.ModelChoiceField(queryset=FeePlan.objects.none())
    start_date = forms.DateField(
        initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["sport"].queryset = Sport.objects.filter(
                academy_id=user.academy_id, is_active=True
            )
            self.fields["plan"].queryset = FeePlan.objects.filter(
                academy_id=user.academy_id, is_active=True
            )


class RecordPaymentForm(forms.Form):
    amount = forms.DecimalField(min_value=0.01, max_digits=10, decimal_places=2)
    method = forms.ChoiceField(
        choices=[
            (PaymentMethod.CASH, "Cash"),
            (PaymentMethod.UPI, "UPI (offline)"),
            (PaymentMethod.BANK, "Bank transfer"),
        ]
    )
    note = forms.CharField(max_length=200, required=False)


class ManualCheckinForm(forms.Form):
    manual_reason = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={"placeholder": "e.g. GPS unavailable at venue"}),
    )


# ======================================================================
#  Org setup forms (Admin) — manage branches / sports / batches / staff
#  entirely inside the white portal (no need for the Django /admin/).
# ======================================================================
class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = [
            "name", "code", "address", "latitude", "longitude",
            "geofence_radius_m", "phone", "photo", "sports", "is_active",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "sports": forms.CheckboxSelectMultiple,
            "latitude": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 11.9340"}),
            "longitude": forms.NumberInput(attrs={"step": "any", "placeholder": "e.g. 79.8300"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["sports"].queryset = Sport.objects.filter(
                academy_id=user.academy_id, is_active=True
            )
        self.fields["sports"].required = False

    PHOTO_MAX_BYTES = 5 * 1024 * 1024
    PHOTO_TYPES = (".jpg", ".jpeg", ".png", ".webp")

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and hasattr(photo, "size") and getattr(photo, "content_type", None) is not None:  # a new upload
            if os.path.splitext(photo.name)[1].lower() not in self.PHOTO_TYPES:
                raise forms.ValidationError("Use a JPG, PNG or WebP image.")
            if photo.size > self.PHOTO_MAX_BYTES:
                raise forms.ValidationError("Photo is too large — 5 MB maximum.")
        return photo


class SportForm(forms.ModelForm):
    class Meta:
        model = Sport
        fields = ["name", "is_active"]


class BatchForm(forms.ModelForm):
    days = forms.MultipleChoiceField(
        choices=WEEKDAYS, required=False, widget=forms.CheckboxSelectMultiple,
        label="Days of week",
    )

    class Meta:
        model = Batch
        fields = ["branch", "sport", "name", "start_time", "end_time", "capacity", "is_active"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["branch"].queryset = accessible_branches(user)
            self.fields["sport"].queryset = Sport.objects.filter(
                academy_id=user.academy_id, is_active=True
            )
        if self.instance and self.instance.pk:
            self.fields["days"].initial = self.instance.day_list()

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.days_of_week = ",".join(self.cleaned_data.get("days", []))
        if commit:
            obj.save()
        return obj


class StaffForm(forms.Form):
    """Create a Manager or Coach account (role passed by the view)."""

    full_name = forms.CharField(max_length=150)
    email = forms.EmailField(help_text="Used for their passwordless OTP login.")
    phone = forms.CharField(max_length=20, required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("A user with this email already exists.")
        return email


class AssignBranchesForm(forms.Form):
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["branches"].queryset = accessible_branches(user)


class AssignBatchesForm(forms.Form):
    batches = forms.ModelMultipleChoiceField(
        queryset=Batch.objects.none(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["batches"].queryset = accessible_batches(user).filter(is_active=True)
