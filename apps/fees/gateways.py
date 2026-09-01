"""
Pluggable online-payment gateway.

Default is MockGateway so the whole pay-online flow works end to end with no
keys. Swap PAYMENT_GATEWAY_BACKEND to RazorpayGateway (and set the keys) to go
live — the service layer and templates don't change.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class Order:
    order_id: str
    amount_paise: int
    currency: str = "INR"
    key_id: str = ""
    gateway: str = "mock"
    extra: dict = field(default_factory=dict)


class BaseGateway:
    name = "base"

    def create_order(self, invoice, amount) -> Order:  # pragma: no cover
        raise NotImplementedError

    def verify(self, payload: dict) -> bool:  # pragma: no cover
        raise NotImplementedError

    def reference(self, payload: dict) -> str:
        return payload.get("payment_id") or payload.get("razorpay_payment_id") or ""


class MockGateway(BaseGateway):
    """Simulates a gateway. Signs orders with SECRET_KEY so verify() is real."""

    name = "mock"

    def _sign(self, order_id: str, payment_id: str) -> str:
        msg = f"{order_id}|{payment_id}".encode()
        return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()

    def create_order(self, invoice, amount) -> Order:
        order_id = "order_mock_" + secrets.token_hex(8)
        return Order(
            order_id=order_id,
            amount_paise=int(amount * 100),
            currency=invoice.academy.currency or "INR",
            key_id="mock_key",
            gateway=self.name,
        )

    def simulate_client_payment(self, order_id: str) -> dict:
        """What a real checkout widget would return to the browser."""
        payment_id = "pay_mock_" + secrets.token_hex(8)
        return {
            "order_id": order_id,
            "payment_id": payment_id,
            "signature": self._sign(order_id, payment_id),
        }

    def verify(self, payload: dict) -> bool:
        expected = self._sign(payload.get("order_id", ""), payload.get("payment_id", ""))
        return hmac.compare_digest(expected, payload.get("signature", ""))


class RazorpayGateway(BaseGateway):  # pragma: no cover - needs live keys
    """
    Real Razorpay integration. Requires `pip install razorpay` and
    RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET in the environment.
    """

    name = "razorpay"

    def __init__(self):
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            raise RuntimeError("Razorpay keys are not configured.")
        import razorpay  # noqa: F401

        self.client = razorpay.Client(
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
        )

    def create_order(self, invoice, amount) -> Order:
        order = self.client.order.create(
            {
                "amount": int(amount * 100),
                "currency": invoice.academy.currency or "INR",
                "receipt": invoice.number,
                "payment_capture": 1,
            }
        )
        return Order(
            order_id=order["id"],
            amount_paise=order["amount"],
            currency=order["currency"],
            key_id=settings.RAZORPAY_KEY_ID,
            gateway=self.name,
        )

    def verify(self, payload: dict) -> bool:
        try:
            self.client.utility.verify_payment_signature(
                {
                    "razorpay_order_id": payload.get("order_id"),
                    "razorpay_payment_id": payload.get("payment_id"),
                    "razorpay_signature": payload.get("signature"),
                }
            )
            return True
        except Exception:
            return False


def get_gateway() -> BaseGateway:
    from django.utils.module_loading import import_string

    return import_string(settings.PAYMENT_GATEWAY_BACKEND)()
