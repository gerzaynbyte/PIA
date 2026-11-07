"""Adaptador InMemory del puerto OrderRepository (ADR-02: sustituible)."""
from typing import Dict, Optional

from src.domain.entities.order import Order


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._store: Dict[str, Order] = {}

    async def save(self, order: Order) -> None:
        self._store[str(order.id)] = order

    async def find_by_id(self, order_id: str) -> Optional[Order]:
        return self._store.get(order_id)