"""Adaptador InMemory del puerto DeliveryRepository (clave = folio)."""
from typing import Dict, Optional

from src.domain.entities.delivery import Delivery


class InMemoryDeliveryRepository:
    def __init__(self) -> None:
        self._store: Dict[str, Delivery] = {}

    async def save(self, delivery: Delivery) -> None:
        self._store[delivery.sub_order_id] = delivery

    async def find_by_folio(self, folio: str) -> Optional[Delivery]:
        return self._store.get(folio)