"""Generated contract definitions."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.payments.models import PaymentRequest, PaymentResult

class PaymentAuthorizer(ABC):
    @abstractmethod
    def authorize(self, request: PaymentRequest) -> PaymentResult: ...


class PaymentGateway(ABC):
    @abstractmethod
    def authorize(self, request: PaymentRequest) -> PaymentResult: ...
