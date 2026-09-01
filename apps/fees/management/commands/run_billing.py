"""
Recurring billing job — run daily (cron / scheduled task).

  * Generates the next invoice for any active fee whose next due date arrived.
  * Flags unpaid past-due invoices as overdue and fires reminder notifications.

    python manage.py run_billing
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.fees import services as fee_services
from apps.fees.models import StudentFee, StudentFeeStatus


class Command(BaseCommand):
    help = "Generate due invoices and flag overdue fees (run daily)."

    def handle(self, *args, **opts):
        today = timezone.localdate()
        due_fees = StudentFee.objects.filter(
            status=StudentFeeStatus.ACTIVE, next_due_date__lte=today
        ).select_related("student", "sport", "plan")

        generated = 0
        for fee in due_fees:
            # Package fees stop billing after their validity window ends.
            if fee.end_date and fee.next_due_date and fee.next_due_date > fee.end_date:
                fee.status = StudentFeeStatus.EXPIRED
                fee.save(update_fields=["status"])
                continue
            fee_services.generate_invoice(fee, period_start=fee.next_due_date)
            generated += 1

        flagged = fee_services.flag_overdue()
        self.stdout.write(self.style.SUCCESS(
            f"Billing run complete — {generated} invoice(s) generated, {flagged} flagged overdue."
        ))
