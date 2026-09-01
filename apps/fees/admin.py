from django.contrib import admin

from .models import FeePlan, Invoice, Payment, StudentFee


@admin.register(FeePlan)
class FeePlanAdmin(admin.ModelAdmin):
    list_display = ("name", "academy", "plan_type", "period", "amount", "sport", "is_active")
    list_filter = ("academy", "plan_type", "period", "is_active")
    search_fields = ("name",)


@admin.register(StudentFee)
class StudentFeeAdmin(admin.ModelAdmin):
    list_display = ("student", "sport", "plan", "status", "start_date", "end_date", "next_due_date")
    list_filter = ("status", "sport")
    search_fields = ("student__full_name",)
    autocomplete_fields = ("student", "sport", "plan")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ("receipt_number", "recorded_at")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "student", "sport", "period_label", "amount", "discount", "amount_paid", "status", "due_date")
    list_filter = ("status", "academy", "sport")
    search_fields = ("number", "student__full_name")
    date_hierarchy = "due_date"
    inlines = [PaymentInline]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "student", "amount", "kind", "method", "status", "recorded_at")
    list_filter = ("kind", "method", "status")
    search_fields = ("receipt_number", "student__full_name", "gateway_ref")
