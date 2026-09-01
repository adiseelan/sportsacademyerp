from django.contrib import admin

from .models import Attendance, Session


class AttendanceInline(admin.TabularInline):
    model = Attendance
    extra = 0
    autocomplete_fields = ("student",)


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ("batch", "date", "status", "coach", "check_in_method", "manual_flagged")
    list_filter = ("status", "check_in_method", "manual_flagged", "date")
    search_fields = ("batch__name", "coach__full_name")
    date_hierarchy = "date"
    inlines = [AttendanceInline]


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "session", "status", "marked_at")
    list_filter = ("status",)
    search_fields = ("student__full_name",)
