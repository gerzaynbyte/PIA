"""Agregado de Inventario por almacén: RN-04, RN-10, RN-15.
Fórmula del glosario: Existencia Disponible = Física - Reservada."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from ..shared.entity import Entity, Identifier
from ..shared.result import Result
from ..value_objects.order_item import SKU


@dataclass
class InventoryProps:
    sku: SKU
    warehouse_id: str
    physical_stock: int
    reserved_stock: int
    updated_at: datetime


class Inventory(Entity[Identifier, InventoryProps]):
    @property
    def sku(self) -> SKU:
        return self._props.sku

    @property
    def warehouse_id(self) -> str:
        return self._props.warehouse_id

    @property
    def physical_stock(self) -> int:
        return self._props.physical_stock

    @property
    def reserved_stock(self) -> int:
        return self._props.reserved_stock

    @property
    def available_stock(self) -> int:
        return max(0, self._props.physical_stock - self._props.reserved_stock)

    @classmethod
    def create(cls, sku: SKU, warehouse_id: str, physical_stock: int) -> Result["Inventory"]:
        if physical_stock < 0:
            return Result.fail("La existencia física no puede ser negativa.")
        return Result.ok(cls(InventoryProps(
            sku=sku,
            warehouse_id=warehouse_id,
            physical_stock=physical_stock,
            reserved_stock=0,
            updated_at=datetime.now(timezone.utc),
        )))

    def _touch(self) -> None:
        self._props.updated_at = datetime.now(timezone.utc)

    def reserve(self, quantity: int) -> Result[None]:  # RN-04
        if quantity <= 0:
            return Result.fail("La cantidad a reservar debe ser mayor a cero.")
        if self.available_stock < quantity:
            return Result.fail(
                f"Existencia insuficiente para reservar {quantity} unidades "
                f"del SKU {self._props.sku.value}."
            )
        self._props.reserved_stock += quantity
        self._touch()
        return Result.ok()

    def release_reservation(self, quantity: int) -> Result[None]:  # RN-10 / cancelaciones
        if quantity <= 0:
            return Result.fail("La cantidad a liberar debe ser mayor a cero.")
        self._props.reserved_stock = max(0, self._props.reserved_stock - quantity)
        self._touch()
        return Result.ok()

    def deduct_on_fulfillment(self, quantity: int) -> Result[None]:
        if self._props.physical_stock < quantity:
            return Result.fail("No se puede despachar más producto del existente físicamente.")
        self._props.physical_stock -= quantity
        self._props.reserved_stock = max(0, self._props.reserved_stock - quantity)
        self._touch()
        return Result.ok()

    def report_discrepancy(self, actual_physical_count: int) -> None:  # RN-15
        self._props.physical_stock = max(0, actual_physical_count)
        self._touch()