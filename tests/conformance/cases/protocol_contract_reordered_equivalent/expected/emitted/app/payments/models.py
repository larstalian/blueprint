"""Generated data model definitions."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

@dataclass(slots=True)
class PaymentRequest:
    amount: Decimal
    currency: str


@dataclass(slots=True)
class PaymentResult:
    accepted: bool
    reason: str
