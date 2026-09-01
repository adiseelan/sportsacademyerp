from django.contrib import admin

from .models import (
    Academy,
    Batch,
    Branch,
    CoachAssignment,
    ManagerAssignment,
    Sport,
)


class ManagerAssignmentInline(admin.TabularInline):
    model = ManagerAssignment
    extra = 1
    autocomplete_fields = ("manager",)


class CoachAssignmentInline(admin.TabularInline):
    model = CoachAssignment
    extra = 1
    autocomplete_fields = ("coach",)


@admin.register(Academy)
class AcademyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "currency", "is_active", "created_at")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Sport)
class SportAdmin(admin.ModelAdmin):
    list_display = ("name", "academy", "is_active")
    list_filter = ("academy", "is_active")
    search_fields = ("name",)


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "academy", "code", "has_geo", "is_active")
    list_filter = ("academy", "is_active")
    search_fields = ("name", "code", "address")
    filter_horizontal = ("sports",)
    inlines = [ManagerAssignmentInline]


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = ("name", "sport", "branch", "schedule_label", "capacity", "is_active")
    list_filter = ("branch", "sport", "is_active")
    search_fields = ("name",)
    inlines = [CoachAssignmentInline]


@admin.register(ManagerAssignment)
class ManagerAssignmentAdmin(admin.ModelAdmin):
    list_display = ("manager", "branch", "is_active", "assigned_at")
    list_filter = ("is_active", "branch")


@admin.register(CoachAssignment)
class CoachAssignmentAdmin(admin.ModelAdmin):
    list_display = ("coach", "batch", "is_active", "assigned_at")
    list_filter = ("is_active",)
