from django.contrib import admin

from .models import DeliveryLog, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "event", "title", "is_read", "created_at")
    list_filter = ("event", "is_read")
    search_fields = ("recipient__full_name", "title")


@admin.register(DeliveryLog)
class DeliveryLogAdmin(admin.ModelAdmin):
    list_display = ("recipient", "channel", "target", "event", "ok", "created_at")
    list_filter = ("channel", "ok", "event")
    search_fields = ("recipient__full_name", "target")
