"""Specifications del contexto de asignación de almacén (RN-14).

RN-14: "prioriza cercanía al domicilio y, en empate, menor carga de
pedidos pendientes. Un Agente de Almacén no puede reasignar el origen."

Composición de la preferencia (explícita, para la defensa):
    A es preferido sobre B
        <=> distancia(A) < distancia(B)
        OR  (distancia(A) == distancia(B) AND carga(A) < carga(B))
"""
from abc import ABC
from dataclasses import dataclass, field
from typing import Dict, Mapping, Sequence, Tuple

from .shared.result import Result
from .value_objects.warehouse import WarehouseId


@dataclass(frozen=True)
class CandidatoAlmacen:
    """Vista de solo-lectura de un almacén candidato para surtir un pedido."""
    warehouse_id: WarehouseId
    distancia_km: float
    carga_pendiente: int                       # pedidos pendientes de surtir
    stock_por_sku: Mapping[str, int] = field(default_factory=dict)


ItemPedido = Tuple[str, int]                   # (sku, cantidad)


class WarehouseSpecification(ABC):
    def is_satisfied_by(self, candidato: CandidatoAlmacen) -> bool:
        raise NotImplementedError


class StockSuficienteSpecification(WarehouseSpecification):
    """Filtro duro: el almacén debe cubrir el 100% de las líneas del pedido."""

    def __init__(self, items: Sequence[ItemPedido]) -> None:
        self._requerido: Dict[str, int] = {}
        for sku, cantidad in items:
            self._requerido[sku] = self._requerido.get(sku, 0) + cantidad

    def is_satisfied_by(self, candidato: CandidatoAlmacen) -> bool:
        for sku, cantidad in self._requerido.items():
            if candidato.stock_por_sku.get(sku, 0) < cantidad:
                return False
        return True


class PreferenciaAlmacenSpecification(WarehouseSpecification):
    """RN-14: orden de preferencia entre DOS candidatos válidos.

    Cercanía manda; SOLO en empate exacto decide la menor carga.
    Nótese la composición OR(AND(...)) en `es_preferido_sobre`.
    """

    def es_preferido_sobre(
        self, candidato: CandidatoAlmacen, otro: CandidatoAlmacen
    ) -> bool:
        return (
            candidato.distancia_km < otro.distancia_km
            or (
                candidato.distancia_km == otro.distancia_km
                and candidato.carga_pendiente < otro.carga_pendiente
            )
        )

    def is_satisfied_by(self, candidato: CandidatoAlmacen) -> bool:  # no usada como predicado
        return True