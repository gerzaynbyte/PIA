"""Patrón Specification (reutilizable y composable) para reglas transversales."""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Generic, TypeVar

from .value_objects.order_item import LIMITE_UNIDADES_POR_SKU

T = TypeVar("T")

UMBRAL_ANTIFRAUDE_MXN = Decimal("15000")  # RN-09


class Specification(ABC, Generic[T]):
    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool: ...

    def and_(self, other: "Specification[T]") -> "AndSpecification[T]":
        return AndSpecification(self, other)

    def or_(self, other: "Specification[T]") -> "OrSpecification[T]":
        return OrSpecification(self, other)

    def not_(self) -> "NotSpecification[T]":
        return NotSpecification(self)


class AndSpecification(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        return self._left.is_satisfied_by(candidate) and self._right.is_satisfied_by(candidate)


class OrSpecification(Specification[T]):
    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        self._left, self._right = left, right

    def is_satisfied_by(self, candidate: T) -> bool:
        return self._left.is_satisfied_by(candidate) or self._right.is_satisfied_by(candidate)


class NotSpecification(Specification[T]):
    def __init__(self, inner: Specification[T]) -> None:
        self._inner = inner

    def is_satisfied_by(self, candidate: T) -> bool:
        return not self._inner.is_satisfied_by(candidate)


class LimiteUnidadesPorSkuSpecification(Specification):  # RN-07
    """El límite es POR SKU y POR PEDIDO: se suman todas las líneas del mismo SKU."""

    def totales_por_sku(self, items: list) -> Dict[str, int]:
        totales: Dict[str, int] = {}
        for item in items:
            sku = getattr(item.sku, "value", item.sku)
            totales[sku] = totales.get(sku, 0) + item.quantity
        return totales

    def excedentes(self, items: list) -> Dict[str, int]:
        return {s: q for s, q in self.totales_por_sku(items).items()
                if q > LIMITE_UNIDADES_POR_SKU}

    def is_satisfied_by(self, items: list) -> bool:
        return not self.excedentes(items)


class RequiereRevisionAntifraudeSpecification(Specification):  # RN-09
    UMBRAL = UMBRAL_ANTIFRAUDE_MXN

    def is_satisfied_by(self, order) -> bool:
        return order.total_amount.amount > self.UMBRAL
