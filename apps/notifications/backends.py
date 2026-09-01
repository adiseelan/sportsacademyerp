"""
Notification channel backends. In-app + email work out of the box. SMS,
WhatsApp and push are console stubs that log what *would* be sent — swap them
for Twilio/FCM/etc. by pointing NOTIFICATION_CHANNELS at real classes.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import DeliveryLog, Notification

log = logging.getLogger("erp.security")


class BaseChannel:
    channel = "base"

    def send(self, recipient, title, body, event="", url=""):  # pragma: no cover
        raise NotImplementedError

    def _log(self, recipient, target, event, ok, ref="", detail=""):
        DeliveryLog.objects.create(
            recipient=recipient,
            channel=self.channel,
            target=target,
            event=event,
            ok=ok,
            provider_ref=ref,
            detail=detail[:300],
        )


class InAppBackend(BaseChannel):
    channel = "inapp"

    def send(self, recipient, title, body, event="", url=""):
        Notification.objects.create(
            recipient=recipient, event=event or "general", title=title, body=body, url=url
        )


class EmailBackend(BaseChannel):
    channel = "email"

    def send(self, recipient, title, body, event="", url=""):
        if not recipient.email:
            return
        try:
            send_mail(
                subject=title,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )
            self._log(recipient, recipient.email, event, True)
        except Exception as exc:  # never let a channel break the request
            log.warning("Email notify failed: %s", exc)
            self._log(recipient, recipient.email, event, False, detail=str(exc))


class ConsoleSMSBackend(BaseChannel):
    channel = "sms"

    def send(self, recipient, title, body, event="", url=""):
        target = recipient.phone or "(no phone)"
        print(f"[SMS→{target}] {title} — {body}")
        self._log(recipient, target, event, bool(recipient.phone), ref="console")


class ConsoleWhatsAppBackend(BaseChannel):
    channel = "whatsapp"

    def send(self, recipient, title, body, event="", url=""):
        target = recipient.phone or "(no phone)"
        print(f"[WhatsApp→{target}] {title} — {body}")
        self._log(recipient, target, event, bool(recipient.phone), ref="console")


class ConsolePushBackend(BaseChannel):
    channel = "push"

    def send(self, recipient, title, body, event="", url=""):
        print(f"[Push→{recipient.get_short_name()}] {title} — {body}")
        self._log(recipient, recipient.get_short_name(), event, True, ref="console")


def get_backend(channel):
    from django.utils.module_loading import import_string

    path = settings.NOTIFICATION_CHANNELS.get(channel)
    if not path:
        return None
    return import_string(path)()
