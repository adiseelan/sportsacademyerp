from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import EmailOTP, LoginEvent, OtpRateState, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("full_name",)
    list_display = ("email", "full_name", "role", "academy", "is_active", "is_staff")
    list_filter = ("role", "is_active", "is_staff", "academy")
    search_fields = ("email", "full_name", "phone")
    readonly_fields = ("last_login", "date_joined", "last_login_ip")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "role", "academy")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Audit", {"fields": ("last_login", "date_joined", "last_login_ip")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "academy", "password1", "password2"),
            },
        ),
    )


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("email", "created_at", "expires_at", "consumed_at", "attempts")
    list_filter = ("purpose",)
    search_fields = ("email",)
    readonly_fields = [f.name for f in EmailOTP._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(OtpRateState)
class OtpRateStateAdmin(admin.ModelAdmin):
    list_display = ("email", "sends_in_window", "locked_until", "last_sent_at", "total_sends")
    search_fields = ("email",)
    actions = ["reset_throttle"]

    @admin.action(description="Reset OTP throttle (clear cooldown)")
    def reset_throttle(self, request, queryset):
        queryset.update(sends_in_window=0, locked_until=None, window_start=None)


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("email", "outcome", "ip_address", "created_at")
    list_filter = ("outcome",)
    search_fields = ("email", "ip_address")
    readonly_fields = [f.name for f in LoginEvent._meta.fields]

    def has_add_permission(self, request):
        return False
