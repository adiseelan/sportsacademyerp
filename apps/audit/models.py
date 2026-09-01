"""Immutable-ish audit trail for accountability (who did what, when)."""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events"
    )
    actor_label = models.CharField(max_length=160, blank=True)  # snapshot, survives deletes
    action = models.CharField(max_length=50, db_index=True)
    summary = models.CharField(max_length=300, blank=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action", "created_at"])]

    def __str__(self):
        return f"{self.actor_label or 'system'} · {self.action} · {self.created_at:%Y-%m-%d %H:%M}"
