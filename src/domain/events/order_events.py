import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


@dataclass(frozen=True)
class DomainEvent:
    occurred_on: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    aggregate_id: str = ""

    def __post_init__(self) -> None:
        if not self.aggregate_id:
            object.__setattr__(self, "aggregate_id", str(uuid.uuid4()))


@dataclass(frozen=True)
class OrderCreatedEvent(DomainEvent):
    customer_id: str = ""
    total_amount: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class OrderCancelledEvent(DomainEvent):
    reason: str = ""
    requested_by_role: str = ""
    destino_producto: str = ""     # RN-12: 'INVENTARIO' | 'MERMA_EMPAQUE' | ''
