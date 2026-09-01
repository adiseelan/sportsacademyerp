"""Invoices, ledger, manual + online payments, receipts, reminders."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.permissions import admin_required, role_required, staff_scope
from apps.accounts.models import Role
from apps.fees import services as fee_services
from apps.fees.gateways import MockGateway, get_gateway
from apps.fees.models import Invoice, InvoiceStatus
from apps.notifications.engine import notify_manual_reminder
from apps.portal import analytics
from apps.portal.forms import RecordPaymentForm


def _invoice_in_scope(request, pk):
    return get_object_or_404(
        analytics.scoped_invoices(request.user).select_related(
            "student", "sport", "branch", "academy"
        ),
        pk=pk,
    )


@role_required(Role.ADMIN, Role.MANAGER, Role.PARENT)
def invoice_detail(request, pk):
    invoice = _invoice_in_scope(request, pk)
    ctx = {
        "invoice": invoice,
        "payments": invoice.payments.select_related("recorded_by").order_by("-recorded_at"),
        "pay_form": RecordPaymentForm(initial={"amount": invoice.balance}),
        "can_record": request.user.is_admin or request.user.is_manager,
        "can_pay_online": request.user.is_parent and invoice.balance > 0,
        "can_waive": request.user.is_admin and not invoice.is_settled,
    }
    return render(request, "portal/fees/invoice.html", ctx)


@staff_scope
@require_POST
def record_payment(request, pk):
    invoice = _invoice_in_scope(request, pk)
    form = RecordPaymentForm(request.POST)
    if form.is_valid():
        payment = fee_services.record_manual_payment(
            invoice,
            form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            actor=request.user,
            note=form.cleaned_data["note"],
        )
        messages.success(request, f"Payment recorded. Receipt {payment.receipt_number}.")
    else:
        messages.error(request, "Invalid payment details.")
    return redirect("portal:invoice_detail", pk=pk)


@admin_required
@require_POST
def waive_invoice(request, pk):
    invoice = _invoice_in_scope(request, pk)
    reason = request.POST.get("reason", "").strip() or "Discretionary waiver"
    fee_services.waive_invoice(invoice, actor=request.user, reason=reason)
    messages.success(request, f"{invoice.number} marked waived.")
    return redirect("portal:invoice_detail", pk=pk)


@staff_scope
@require_POST
def send_reminder(request, pk):
    invoice = _invoice_in_scope(request, pk)
    notify_manual_reminder(invoice, actor=request.user)
    messages.success(request, "Reminder sent to the parent.")
    return redirect("portal:invoice_detail", pk=pk)


# ---------------------------------------------------------------- online pay
@role_required(Role.PARENT)
def pay_online(request, pk):
    invoice = _invoice_in_scope(request, pk)
    if invoice.balance <= 0:
        messages.info(request, "This invoice is already settled.")
        return redirect("portal:invoice_detail", pk=pk)

    gateway, order = fee_services.create_online_order(invoice)
    simulated = None
    if isinstance(gateway, MockGateway):
        # Mimic what a real checkout widget hands back to the browser.
        simulated = gateway.simulate_client_payment(order.order_id)
    ctx = {"invoice": invoice, "order": order, "simulated": simulated, "gateway": gateway.name}
    return render(request, "portal/fees/pay_online.html", ctx)


@role_required(Role.PARENT)
@require_POST
def confirm_online(request, pk):
    invoice = _invoice_in_scope(request, pk)
    payload = {
        "order_id": request.POST.get("order_id", ""),
        "payment_id": request.POST.get("payment_id", ""),
        "signature": request.POST.get("signature", ""),
    }
    try:
        payment = fee_services.confirm_online_payment(invoice, payload, actor=request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("portal:invoice_detail", pk=pk)
    messages.success(request, f"Payment successful. Receipt {payment.receipt_number}.")
    return redirect("portal:receipt", pk=payment.pk)


# ---------------------------------------------------------------- receipt
@role_required(Role.ADMIN, Role.MANAGER, Role.PARENT)
def receipt(request, pk):
    from apps.fees.models import Payment

    payment = get_object_or_404(
        Payment.objects.select_related("invoice", "student", "academy"), pk=pk
    )
    # Scope check: the payment's invoice must be visible to this user.
    if payment.invoice_id and not analytics.scoped_invoices(request.user).filter(
        pk=payment.invoice_id
    ).exists():
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied
    return render(request, "portal/fees/receipt.html", {"p": payment, "invoice": payment.invoice})


# ---------------------------------------------------------------- fee status
@staff_scope
def fee_status(request, ):
    status = request.GET.get("status", "")
    invoices = analytics.scoped_invoices(request.user).select_related("student", "sport", "branch")
    if status:
        invoices = invoices.filter(status=status)
    else:
        invoices = invoices.filter(
            status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL, InvoiceStatus.OVERDUE]
        )
    return render(
        request,
        "portal/fees/status.html",
        {"invoices": invoices.order_by("due_date")[:300], "status": status},
    )
