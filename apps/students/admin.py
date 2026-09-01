from django.contrib import admin

from .models import Enrollment, Guardian, Student


class GuardianInline(admin.TabularInline):
    model = Guardian
    extra = 1
    autocomplete_fields = ("parent",)


class EnrollmentInline(admin.TabularInline):
    model = Enrollment
    extra = 0
    autocomplete_fields = ("batch", "sport", "branch")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("full_name", "academy", "age", "status", "created_at")
    list_filter = ("academy", "status", "gender")
    search_fields = ("full_name", "contact_phone", "contact_email")
    inlines = [GuardianInline, EnrollmentInline]


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ("student", "sport", "batch", "branch", "status", "start_date")
    list_filter = ("status", "branch", "sport")
    search_fields = ("student__full_name",)
    autocomplete_fields = ("student", "batch", "sport", "branch")


@admin.register(Guardian)
class GuardianAdmin(admin.ModelAdmin):
    list_display = ("parent", "student", "relationship", "is_primary")
    search_fields = ("parent__full_name", "student__full_name")
