from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "MXN"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            # int/float/str -> Decimal vía str para no arrastrar error binario
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        if self.amount < Decimal("0"):
            raise ValueError("El monto no puede ser negativo.")

    @classmethod
    def zero(cls, currency: str = "MXN") -> "Money":
        return cls(amount=Decimal("0.00"), currency=currency)

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("No se pueden sumar montos de distintas monedas.")
        return Money((self.amount + other.amount).quantize(TWO_PLACES, ROUND_HALF_UP),
                     self.currency)

    def equals(self, other: "Money") -> bool:
        return self.currency == other.currency and self.amount == other.amount

    def is_greater_than(self, threshold: Decimal) -> bool:
        return self.amount > Decimal(str(threshold))
