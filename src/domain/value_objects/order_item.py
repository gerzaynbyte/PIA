import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP

from .money import TWO_PLACES, Money

LIMITE_UNIDADES_POR_SKU = 50  # RN-07


@dataclass(frozen=True)
class SKU:
    value: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z0-9\-]{3,30}", self.value):
            raise ValueError(f"Formato de SKU inválido: '{self.value}'.")


@dataclass(frozen=True)
class OrderItem:  # Value Object: inmutable y comparable por valor
    sku: SKU
    quantity: int
    unit_price: Money

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("La cantidad debe ser mayor a cero.")
        if self.quantity > LIMITE_UNIDADES_POR_SKU:
            # RN-07: límite estricto de 50 unidades por SKU por pedido
            raise ValueError(
                f"El SKU {self.sku.value} excede el límite de "
                f"{LIMITE_UNIDADES_POR_SKU} unidades (RN-07)."
            )

    @property
    def subtotal(self) -> Money:
        importe = (self.quantity * self.unit_price.amount).quantize(TWO_PLACES, ROUND_HALF_UP)
        return Money(importe, self.unit_price.currency)
