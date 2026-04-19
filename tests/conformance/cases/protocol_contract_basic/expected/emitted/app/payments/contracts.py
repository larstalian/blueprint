"""Generated contract definitions."""

from __future__ import annotations

from typing import Protocol

from app.payments.models import PaymentRequest, PaymentResult

class PaymentAuthorizer(Protocol):
    def authorize(self, request: PaymentRequest) -> PaymentResult: ...


class PaymentGateway(Protocol):
    def authorize(self, request: PaymentRequest) -> PaymentResult: ...
